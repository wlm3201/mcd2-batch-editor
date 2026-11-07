"""Publish verified game textures to the catalog, the glossary and public/icons."""
import argparse
import base64
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import hashlib
import io
import json
import os
from pathlib import Path
import re
import subprocess
from tempfile import NamedTemporaryFile, gettempdir

from PIL import Image


PUBLIC = Path(__file__).resolve().parents[1] / "public"
GROUPS = ("items", "effects", "enchantments")
GENERATED_ICON = re.compile(r"T_[A-Za-z0-9_-]+\.([0-9a-f]{12})\.webp")


def compact(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def sha(data):
    return hashlib.sha256(data).hexdigest()


@contextmanager
def publish_lock(public):
    # The OS releases the advisory lock if a publisher exits during a refresh.
    identity = sha(os.fsencode(os.path.normcase(str(public.resolve()))))[:24]
    with (Path(gettempdir()) / f"mcd2-icons-{identity}.lock").open("a+b") as guard:
        guard.seek(0)
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(guard.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl
            fcntl.flock(guard.fileno(), fcntl.LOCK_EX)
        yield


def write_changed(path, data):
    if path.is_file() and path.read_bytes() == data:
        return
    temp = NamedTemporaryFile(dir=path.parent, delete=False)
    try:
        with temp:
            temp.write(data)
        os.replace(temp.name, path)
    finally:
        Path(temp.name).unlink(missing_ok=True)


def encode_texture(export, row):
    package, separator, asset = row["ref"].rpartition(".")
    if not separator or asset != package.split("/")[-1] or not re.fullmatch(r"[A-Za-z0-9_-]+", asset):
        raise ValueError(f"Unexpected texture reference {row['ref']}")
    path = (export / row["file"]).resolve()
    if not path.is_relative_to((export / "png").resolve()) or path.suffix.lower() != ".png":
        raise ValueError(f"Invalid PNG path {path}")
    source = path.read_bytes()
    if sha(source) != row["pngSha256"] or row["firstMip"] != 0:
        raise ValueError(f"PNG digest or source mip mismatch: {asset}")
    with Image.open(io.BytesIO(source)) as image:
        rgba = image.convert("RGBA")
    if rgba.size != (row["width"], row["height"]) or sha(rgba.tobytes()) != row["rgbaSha256"]:
        raise ValueError(f"Source pixels differ from the game texture: {asset}")

    buffer = io.BytesIO()
    rgba.save(buffer, "WEBP", lossless=True, exact=True, method=6)
    webp = buffer.getvalue()
    with Image.open(io.BytesIO(webp)) as decoded:
        if decoded.size != rgba.size or decoded.convert("RGBA").tobytes() != rgba.tobytes():
            raise ValueError(f"Lossless WebP round-trip changed pixels: {asset}")
    return row["ref"], (f"{asset}.{sha(webp)[:12]}.webp", webp)


def sync(export, public):
    manifest = json.loads((export / "manifest.json").read_bytes())
    index = json.loads((export / "texture-index.json").read_bytes())
    catalog_file = public / "catalog.json"
    previous_catalog = catalog_file.read_bytes()
    catalog = json.loads(previous_catalog)
    version = manifest["gameVersion"]
    if not version or version != catalog["meta"]["localVerification"]["version"]:
        raise ValueError("Sync the game data and icons from the same game build")
    records = manifest["records"]
    unique_refs = manifest.get("uniqueEnchantments", {})
    extras_file = public / "extras.json"
    previous_extras = extras_file.read_bytes() if extras_file.is_file() else None
    extras = json.loads(previous_extras) if previous_extras is not None else {}
    if "uniqueEnchantments" in manifest:
        expected_unique = {tag: row["iconSource"] for tag, row in extras.get("uniqueEnchantments", {}).items()
                           if row.get("iconSource")}
        if unique_refs != expected_unique:
            raise ValueError("The fixed enchantment texture map must match the generated game data")
    expected = {(group, key) for group in GROUPS for key in catalog[group]}
    if {(r["category"], r["id"]) for r in records} != expected or len(records) != len(expected):
        raise ValueError("The icon map and catalog must contain the same entries")
    refs = {r["iconRef"] for r in records if r["iconRef"]}
    all_refs = refs | set(unique_refs.values())
    entries = index["entries"]
    if index["errors"] or not refs or all_refs != {t["ref"] for t in entries} or len(all_refs) != len(entries):
        raise ValueError("Expected one successful texture export per unique catalog reference")

    with ThreadPoolExecutor(max_workers=4) as pool:
        textures = dict(pool.map(lambda row: encode_texture(export, row), entries))
    files = {}
    for ref in sorted(refs):
        name, pixels = textures[ref]
        existing = files.get(name.casefold())
        if existing is not None and existing != (name, pixels):
            raise ValueError("Texture output filenames collide")
        files[name.casefold()] = (name, pixels)
    new_files = {name for name, _ in files.values()}
    for row in records:
        entry = catalog[row["category"]][row["id"]]
        if row["saveId"] != (entry.get("saveId") or row["id"]):
            raise ValueError(f"Save ID mismatch: {row['id']}")
        ref = row["iconRef"]
        if not ref and (entry.get("icon") or not row["sources"]):
            raise ValueError(f"Missing game table or icon binding: {row['id']}")
        entry["icon"] = textures[ref][0] if ref else None
        if ref:
            entry["iconSource"] = ref
        else:
            entry.pop("iconSource", None)
    for tag, ref in unique_refs.items():
        extras["uniqueEnchantments"][tag]["icon"] = (
            "data:image/webp;base64," + base64.b64encode(textures[ref][1]).decode("ascii"))

    catalog["meta"]["localIcons"] = {
        "version": version, "container": index["utoc"], "utocSha256": index["utocSha256"],
        "textures": len(refs), "mapped": sum(bool(r["iconRef"]) for r in records),
    }
    pools_file = public / "pools.html"
    previous_pools = pools_file.read_bytes() if pools_file.is_file() else None
    catalog_bytes = compact(catalog).encode("utf-8")

    folder = public / "icons"
    if folder.resolve() != public.resolve() / "icons":
        raise ValueError(f"Unexpected icon directory: {folder.resolve()}")
    with publish_lock(public):
        current_pools = pools_file.read_bytes() if pools_file.is_file() else None
        current_extras = extras_file.read_bytes() if extras_file.is_file() else None
        if (catalog_file.read_bytes() != previous_catalog or current_pools != previous_pools
                or current_extras != previous_extras):
            raise ValueError("The editor data changed during conversion. Run the sync again.")
        # Write images first. Both documents have valid URLs even after an interrupted write.
        folder.mkdir(exist_ok=True)
        for name, webp in files.values():
            write_changed(folder / name, webp)
        builder = Path(__file__).with_name("build-glossary.mjs")
        html = subprocess.run(["node", str(builder), str(public.resolve()), "--stdin"],
                              input=catalog_bytes, stdout=subprocess.PIPE, check=True).stdout
        write_changed(pools_file, html)
        write_changed(catalog_file, catalog_bytes)
        if "uniqueEnchantments" in manifest:
            write_changed(extras_file, compact(extras).encode("utf-8"))
        # Retire only our obsolete, content-addressed files after both readers have switched.
        for path in folder.glob("*.webp"):
            match = GENERATED_ICON.fullmatch(path.name)
            if match and path.name not in new_files and path.is_file() and not path.is_symlink():
                if sha(path.read_bytes()).startswith(match[1]):
                    path.unlink()
    print(f"{len(textures)} lossless textures, {catalog['meta']['localIcons']['mapped']} catalog icons, "
          "glossary refreshed")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("export", type=Path, help="Directory produced by extract-game-icons.py")
    parser.add_argument("--public", type=Path, default=PUBLIC, help="Editor public directory")
    args = parser.parse_args()
    sync(args.export, args.public)
