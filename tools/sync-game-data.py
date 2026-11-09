"""Rebuild editor data from extracted UFS tables, quest trees and both game locres."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
from tempfile import NamedTemporaryFile, TemporaryDirectory
from uuid import uuid4
from xml.etree import ElementTree
from hashlib import sha256

PUBLIC = Path(__file__).resolve().parents[1] / "public"


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path, data):
    options = {"indent": 1} if path.name == "zh.json" else {"separators": (",", ":")}
    path.write_bytes(json.dumps(data, ensure_ascii=False, **options).encode("utf-8"))


def localization(path):
    """UE Optimized_CityHash64_UTF16 stores key/string pairs and a shared text array."""
    stream = io.BytesIO(path.read_bytes())
    if stream.read(17).hex() != "0e147475674a03fc4a15909dc3377f1b03":
        raise ValueError("Unsupported locres version")

    def integer():
        return struct.unpack("<i", stream.read(4))[0]

    def string():
        size = integer()
        if size < 0:
            return stream.read(-2 * size).decode("utf-16-le").removesuffix("\0")
        return stream.read(size).decode("utf-8").removesuffix("\0")

    def key():
        stream.read(4)  # text key hash
        return string()

    offset, = struct.unpack("<q", stream.read(8))
    stream.seek(offset)
    texts = []
    for _ in range(integer()):
        texts.append(string())
        integer()  # reference count
    stream.seek(29)  # header, string-array offset and entry count
    result = {}
    for _ in range(integer()):
        namespace = key().rsplit("/", 1)[-1]
        for _ in range(integer()):
            item = key()
            integer()  # source hash
            result[namespace, item] = texts[integer()]
    return result


def tag_set(row):
    traits = row.get("Traits", {})
    return {v["TagName"] for key in ("GameplayTags", "ParentTags") for v in traits.get(key, [])}


def incompatible(query, item_tags):
    # FGameplayTagQuery token stream. Reject unfamiliar operators on a future build.
    version, has_root, *tokens = query["QueryTokenStream"]
    if (version, has_root) != (0, 1):
        raise ValueError("Unsupported gameplay tag query")
    tags = [v["TagName"] for v in query["TagDictionary"]]
    stream = iter(tokens)

    def evaluate():
        op, count = next(stream), next(stream)
        if op in (1, 2, 3):
            matches = [tags[next(stream)] in item_tags for _ in range(count)]
            return (any(matches), all(matches), not any(matches))[op - 1]
        if op in (4, 5, 6):
            matches = [evaluate() for _ in range(count)]
            return (any(matches), all(matches), not any(matches))[op - 4]
        raise ValueError(f"Unsupported gameplay tag operator {op}")

    result = evaluate()
    if next(stream, None) is not None:
        raise ValueError("Unconsumed gameplay tag tokens")
    return result



TOOLS = Path(__file__).resolve().parent
GENERATED = ("catalog.json", "extras.json", "zh.json", "zh-unique.json", "world-quests.json", "pools.html", "icons")


def sibling(name):
    spec = importlib.util.spec_from_file_location(name, TOOLS / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def file_hash(path):
    digest = sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def tree_hash(directory, generated_only=False):
    digest = sha256()
    if not directory.is_dir():
        return None
    files = sorted(p for p in directory.rglob("*") if p.is_file()
                   and (not generated_only or p.relative_to(directory).parts[0] in GENERATED))
    for path in files:
        digest.update(path.relative_to(directory).as_posix().encode() + b"\0")
        digest.update(bytes.fromhex(file_hash(path)))
    return digest.hexdigest()


def tool_path(value, name):
    found = str(value) if value else shutil.which(name)
    if not found or not Path(found).is_file():
        raise ValueError(f"Supply --{name} with the path to an installed {name} executable")
    return Path(found).resolve()


def run_checked(command, description, log, key="", cwd=None):
    result = subprocess.run([str(part) for part in command], cwd=cwd,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    # Native tools may echo a key in a different encoding on failure. Do not persist
    # any diagnostic bytes from a command carrying archive credentials.
    output = (f"exit={result.returncode}, stdout={len(result.stdout)} bytes, "
              f"stderr={len(result.stderr)} bytes (private tool output omitted)\n").encode() if key else result.stdout + result.stderr
    with log.open("ab") as stream:
        stream.write((description + "\n").encode() + output + b"\n")
    if result.returncode:
        raise ValueError(f"{description} failed (exit {result.returncode}); see {log}. "
                         "Encrypted builds require MCD2_AES_KEY or --key-file.")
    return result.stdout


def installed_version(game, explicit):
    config = game / "MicrosoftGame.config"
    identity = ElementTree.parse(config).getroot().find("{*}Identity")
    if identity is None or identity.get("Name") != "Microsoft.MinecraftDungeons2":
        raise ValueError(f"Not a Minecraft Dungeons II installation: {config}")
    version = identity.get("Version")
    if not version or explicit and explicit != version:
        raise ValueError("The requested version does not match MicrosoftGame.config")
    return version


def extract_resources(game, repak, raw, key, log):
    pak = game / "Dungeons/Content/Paks/Dungeons-Windows.pak"
    command = [repak, *(["-a", key] if key else [])]
    listing = run_checked([*command, "list", pak], "Read native pak directory", log, key, repak.parent)
    members = listing.decode("utf-8-sig").splitlines()
    prefixes = ("Dungeons/Content/Spicewood/Core/DataTables/UFS/",
                "Dungeons/Content/Spicewood/Quests/QuestsData/")
    locales = tuple(f"Dungeons/Content/Localization/All/{lang}/All.locres" for lang in ("en", "zh-Hans"))
    selected = [name for name in members if name.startswith(prefixes) or name in locales]
    if not all(name in selected for name in locales) or not any(name.startswith(prefixes[0]) for name in selected):
        raise ValueError("The pak no longer contains the required UFS and bilingual localization layout")
    for member in selected:
        path = Path(member)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError("Unsafe native resource path")
    run_checked([*command, "unpack", pak, "--output", raw, "--quiet",
                 *[part for include in (*prefixes, *locales) for part in ("--include", include)]],
                "Extract UFS, quests and official localization", log, key, repak.parent)
    return raw / "Dungeons/Content", pak


def generate_documents(content, output, log):
    steps = (("sync-native-catalog.py", "--defer-icons"), ("sync-native-rules.py", "--write"),
             ("sync-unique-enchantments.py", "--defer-icons"), ("sync-world.py",))
    for script, *options in steps:
        run_checked([sys.executable, "-B", TOOLS / script, content, "--public", output, *options],
                    script, log)
    catalog = read_json(output / "catalog.json")
    world = read_json(output / "world-quests.json")
    sources = sorted([*content.glob("Spicewood/Core/DataTables/UFS/*.json"),
                      *content.glob("Spicewood/Quests/QuestsData/*_Quests.json"),
                      *(content / f"Localization/All/{lang}/All.locres" for lang in ("en", "zh-Hans"))])
    digest = sha256()
    for path in sources:
        digest.update(path.relative_to(content).as_posix().encode() + b"\0" + bytes.fromhex(file_hash(path)))
    return catalog, world, digest.hexdigest(), len(sources)


def generate_icons(content, output, export, archive, retoc, key, version, jobs):
    extractor, encoder = sibling("extract-game-icons"), sibling("sync-game-icons")
    catalog = read_json(output / "catalog.json")
    extractor.game_version(archive, catalog, version)
    extras = read_json(output / "extras.json")
    manifest = extractor.icon_manifest(content / "Spicewood/Core/DataTables/UFS", catalog, version)
    manifest["uniqueEnchantments"] = {tag: row["iconSource"] for tag, row in
                                      extras.get("uniqueEnchantments", {}).items() if row.get("iconSource")}
    refs = sorted({row["iconRef"] for row in manifest["records"] if row["iconRef"]}
                  | set(manifest["uniqueEnchantments"].values()))
    listing = extractor.run_retoc(retoc, key, "list", "--path", "--size", str(archive)).decode("utf-8-sig")
    chunks = extractor.find_chunks(listing, refs)
    export.mkdir()
    with ThreadPoolExecutor(max_workers=jobs) as pool:
        textures = list(pool.map(lambda ref: extractor.extract(ref, chunks, retoc, key, archive, export), refs))
    write_json(export / "manifest.json", manifest)
    write_json(export / "texture-index.json", {
        "decoder": "Windows cooked Texture2D; highest serialized mip",
        "utoc": archive.name, "utocSha256": file_hash(archive), "entries": textures, "errors": [],
    })
    # Every pixel comes from this run's container, including unchanged paths and fixed enchantments.
    encoder.sync(export, output)
    return len(textures), manifest["counts"]


def validate_output(output):
    catalog, extras, zh = (read_json(output / name) for name in ("catalog.json", "extras.json", "zh.json"))
    for section in ("items", "effects", "enchantments"):
        if not catalog.get(section):
            raise ValueError("Empty generated catalog section: " + section)
        for identifier, entry in catalog[section].items():
            icon = entry.get("icon")
            if entry.get("iconSource") and not icon:
                raise ValueError("Missing extracted icon for " + identifier)
            if icon:
                path = output / "icons" / icon
                if path.resolve().parent != (output / "icons").resolve() or not path.is_file():
                    raise ValueError("Invalid generated image for " + identifier)
                if file_hash(path)[:12] != path.name.split(".")[-2]:
                    raise ValueError("Generated image fingerprint differs for " + identifier)
            if section == "items" and entry["name"] not in zh["items"]:
                raise ValueError("Missing official item translation: " + identifier)
            if section != "items":
                for tier in entry.get("tiers", []):
                    if tier.get("template") and tier["template"] not in zh["templates"]:
                        raise ValueError("Missing official template translation: " + tier["template"])
    for tag, entry in extras.get("uniqueEnchantments", {}).items():
        if entry.get("iconSource") and not entry.get("icon", "").startswith("data:image/webp;base64,"):
            raise ValueError("Missing fixed enchantment image: " + tag)
    if not (output / "pools.html").is_file():
        raise ValueError("The standalone effect guide was not generated")


def generated_files(directory):
    files = {}
    for name in GENERATED:
        root = directory / name
        if root.is_symlink():
            raise ValueError("Generated resource paths cannot be symlinks")
        for path in root.rglob("*") if root.is_dir() else [root]:
            if path.is_symlink() or not path.resolve().is_relative_to(directory.resolve()):
                raise ValueError("Generated resource path escaped the output directory")
            if path.is_file():
                files[path.relative_to(directory)] = path
    return files


def copy_atomic(source, destination):
    data = source.read_bytes()
    if destination.is_file() and destination.read_bytes() == data:
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp = NamedTemporaryFile(dir=destination.parent, delete=False)
    try:
        with temp:
            temp.write(data)
        os.replace(temp.name, destination)
    finally:
        Path(temp.name).unlink(missing_ok=True)


def publish(output, destination, scratch):
    if not output.resolve().is_relative_to(scratch.resolve()) or destination.is_symlink():
        raise ValueError("Invalid resource publication paths")
    old_files, new_files = generated_files(destination), generated_files(output)
    if tree_hash(output, True) == tree_hash(destination, True):
        return False
    backup = destination.parent / (".mcd2-recovery-" + uuid4().hex)
    if backup.resolve().parent != destination.parent.resolve() or not backup.name.startswith(".mcd2-recovery-"):
        raise ValueError("Invalid resource recovery path")
    backup.mkdir()
    for relative, path in old_files.items():
        copy_atomic(path, backup / relative)
    destination.mkdir(parents=True, exist_ok=True)
    # Keep watched Windows directories in place. Immutable images arrive first,
    # then auxiliary data, the catalog index and finally the self-contained guide.
    order = sorted(new_files, key=lambda relative: (
        2 if relative.as_posix() == "catalog.json" else
        3 if relative.as_posix() == "pools.html" else
        0 if relative.parts[0] == "icons" else 1, relative.as_posix()))
    try:
        for relative in order:
            copy_atomic(new_files[relative], destination / relative)
        for relative in old_files.keys() - new_files.keys():
            (destination / relative).unlink()
    except BaseException:
        failures = []
        for relative in new_files.keys() - old_files.keys():
            try:
                (destination / relative).unlink(missing_ok=True)
            except OSError as error:
                failures.append(error)
        for relative in old_files:
            try:
                copy_atomic(backup / relative, destination / relative)
            except OSError as error:
                failures.append(error)
        if failures:
            raise OSError(f"Publication failed; previous resources remain safe at {backup}. "
                          "Restore those files before retrying.") from failures[0]
        raise
    # Recovery copies are outside TemporaryDirectory, including on rollback failure.
    if backup.resolve().parent != destination.parent.resolve() or backup.is_symlink():
        raise ValueError("Unsafe previous-resource cleanup path")
    try:
        shutil.rmtree(backup)
    except OSError:
        print("Previous resource copy retained at " + str(backup), flush=True)
    return True


def refresh(args):
    destination = args.public.absolute()
    game = args.game.resolve() if args.game else None
    if game and (args.content or args.archive):
        raise ValueError("Choose either --game or the explicit --content/--archive inputs")
    if destination.is_symlink() or destination.exists() and not destination.is_dir():
        raise ValueError("The output must be a regular directory, not a symlink")
    destination = destination.resolve()
    project = TOOLS.parent.resolve()
    if project.is_relative_to(destination) or game and (game.is_relative_to(destination) or destination.is_relative_to(game)):
        raise ValueError("The resource output cannot replace the project or game installation")
    work = args.work.resolve()
    if work.is_relative_to(destination) or destination.is_relative_to(work):
        raise ValueError("Keep --work and --public in separate directory trees")
    work.mkdir(parents=True, exist_ok=True)
    run = work / ("run-" + uuid4().hex)
    run.mkdir()
    log = run / "tools.log"
    key = args.key_file.read_text(encoding="utf-8-sig").strip() if args.key_file else os.environ.get("MCD2_AES_KEY", "")
    retoc = tool_path(args.retoc, "retoc")
    version = installed_version(game, args.version) if game else args.version
    if not version or not game and not args.content:
        raise ValueError("Use --game INSTALLATION, or supply --content CONTENT --version VERSION --archive FILE.utoc")
    if game:
        content, pak = extract_resources(game, tool_path(args.repak, "repak"), run / "raw", key, log)
        archive = game / "Dungeons/Content/Paks/Dungeons-Windows.utoc"
    else:
        content, pak = args.content.resolve(), None
        if not args.archive:
            raise ValueError("--content mode also requires --archive for a complete texture refresh")
        archive = args.archive.resolve()
    if not archive.is_file():
        raise ValueError("Missing IoStore container: " + str(archive))
    destination.parent.mkdir(parents=True, exist_ok=True)
    report = {"version": version, "source": "installed-game" if game else "extracted-content",
              "pakSha256": file_hash(pak) if pak else None, "utocSha256": file_hash(archive)}
    # Stage on the destination filesystem so each published file can be replaced atomically.
    with TemporaryDirectory(prefix=".mcd2-data-", dir=destination.parent) as temp:
        scratch = Path(temp).resolve()
        if scratch.parent != destination.parent or not scratch.name.startswith(".mcd2-data-"):
            raise ValueError("Invalid resource staging root")
        output = scratch / "public"
        output.mkdir()
        print(f"Rebuilding {version} from empty staging data", flush=True)
        catalog, world, source_hash, source_count = generate_documents(content, output, log)
        catalog["meta"]["localVerification"] = {
            "version": version,
            "source": ("Dungeons-Windows.pak" if game else "Provided extracted Content")
                      + ": UFS, quests, en/zh-Hans All.locres",
            "inputTreeSha256": source_hash, "itemIds": len(catalog["items"]),
            "effects": sum(len(e["tiers"]) for e in catalog["effects"].values()),
            "enchantments": sum(len(e["tiers"]) for e in catalog["enchantments"].values()),
            "mainQuests": len(world["mainQuests"]), "stations": len(world["stations"]),
        }
        write_json(output / "catalog.json", catalog)
        print("Decoding current native textures (no old pixel cache)", flush=True)
        textures, mapping = generate_icons(content, output, run / "textures", archive, retoc, key, version, args.jobs)
        validate_output(output)
        report.update({"inputTreeSha256": source_hash, "inputFiles": source_count, "texturesDecoded": textures,
                       "icons": mapping, "generatedTreeSha256": tree_hash(output, True),
                       "items": len(catalog["items"]), "effects": len(catalog["effects"]),
                       "enchantments": len(catalog["enchantments"])})
        write_json(run / "report.json", {**report, "status": "validated"})
        publisher = sibling("sync-game-icons")
        with publisher.publish_lock(destination):
            report["changed"] = publish(output, destination, scratch)
    write_json(run / "report.json", {**report, "status": "published"})
    print(f"Validated {report['items']} items, {report['effects']} effects, {report['enchantments']} enchantments; "
          + ("published complete resources" if report["changed"] else "output is byte-identical"), flush=True)
    print("Report: " + str(run / "report.json"), flush=True)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Rebuild all editor resources from a local game, without previous generated data.")
    parser.add_argument("--game", type=Path, help="Minecraft Dungeons II installation directory")
    parser.add_argument("--content", type=Path, help="Alternatively, an extracted Dungeons/Content directory")
    parser.add_argument("--version", help="Required with --content; --game reads MicrosoftGame.config")
    parser.add_argument("--archive", type=Path, help="IoStore .utoc, required with --content")
    parser.add_argument("--repak", type=Path, help="Installed repak executable, required with --game")
    parser.add_argument("--retoc", type=Path, help="Installed retoc executable with its Oodle decoder")
    parser.add_argument("--key-file", type=Path, help="Optional private file containing the game's archive key")
    parser.add_argument("--work", type=Path, required=True, help="Separate directory for native extraction and evidence")
    parser.add_argument("--public", type=Path, default=PUBLIC, help="Resource output (default: project public)")
    parser.add_argument("--jobs", type=int, choices=range(1, 17), default=3, metavar="1..16")
    try:
        refresh(parser.parse_args())
    except (OSError, ValueError, ElementTree.ParseError, struct.error) as error:
        parser.exit(1, f"Error: {error}\n")
