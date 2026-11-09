"""Export the editor's original Windows Texture2D icons from a local game build.

Requires Python 3.10+, Pillow with BC3 support, and retoc with the game's Oodle
decoder available. Set MCD2_AES_KEY in the calling process for encrypted builds.
The UFS directory must contain the JSON tables extracted from the same build.
Use a new or empty output directory, or an identical previously completed export.
"""

import argparse
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import struct
import subprocess
from tempfile import TemporaryDirectory
from xml.etree import ElementTree

from PIL import Image


DEFAULT_CATALOG = Path(__file__).resolve().parents[1] / "public" / "catalog.json"
CATEGORIES = ("items", "effects", "enchantments")
# These UFS tables supply every catalog row in the verified Windows build,
# including the food definitions whose UI references are empty.
SOURCE_TABLES = {
    "DT_EffectDefinition", "DT_EnchantmentDefinition", "DT_FoodDefinition",
    "DT_ItemDefinitionArmor", "DT_ItemDefinitionArtifact", "DT_ItemDefinitionCape",
    "DT_ItemDefinitionEnchantmentBook", "DT_ItemDefinitionMelee", "DT_ItemDefinitionPet",
    "DT_ItemDefinitionRanged", "DT_ItemDefinitionTalisman", "DT_ItemDefinitionThrowable",
    "DT_QuestItemDefinition",
}
MOUNTS = {
    "Game": "../../../Dungeons/Content",
    "OreUI": "../../../Dungeons/Plugins/OreUI/Content",
    "SpicewoodUI": "../../../Dungeons/Plugins/SpicewoodUI/Content",
}
SLOT_DIRECTORY = "/SpicewoodUI/Spicewood/UI/Widget/Inventory/PlayerInventory/EmptyCategoryIcons"
SLOT_NAMES = ("Artifact", "Boots", "Breast", "Helmet", "Legs", "Melee", "Ranged", "Talisman")
PIXEL_FORMAT = re.compile(rb"PF_[A-Za-z0-9_]+\x00\Z")


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path, data):
    path.write_bytes((json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def game_version(archive, catalog, explicit):
    version = explicit
    if tuple(p.casefold() for p in archive.parts[-4:-1]) == ("dungeons", "content", "paks"):
        config = archive.parents[3] / "MicrosoftGame.config"
        if config.is_file():
            identity = ElementTree.parse(config).getroot().find("{*}Identity")
            if identity is None or identity.get("Name") != "Microsoft.MinecraftDungeons2" or not identity.get("Version"):
                raise ValueError(f"Invalid Minecraft Dungeons II Identity in {config}")
            version = identity.get("Version")
            if explicit and explicit != version:
                raise ValueError(f"Installed game is {version}, requested --game-version is {explicit}")
    if not version:
        raise ValueError("Supply --game-version for a container copied outside its game installation")
    verified = catalog.get("meta", {}).get("localVerification", {}).get("version")
    if verified != version:
        raise ValueError(f"Game version {version} differs from the catalog's verified version {verified!r}")
    return version


def package_path(ref):
    package, dot, asset = ref.partition(".")
    if not dot or not re.fullmatch(r"(?:/[A-Za-z0-9_-]+){2,}", package):
        raise ValueError(f"Invalid Unreal texture reference {ref!r}")
    path = PurePosixPath(package)
    if asset != path.name or path.parts[1] not in MOUNTS:
        raise ValueError(f"Unsupported Unreal mount or object name in {ref!r}")
    member = MOUNTS[path.parts[1]] + "/" + "/".join(path.parts[2:]) + ".uasset"
    return path, member


def icon_manifest(tables, catalog, version):
    files = sorted(tables.glob("*.json"))
    missing = SOURCE_TABLES - {p.stem for p in files}
    if missing:
        raise ValueError("Missing required UFS tables: " + ", ".join(sorted(missing)))
    by_tag = defaultdict(list)
    for path in files:
        rows = read_json(path)
        if path.stem in SOURCE_TABLES and (not isinstance(rows, list) or not rows):
            raise ValueError(f"Invalid or empty UFS table {path.name}")
        if not isinstance(rows, list):
            continue
        for index, row in enumerate(rows):
            tag_data = row.get("TypeTag") if isinstance(row, dict) else None
            tag = tag_data.get("TagName") if isinstance(tag_data, dict) else None
            if not isinstance(tag, str) or not tag:
                if path.stem in SOURCE_TABLES:
                    raise ValueError(f"Missing TypeTag at {path.name} row {index}")
                continue
            source = {"table": path.name, "row": index, "tag": tag}
            ref = row.get("IconReference")
            if ref not in (None, "", "None") and not isinstance(ref, str):
                raise ValueError(f"Unexpected IconReference at {path.name} row {index}")
            by_tag[tag.casefold()].append((source, ref))

    records = []
    for category in CATEGORIES:
        entries = catalog.get(category)
        if not isinstance(entries, dict) or not entries:
            raise ValueError(f"Missing or empty catalog category {category}")
        for identifier, entry in entries.items():
            save_id = entry.get("saveId") or identifier
            rows = by_tag.get(save_id.casefold(), [])
            matches = defaultdict(list)
            for source, ref in rows:
                if ref and ref != "None":
                    matches[ref].append(source)
            if len(matches) > 1:
                raise ValueError(f"Conflicting IconReference values for {save_id}: {', '.join(matches)}")
            ref = next(iter(matches), None)
            record = {"category": category, "id": identifier, "saveId": save_id, "iconRef": ref,
                      "package": str(package_path(ref)[0]) if ref else None,
                      "sources": matches[ref] if ref else [source for source, _ in rows]}
            if not ref:
                record["reason"] = "no IconReference in matched rows" if rows else "no matching TypeTag"
            records.append(record)

    refs = Counter(row["iconRef"] for row in records if row["iconRef"])
    if not refs:
        raise ValueError("The supplied game tables contain no catalog icon references")
    return {"schema": 1, "gameVersion": version,
            "counts": {"records": len(records), "mapped": sum(refs.values()), "textures": len(refs),
                       "sharedTextures": sum(n > 1 for n in refs.values())}, "records": records}


def run_retoc(retoc, key, operation, *args):
    command = [str(retoc)]
    if key:
        command.extend(["-a", key])
    # A retoc usage error can quote its arguments. Keep both streams private on
    # failure, including for the initial directory listing.
    result = subprocess.run([*command, operation, *args], cwd=retoc.parent,
                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=False)
    if result.returncode:
        raise ValueError(f"retoc {operation} failed (exit {result.returncode}). "
                         "Check the container, Oodle decoder and MCD2_AES_KEY.")
    return result.stdout


def find_chunks(listing, refs):
    targets = {package_path(ref)[1].casefold() for ref in refs}
    if len(targets) != len(refs):
        raise ValueError("Multiple texture references point to the same case-insensitive file path")
    chunks = {}
    for line in listing.splitlines():
        fields = line.split(maxsplit=4)
        if len(fields) != 5 or fields[2] != "ExportBundleData":
            continue
        _, chunk, _, size, member = fields
        target = member.casefold()
        if target not in targets:
            continue
        if (target in chunks or not re.fullmatch(r"[a-fA-F0-9]{24}", chunk)
                or not re.fullmatch(r"[1-9][0-9]*", size)):
            raise ValueError(f"Invalid or ambiguous IoStore export {member}")
        chunks[target] = (chunk, int(size), member)
    missing = targets - chunks.keys()
    if missing:
        raise ValueError(f"Missing {len(missing)} Texture2D exports in IoStore, including {min(missing)}")
    return chunks


def read_bulk_map(data):
    # This unversioned Zen layout stores the local name batch at byte 60,
    # followed by a padded, byte-counted array of 32-byte FBulkDataMapEntry.
    versioned, header_size = struct.unpack_from("<II", data)
    if versioned or not 76 <= header_size < len(data):
        raise ValueError("Unsupported Zen package summary")
    names, name_bytes = struct.unpack_from("<II", data, 60)
    end = 76 + 10 * names + name_bytes
    if end + 8 > header_size:
        raise ValueError("Invalid Zen name map")
    padding, = struct.unpack_from("<Q", data, end)
    at = end + 8 + padding
    if padding > 7 or at + 8 > header_size:
        raise ValueError("Invalid Zen bulk-map padding")
    size, = struct.unpack_from("<Q", data, at)
    at += 8
    if not size or size % 32 or at + size > header_size:
        raise ValueError("Invalid Zen bulk map")
    return header_size, list(struct.iter_unpack("<qqqIB3x", data[at:at + size]))


def top_mip(data):
    header, bulk = read_bulk_map(data)
    # Accept only ForceInlinePayload, optionally combined with SingleUse. In
    # particular, bulk compression and external/duplicate storage need separate
    # decoding even if the payload happens to have the expected byte count.
    for offset, duplicate, size, flags, cooked_index in bulk:
        if flags not in (0x40, 0x48) or duplicate != -1 or cooked_index != 0:
            raise ValueError(f"Unsupported bulk storage or compression (flags 0x{flags:x})")
        if offset < 0 or size <= 0 or header + offset + size + 12 > len(data):
            raise ValueError("Invalid inline mip offset or length")

    offset, _, size, _, _ = bulk[0]
    start = header + offset
    # FirstMipToSerialize, mip count and the first bulk map index (3 int32s)
    # immediately follow the pixel-format FString in FTexturePlatformData.
    format_end = start - 12
    match = PIXEL_FORMAT.search(data, max(header + 16, format_end - 48), format_end)
    if match is None:
        raise ValueError("Missing Texture2D platform data before the first inline mip")
    width, height, slices, string_size = struct.unpack_from("<iiIi", data, match.start() - 16)
    first, count, index = struct.unpack_from("<iii", data, format_end)
    if first != 0:
        raise ValueError(f"Full-resolution mip zero is unavailable (FirstMipToSerialize={first})")
    if (index != 0 or count != len(bulk) or slices != 1 or string_size != len(match.group())
            or not 0 < width <= 16384 or not 0 < height <= 16384):
        raise ValueError("Texture2D platform data disagrees with the bulk map")
    if struct.unpack_from("<iii", data, start + size) != (width, height, 1):
        raise ValueError("Top mip dimensions disagree with the Texture2D platform dimensions")
    fmt = match.group()[:-1].decode("ascii")
    if fmt == "PF_DXT5":
        expected = ((width + 3) // 4) * ((height + 3) // 4) * 16
        codec, layout = "bcn", (3, "DXT5")
    elif fmt == "PF_B8G8R8A8":
        expected = width * height * 4
        codec, layout = "raw", "BGRA"
    else:
        raise ValueError(f"Unsupported Texture2D pixel format {fmt}")
    if size != expected:
        raise ValueError(f"Invalid {fmt} mip size: expected {expected}, got {size}")
    pixels = data[start:start + size]
    image = Image.frombytes("RGBA", (width, height), pixels, codec, layout)
    return image, {"width": width, "height": height, "format": fmt, "firstMip": first,
                   "mipCount": count, "mipBytes": size, "mipSha256": sha256(pixels)}


def extract(ref, chunks, retoc, key, archive, output):
    package, member = package_path(ref)
    chunk, length, physical = chunks[member.casefold()]
    try:
        raw = run_retoc(retoc, key, "get", str(archive), chunk)
    except ValueError as error:
        raise ValueError(f"Cannot read {ref} (chunk {chunk}): {error}") from error
    if len(raw) != length:
        raise ValueError(f"Size mismatch in chunk {chunk} for {ref}")
    try:
        image, metadata = top_mip(raw)
    except (ValueError, struct.error, OSError) as error:
        raise ValueError(f"Cannot decode {ref}: {error}") from error
    png = PurePosixPath("png", *package.parts[1:]).with_suffix(".png")
    path = output / png
    path.parent.mkdir(parents=True, exist_ok=True)
    with image:
        image.save(path, format="PNG", compress_level=6)
        rgba_hash = sha256(image.tobytes())
        alpha_range = list(image.getchannel("A").getextrema())
    return {"ref": ref, "package": str(package), "file": png.as_posix(), "member": physical,
            "chunk": chunk, "chunkBytes": length, "chunkSha256": sha256(raw), **metadata,
            "rgbaSha256": rgba_hash, "pngSha256": sha256(path.read_bytes()), "alphaRange": alpha_range}


def needs_publish(source, destination):
    if not destination.exists() or destination.is_dir() and not any(destination.iterdir()):
        return True
    error = ValueError(f"Existing output differs from this export. Choose an empty directory: {destination}")
    if not destination.is_dir() or {p.name for p in source.iterdir()} != {p.name for p in destination.iterdir()}:
        raise error
    expected = {p.relative_to(source) for p in source.rglob("*")}
    if expected != {p.relative_to(destination) for p in destination.rglob("*")}:
        raise error
    for relative in expected:
        new, old = source / relative, destination / relative
        if old.is_symlink() or new.is_dir() != old.is_dir():
            raise error
        if new.is_file() and (not old.is_file() or new.read_bytes() != old.read_bytes()):
            raise error
    return False


def main(args):
    archive = args.archive.resolve()
    retoc = args.retoc.resolve()
    if not archive.is_file() or not retoc.is_file():
        raise ValueError("The IoStore container and retoc executable must both exist")
    catalog = read_json(args.catalog)
    version = game_version(archive, catalog, args.game_version)
    manifest = icon_manifest(args.tables, catalog, version)
    refs = sorted({row["iconRef"] for row in manifest["records"] if row["iconRef"]})
    output = args.output.resolve()
    exports = [(output, refs, manifest)]
    if args.slot_icons:
        slots = args.slot_icons.resolve()
        if slots == output or slots in output.parents or output in slots.parents:
            raise ValueError("Slot and catalog outputs require separate, non-nested directories")
        slot_refs = [f"{SLOT_DIRECTORY}/T_UI_Icon_{name}.T_UI_Icon_{name}" for name in SLOT_NAMES]
        exports.append((slots, slot_refs, None))

    key = os.environ.get("MCD2_AES_KEY")
    listing = run_retoc(retoc, key, "list", "--path", "--size", str(archive)).decode("utf-8")
    chunks = find_chunks(listing, [ref for _, group, _ in exports for ref in group])
    utoc_hash = sha256(archive.read_bytes())
    # Stage on each destination filesystem, then publish only complete exports.
    # Existing files are never removed or overwritten, including after a failure.
    with ExitStack() as stack:
        pending = []
        for destination, group, mapping in exports:
            destination.parent.mkdir(parents=True, exist_ok=True)
            temp = stack.enter_context(TemporaryDirectory(prefix=".mcd2-icons-", dir=destination.parent))
            staged = Path(temp) / "export"
            staged.mkdir()

            def decode(ref):
                return extract(ref, chunks, retoc, key, archive, staged)

            with ThreadPoolExecutor(max_workers=3) as pool:
                entries = list(pool.map(decode, group))
            if mapping is not None:
                write_json(staged / "manifest.json", mapping)
            write_json(staged / "texture-index.json", {
                "decoder": f"MCD2 Windows {version} cooked Texture2D; highest serialized mip",
                "utoc": archive.name, "utocSha256": utoc_hash, "entries": entries, "errors": [],
            })
            if needs_publish(staged, destination):
                pending.append((staged, destination))
        for staged, destination in pending:
            if destination.exists():
                destination.rmdir()  # Only succeeds for an empty directory.
            staged.rename(destination)

    counts = manifest["counts"]
    print(f"{counts['mapped']}/{counts['records']} catalog entries mapped to {counts['textures']} original textures")
    if args.slot_icons:
        print(f"{len(SLOT_NAMES)} inventory slot textures exported separately to {slots}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tables", type=Path, help="Extracted Spicewood/Core/DataTables/UFS directory")
    parser.add_argument("archive", type=Path, help="Dungeons-Windows.utoc alongside its .ucas data")
    parser.add_argument("output", type=Path, help="Dedicated output for manifest.json, texture-index.json and png/")
    parser.add_argument("--retoc", required=True, type=Path, help="Path to the retoc executable")
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG, help="Editor catalog (default: public/catalog.json)")
    parser.add_argument("--game-version", help="Build version, required when no installed MicrosoftGame.config is available")
    parser.add_argument("--slot-icons", type=Path, metavar="DIR", help="Separately export eight original empty inventory slot icons")
    try:
        main(parser.parse_args())
    except (OSError, ValueError, ElementTree.ParseError, struct.error) as exc:
        parser.exit(1, f"Error: {exc}\n")
