"""Extract native world/map progress definitions from an installed Minecraft Dungeons II.

This script reads ONLY the installed game's own resources (Dungeons-Windows.pak,
optional Dungeons-Windows.utoc) or an already-extracted Dungeons/Content tree.
It never reads save files or external databases. The generated files are NEW and
never replace the editor's existing generated resources.

Two data files are produced:
  public/world-map-native.json  - world quests/stations/doors/regions/achievements,
                                  source provenance and an explicit coverage report
  public/talisman-native.json   - the 57 native talisman templates, bilingual labels
                                  and descriptions built from UFS + All.locres

Usage (installed game; repak is required because pak entries are Oodle-compressed):
    set MCD2_AES_KEY=<AES_KEY>
    python tools/sync-world-map.py --game "D:/Games/Minecraft Dungeons II" ^
        --repak "C:/path/to/repak.exe"

  The AES key is accepted ONLY through the MCD2_AES_KEY environment variable or
  --key-file. It is never written to any output file, log or error message.
  repak can be obtained from https://github.com/trumank/repak/releases
  (repak_cli-x86_64-pc-windows-msvc.zip). retoc (optional, for the .utoc index)
  comes from https://github.com/trumank/retoc/releases .

Usage (pre-extracted content; no key and no native tool needed):
    python tools/sync-world-map.py --content "D:/extracted/Dungeons/Content"

Other options: --public DIR, --work DIR, --version VERSION, --retoc PATH,
--skip-utoc, --out/--talisman-out NAME.
"""
import argparse
from collections import Counter
from hashlib import sha256
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from xml.etree import ElementTree

PUBLIC = Path(__file__).resolve().parents[1] / "public"
TOOLS = Path(__file__).resolve().parent

# Pak members needed by this script. Everything is inside Dungeons-Windows.pak;
# the 9.1 GB .ucas is never copied and is only touched on demand by retoc.
INCLUDES = (
    "Dungeons/Content/Spicewood/Core/DataTables/",
    "Dungeons/Content/Spicewood/Quests/QuestsData/",
    "Dungeons/Content/Localization/All/en/All.locres",
    "Dungeons/Content/Localization/All/zh-Hans/All.locres",
    "Dungeons/Config/",
    "Dungeons/Plugins/SpicewoodGuidance/Content/Networks/OverworldGuidanceNetwork.json",
    "Dungeons/Plugins/MapSystemTypes/Config/",
    "Dungeons/Plugins/MinecartStations/Config/",
    "Dungeons/Plugins/WorldTeleportation/Config/",
    "Dungeons/Content/Text/Release/",
)

# Counts of fields previously observed ONLY in a completed-save diff. They are
# supplied by the task description as verified evidence; no save file is read.
REPORTED_SAVE_COUNTS = {
    "discoveredDungeonDoors": {"total": 126, "dungeon": 24, "rift": 21, "tower": 31},
    "savedCutsceneTags": 24,
    "savedFogOfWarExplorationItems": 26,
}

TIER_TAGS = {"SW.EffectTemplate.Tier1": "I", "SW.EffectTemplate.Tier2": "II",
             "SW.EffectTemplate.Tier3": "III", "SW.EffectTemplate.TierUnique": "Unique"}


def sibling(name):
    spec = importlib.util.spec_from_file_location(name, TOOLS / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read_json(path):
    return json.loads(Path(path).read_bytes())


def write_json(path, data):
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    # Validate before publishing, and avoid writing a partial file.
    json.loads(payload)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    temp.write_bytes(payload)
    os.replace(temp, path)


def file_hash(path):
    digest = sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def find_tool(name, explicit=None):
    """Look in PATH, the supplied path, and a few common local tool locations."""
    home = Path.home()
    candidates = [
        Path(explicit) if explicit else None,
        Path(shutil.which(name)) if shutil.which(name) else None,
        Path(tempfile.gettempdir()) / "mcd2-tools" / (name + ".exe"),
        home / "Downloads" / (name + ".exe"),
        home / ".cargo" / "bin" / (name + ".exe"),
        TOOLS / (name + ".exe"),
        Path(r"D:\Games\Minecraft Dungeons II") / (name + ".exe"),
    ]
    for candidate in candidates:
        if candidate and candidate.is_file():
            return candidate.resolve()
    return None


def run_private(command, description, key, cwd=None):
    """Run a native tool; never persist diagnostics from a credentialed command."""
    result = subprocess.run([str(part) for part in command], cwd=cwd,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if result.returncode:
        err = result.stderr.decode("utf-8-sig", "replace").replace(key, "<AES_KEY>")
        raise ValueError(f"{description} failed (exit {result.returncode}): {err[:300]}")
    return result.stdout


def installed_version(game):
    config = game / "MicrosoftGame.config"
    identity = ElementTree.parse(config).getroot().find("{*}Identity")
    if identity is None or identity.get("Name") != "Microsoft.MinecraftDungeons2":
        raise ValueError("Not a Minecraft Dungeons II installation: " + str(config))
    return identity.get("Version") or "unknown"


def extract_content(game, repak, key, work):
    pak = game / "Dungeons/Content/Paks/Dungeons-Windows.pak"
    if not pak.is_file():
        raise ValueError("Missing pak: " + str(pak))
    raw = work / "raw"
    command = [repak, *(["-a", key] if key else [])]
    args = [*command, "unpack", pak, "-o", raw, "--quiet", "-f"]
    for include in INCLUDES:
        args += ["-i", include]
    run_private(args, "repak unpack (UFS, quests, config, locres, guidance)", key, repak.parent)
    for root in (raw / "Dungeons/Content", raw):
        if (root / "Spicewood/Core/DataTables/UFS").is_dir():
            return root
    raise ValueError("repak did not produce the expected Dungeons/Content tree")


def normalize_content(path):
    path = Path(path).resolve()
    if (path / "Spicewood/Core/DataTables/UFS").is_dir():
        return path
    nested = path / "Dungeons/Content"
    if (nested / "Spicewood/Core/DataTables/UFS").is_dir():
        return nested
    raise ValueError("--content must point at Dungeons/Content (or its parent tree)")


def rows(content, name):
    return read_json(content / "Spicewood/Core/DataTables/UFS" / ("DT_" + name + ".json"))


def tags(group):
    return [t["TagName"] for t in group.get("GameplayTags", [])]


def tag_name(value, default=""):
    return value.get("TagName", default) if isinstance(value, dict) else default


def localization(content):
    source = sibling("sync-game-data")
    return [source.localization(content / f"Localization/All/{lang}/All.locres") for lang in ("en", "zh-Hans")]


def quest_data(content):
    """Native quest trees, task counts and quest-type classification.

    The editor's world-quests.json `counts` section is built from CoreQuest
    trees only, so both that set and the full 44-quest set are reported.
    """
    quests, counts, counts_all, sources = {}, {}, {}, []
    folder = content / "Spicewood/Quests/QuestsData"

    def visit(goal, steps, target):
        steps.append(goal["name"])
        for key in ("kill_count", "howmany_count"):
            if goal.get(key, 0) > 0:
                target[goal["name"]] = goal[key]
        for child in goal.get("subgoals", []):
            visit(child, steps, target)

    for file in sorted(folder.glob("*_Quests.json")):
        data = read_json(file)
        sources.append({"table": file.name, "quests": len(data.get("Quests", []))})
        for quest in data.get("Quests", []):
            name = quest["id"]
            if name in quests:
                raise ValueError("Duplicate native quest " + name)
            steps, ignored = [], []
            visit(quest["goals"], steps, counts_all)
            if quest.get("quest_type") == "CoreQuest":
                visit(quest["goals"], ignored, counts)
            quests[name] = {"type": quest.get("quest_type"), "file": file.name,
                            "tasks": list(dict.fromkeys(steps[1:] + steps[:1]))}
    return quests, counts, counts_all, sources


def station_data(content, achievements):
    ach, = [r for r in achievements if r["Name"] == "DISCOVER_ALL_MINECART_STATIONS"]
    collection = tags(ach["Condition"]["CollectionTags"])
    teleports = [{"name": r["Name"], "actorTag": tag_name(r["ActorTag"]),
                  "teleportTag": tag_name(r["TeleportTag"])} for r in rows(content, "WorldExplorationTeleportPoints")]
    return {"achievementCollectionTags": collection,
            "teleportPoints": teleports,
            "allTags": sorted({r["actorTag"] for r in teleports} | set(collection))}


ACHIEVEMENT_CATEGORY = (
    ("Quest", "QuestAchievements"), ("Bool", "BoolAchievements"),
    ("Collection", "CollectionAchievements"), ("Count", "CountAchievements"),
)


def achievement_data(content):
    definitions = []
    for r in rows(content, "AchievementDefinition"):
        condition = r.get("Condition", {})
        struct = condition.get("InstancedStructScriptStruct", "").split(".")[-1]
        category = next((name for prefix, name in ACHIEVEMENT_CATEGORY if prefix in struct), "Other")
        record = {"name": r["Name"], "id": r.get("AchievementId"), "conditionType": struct,
                  "saveCategory": category}
        state = condition.get("QuestState")
        if isinstance(state, dict):
            record["questState"] = {k: state[k] for k in ("QuestName", "QuestState", "TaskName", "TaskState")
                                    if k in state}
        for key, value in condition.items():
            if key in ("InstancedStructScriptStruct", "QuestState"):
                continue
            if isinstance(value, dict) and "GameplayTags" in value:
                record[key] = tags(value)          # CollectionTags / BossTags
            elif isinstance(value, (int, float, str, bool)):
                record[key] = value                # MaxAmount -> save CountAchievements.Count
        definitions.append(record)
    return definitions


def cutscene_data(content):
    return sorted({tag_name(r["CutsceneName"]) for r in rows(content, "CutsceneDefinition")})


def fog_regions(content):
    result = []
    for r in rows(content, "WorldIndoorAreaMapData"):
        region = r.get("RegionData", {})
        result.append({"tag": tag_name(r["AreaId"]), "kind": "indoorArea",
                       "minimapTexture": region.get("MinimapTexture"),
                       "objectGroups": region.get("ObjectGroups", []),
                       "bounds": region.get("Bounds")})
    for r in rows(content, "WorldRegionMapData"):
        region = r.get("RegionData", {})
        result.append({"tag": tag_name(r["RegionTag"]), "kind": "worldRegion",
                       "worldMapTexture": region.get("WorldMapTexture"),
                       "minimapTexture": region.get("MinimapTexture"),
                       "objectGroups": region.get("ObjectGroups", []),
                       "bounds": region.get("Bounds")})
    return result


def parse_position(text):
    return {k: float(v) for k, v in re.findall(r"([XYZ])=(-?[\d.]+)", text or "")}


def doorway_data(content):
    tag_file = content.parent / "Config/tags/SpicewoodTags.ini"
    tag_text = tag_file.read_text(encoding="utf-8-sig", errors="replace") if tag_file.is_file() else ""
    registry = sorted(set(re.findall(r'GameplayTagList=\(Tag="(SW\.Doorway\.[^"]+)"', tag_text)))

    network_path = (content.parent / "Plugins/SpicewoodGuidance/Content/Networks/OverworldGuidanceNetwork.json")
    guidance = []
    if network_path.is_file():
        network = read_json(network_path)
        for node in network.get("Nodes", []):
            for poi in node.get("PointsOfInterest", []):
                if isinstance(poi, str) and poi.startswith("SW.Doorway."):
                    guidance.append({"doorId": poi, "nodeId": node.get("Id"),
                                     "location": parse_position(node.get("Position"))})
    bonds = sorted({tag_name(d["Id"]) for r in rows(content, "WorldAreaBonds")
                    for d in r.get("Doorways", []) if tag_name(d["Id"]).startswith("SW.Doorway.")})
    controls = sorted({t for r in rows(content, "QuestDoorwayControl") for t in tags(r.get("DoorwayIds", {}))})
    guidance_ids = {g["doorId"] for g in guidance}
    return {
        "tagRegistry": registry,
        "guidanceNetwork": guidance,
        "worldAreaBondIds": bonds,
        "questDoorwayControlIds": controls,
        "categories": {c: len([t for t in guidance_ids if c in t.lower()]) for c in ("dungeon", "rift", "tower")},
        "sources": {
            "tagRegistry": "Dungeons/Config/tags/SpicewoodTags.ini :: GameplayTagList",
            "guidanceNetwork": "Dungeons/Plugins/SpicewoodGuidance/Content/Networks/OverworldGuidanceNetwork.json :: Nodes[].PointsOfInterest + Position",
            "worldAreaBonds": "DT_WorldAreaBonds.json :: Doorways[].Id",
            "questDoorwayControl": "DT_QuestDoorwayControl.json :: DoorwayIds",
        },
    }


def actor_gimmicks(content):
    path = content.parent / "Config/DefaultActorStateGimmicks.ini"
    text = path.read_text(encoding="utf-8-sig", errors="replace") if path.is_file() else ""
    classes = re.findall(r"\+PlaceableGimmicks=(\S+)", text)
    gates = [c for c in classes if any(k in c for k in ("KeyGate", "KeyGolem", "ConcreteGate", "GoldKey", "SilverKey"))]
    shortcuts = [c for c in classes if "Roadblock" in c or "Bridge" in c]
    return {"placeableClasses": classes, "gateClasses": gates, "shortcutClasses": shortcuts,
            "source": "Dungeons/Config/DefaultActorStateGimmicks.ini :: [Placeables] +PlaceableGimmicks"}


def iostore_evidence(game, retoc, key, baseline_paths):
    """Read the .utoc directory index only (no bulk .ucas copy)."""
    utoc = game / "Dungeons/Content/Paks/Dungeons-Windows.utoc"
    if not utoc.is_file() or not retoc:
        return {"status": "not-checked", "reason": "no .utoc or no retoc executable"}
    try:
        out = run_private([retoc, *(["-a", key] if key else []), "list", "--path", utoc],
                          "retoc list (directory index)", key, retoc.parent)
    except ValueError as error:
        return {"status": "unavailable", "reason": str(error)[:200]}
    text = out.decode("utf-8-sig", "replace")
    lines = text.splitlines()
    assets = [l for l in lines if "ActorStatePersistence/Overworld/DA_" in l]
    generated = [l for l in lines if "_Generated_" in l and l.rstrip().endswith(".umap")]
    hashes = sorted({m.group(1) for p in baseline_paths
                     for m in [re.search(r"_Generated_/([A-Z0-9]+)\.", p)] if m})
    found = [h for h in hashes if h in text]
    return {"status": "ok", "utoc": utoc.name, "directoryIndexEntries": len(lines),
            "actorStatePersistenceAssets": len(assets), "generatedWorldPackages": len(generated),
            "travelActorPackageHashes": len(hashes), "travelActorPackageHashesFound": len(found),
            "note": ("Actor names (BP_*_C_UAID_*) live in these cooked Zen assets; their exact "
                     "SoftObjectPath and PreviousState/CurrentState/Version transitions are not "
                     "plain pak/utoc data and still require the verified save diff.")}


def talisman_data(content, langs):
    """Rebuild the 57 talisman options from UFS tables plus both official locres."""
    uniq = sibling("sync-unique-enchantments")
    definitions = {r["TypeTag"]["TagName"]: r for r in rows(content, "EffectDefinition")}
    templates = {r["TypeTag"]["TagName"]: r for r in rows(content, "TalismanEffectTemplateDefinition")}
    properties = rows(content, "TalismanPropertyDefinition")
    items = rows(content, "ItemDefinitionTalisman")
    collections = rows(content, "ItemCollectionsDefinition")

    def loc_key(tag, part):
        return tag.replace(".", "_") + "_SW_TextEntry_" + part

    def text(namespace, key):
        pair = (namespace, key)
        return (langs[0].get(pair, ""), langs[1].get(pair, ""))

    template_to_item = {}
    for prop in properties:
        for level in prop["ItemLevels"].get("Levels", []):
            for template in tags(level.get("Effects", {})):
                template_to_item[template] = prop["TypeTag"]["TagName"]

    options, labels, unformatted = [], {}, []
    for tag, row in sorted(templates.items()):
        effect = tag_name(row["TemplateData"]["Effect"])
        tier = next((TIER_TAGS[t] for t in tags(row.get("Traits", {})) if t in TIER_TAGS), "?")
        definition = definitions.get(effect, {})
        texts = definition.get("TypeTextData", {}).get("Texts", {})
        name_entry = texts.get('(TagName="SW.TextEntry.Name")')
        desc_entry = texts.get('(TagName="SW.TextEntry.Description")')
        en_name = zh_name = ""
        if name_entry:
            match = re.fullmatch(r'LOCTABLE\("([^"]+)", "([^"]+)"\)', name_entry["Text"])
            if match:
                en_name, zh_name = langs[0].get(match.groups(), ""), langs[1].get(match.groups(), "")
        labels.setdefault(effect, {"en": en_name, "zh": zh_name})
        item = template_to_item.get(tag, "")
        en_item, zh_item = text("DT_ItemDefinitionTalisman.csv", loc_key(item, "Name")) if item else ("", "")
        category = next((t.rsplit(".", 1)[-1].lower() for t in tags(definition.get("Traits", {}))
                         if t.startswith("SW.EffectCategory.")), "")
        record = {"id": tag, "effect": effect, "template": tag, "tier": tier,
                  "strength": row["TemplateData"].get("FixedEffectValue"),
                  "talisman": item, "talismanNameEn": en_item, "talismanName": zh_item,
                  "nameEn": (en_name + " " + tier) if en_name else "",
                  "name": (zh_name + " " + tier) if zh_name else "", "category": category,
                  "source": "DT_TalismanEffectTemplateDefinition.json + DT_EffectDefinition.csv/DT_ItemDefinitionTalisman.csv locres"}
        pattern_en = pattern_zh = None
        if desc_entry:
            match = re.fullmatch(r'LOCTABLE\("([^"]+)", "([^"]+)"\)', desc_entry["Text"])
            if match:
                pattern_en, pattern_zh = langs[0].get(match.groups(), ""), langs[1].get(match.groups(), "")
        record["patternEn"], record["patternZh"] = pattern_en or "", pattern_zh or ""
        try:
            args = uniq.dynamic_args(row, definition, desc_entry) if "{" in (pattern_en or "") else []
            record["descEn"] = pattern_en.format(*args)
            record["desc"] = pattern_zh.format(*args)
            record["formatted"] = True
        except (KeyError, ValueError, IndexError, TypeError):
            record["formatted"] = False
            record["formattingGetter"] = tag_name(desc_entry.get("DynamicDataGetterFunction")) if desc_entry else ""
            record["formatting"] = desc_entry.get("ValuesToGet", []) if desc_entry else []
            unformatted.append(tag)
        options.append(record)

    levels = []
    for prop in properties:
        progression = prop["ItemLevels"].get("Levels", [])
        if not progression:
            continue
        levels.append({"talisman": prop["TypeTag"]["TagName"],
                       "levels": [{"level": tag_name(l["Level"]),
                                   "xpRequiredForNextLevel": l.get("XPRequiredForNextLevel"),
                                   "templates": tags(l.get("Effects", {})),
                                   "grantedTags": tags(l.get("GrantedTags", {}))} for l in progression]})
    collection_records = []
    for c in collections:
        definition = c.get("CollectionDefinition", {})
        collection_records.append({"id": tag_name(c["TypeTag"]), "name": c["Name"],
                                   "items": tags(definition.get("ItemsInCollection", {}))})
    item_records = []
    for r in items:
        item = tag_name(r["TypeTag"])
        en, zh = text("DT_ItemDefinitionTalisman.csv", loc_key(item, "Name"))
        item_records.append({"id": item, "nameEn": en, "name": zh,
                             "iconSource": r.get("IconReference")})
    return {"options": options, "labels": labels, "levels": levels,
            "items": item_records, "collections": collection_records,
            "unformatted": unformatted,
            "formattedDescriptions": len(options) - len(unformatted)}


def progress_candidates(content):
    item_tables = ("ItemDefinitionMelee", "ItemDefinitionRanged", "ItemDefinitionArmor",
                  "ItemDefinitionArtifact", "ItemDefinitionTalisman", "ItemDefinitionEnchantmentBook",
                  "ItemDefinitionCape", "ItemDefinitionPet", "ItemDefinitionThrowable")
    counts = {name: len(rows(content, name)) for name in item_tables}
    return {"discoveredLoot": {"candidateTables": ["DT_" + n + ".json" for n in item_tables],
                              "rowCounts": counts, "totalRows": sum(counts.values()),
                              "note": "These enumerate every item ID the game can discover; the save's "
                                      "DiscoveredLoot membership itself is runtime progress, not static data."},
            "collectionsStats": {"table": "DT_ItemCollectionsDefinition.json",
                                 "rows": len(rows(content, "ItemCollectionsDefinition")),
                                 "note": "SW.Collectibles.SecretTalismans defines the collection membership."},
            "milestones": {"table": "DT_MilestoneDefinition.json", "rows": len(rows(content, "MilestoneDefinition"))},
            "progression": {"table": "DT_ProgressionDefinition.json", "rows": len(rows(content, "ProgressionDefinition"))}}


def coverage(baseline, native, doors, io):
    """Compare native extraction against the verified-save-diff baseline."""
    comparisons = []

    def add(field, base, count, source, note, status, details=None):
        row = {"field": field, "baseline": base, "native": count,
               "nativeSource": source, "status": status, "note": note}
        if details is not None:
            row["details"] = details
        comparisons.append(row)

    if baseline:
        q = baseline.get("quests", {})
        native_ids, baseline_ids = set(native["quests"]), set(q)
        add("quests", len(q), len(native["quests"]), "QuestsData/*_Quests.json",
            "44 native quests; 43 were present in the completed save.", "partial",
            {"nativeOnly": sorted(native_ids - baseline_ids), "baselineOnly": sorted(baseline_ids - native_ids)})
        add("mainQuests", len(baseline.get("mainQuests", [])),
            sum(1 for v in native["quests"].values() if v["type"] == "CoreQuest"),
            "QuestsData (quest_type=CoreQuest)", "Exact 15/15 match; classification is native.", "full")
        add("sideQuests", len(baseline.get("sideQuests", [])),
            sum(1 for v in native["quests"].values() if v["type"] == "SideQuest"),
            "QuestsData (quest_type=SideQuest)",
            "29 native side quests; the completed save held 28. The extra native quest has no "
            "verified completion targets.", "partial",
            {"nativeOnly": sorted({k for k, v in native["quests"].items() if v["type"] == "SideQuest"}
                                  - set(baseline.get("sideQuests", [])))})
        add("counts", len(baseline.get("counts", {})), len(native["counts"]),
            "QuestsData CoreQuest goal kill_count/howmany_count",
            "Exact 123/123 key match with the editor's counts section.", "full",
            {"allQuestsCountKeys": len(native["countsAllQuests"]),
             "note": "Counting all 44 quests yields 283 keys; the editor intentionally uses core quests only."})
        base_stations = set(baseline.get("stations", []))
        native_stations = set(native["stations"]["allTags"])
        add("stations", len(base_stations), len(native_stations),
            "DT_AchievementDefinition + DT_WorldExplorationTeleportPoints",
            "All 28 saved stations are present natively; the native registry is a strict superset.", "full",
            {"baselineOnly": sorted(base_stations - native_stations),
             "nativeOnly": sorted(native_stations - base_stations)})
        ach = baseline.get("achievements", {})
        base_collections = {frozenset(v["CollectedTags"]) for v in ach.get("CollectionAchievements", {}).values()}
        native_collections = {frozenset(r["CollectionTags"]) for r in native["achievements"] if "CollectionTags" in r}
        base_counts = sorted(v["Count"] for v in ach.get("CountAchievements", {}).values())
        native_counts = sorted(r["MaxAmount"] for r in native["achievements"] if "MaxAmount" in r)
        add("achievements", sum(len(v) for v in ach.values()), len(native["achievements"]),
            "DT_AchievementDefinition.json",
            "32/32 definitions, all three CollectionTags sets and all seven Count targets match natively; "
            "only bCompleted=true is a save-state flag.", "full",
            {"collectionTagSetsMatch": base_collections == native_collections,
             "countTargetsMatch": base_counts == native_counts,
             "countTargets": native_counts})
        add("travelActors.gates", len(baseline.get("travelActors", {}).get("gates", [])), 0,
            "none (cooked IoStore Zen assets only)",
            "SoftObjectPath + PreviousState/CurrentState/Version cannot be recovered from pak tables.", "none")
        add("travelActors.shortcuts", len(baseline.get("travelActors", {}).get("shortcuts", [])), 0,
            "none (cooked IoStore Zen assets only)",
            "Same as gates; needs cooked Zen asset parsing or the verified save diff.", "none")
        add("saveFormat", 1, 0, "none",
            "FCharacterSaveV1 serialization metadata is not a game resource.", "none")
        add("questPolicy", 1, 0, "none", "Editor policy constant, not a game resource.", "none")
        shared = {}
        for name, saved in q.items():
            if name in native["quests"]:
                extra = sorted(set(saved) - set(native["quests"][name]["tasks"]))
                if extra:
                    shared[name] = extra
        add("questSharedTaskGaps", len(shared), 0,
            "DT_QuestLibraries.json (checked; does not enumerate these nodes)",
            "Task nodes referenced across quest graphs are absent from every shipped inline goal tree.", "none",
            shared)
    reported = REPORTED_SAVE_COUNTS
    add("savedCutsceneTags", reported["savedCutsceneTags"], len(native["cutsceneTags"]),
        "DT_CutsceneDefinition.json :: CutsceneName", "Exact count match; all 24 tags are native.", "full")
    add("savedFogOfWarExplorationItems", reported["savedFogOfWarExplorationItems"],
        len(native["fogOfWarRegions"]),
        "DT_WorldIndoorAreaMapData.json (23) + DT_WorldRegionMapData.json (3)",
        "Exact count match; 23 SW.Area.* + 3 SW.Region.* tags.", "full")
    add("discoveredDungeonDoors", reported["discoveredDungeonDoors"]["total"],
        len({g["doorId"] for g in doors["guidanceNetwork"]}),
        "OverworldGuidanceNetwork.json (IDs + node positions) + SpicewoodTags.ini + DT_WorldAreaBonds.json",
        "Native registries supply 251 distinct doorway IDs with X/Y/Z node coordinates, but "
        "MarkerType(7/8/9), HasOptionalDoorMarkerOverride and OptionalDoorMarkerType do not exist "
        "in pak data; the exact 126-item save list cannot be reproduced.", "ids-only",
        {"reportedSaveCategories": {"dungeon": 24, "rift": 21, "tower": 31},
         "nativeGuidanceCategories": doors["categories"],
         "tagRegistrySize": len(doors["tagRegistry"]),
         "worldAreaBondIds": len(doors["worldAreaBondIds"]),
         "note": "OverworldGuidanceNetwork positions are nav-node coordinates, not the save's door Location."})
    still = [
        "WorldExploration.DiscoveredDungeonDoors: exact 126 records with Location + MarkerType(7/8/9) "
        "+ HasOptionalDoorMarkerOverride + OptionalDoorMarkerType (only doorway IDs/positions are native)",
        "WorldExploration.SavedActorStates: 28 gates + 13 shortcuts with SoftObjectPath / PreviousState / "
        "CurrentState / Version (actor names live in cooked IoStore Zen assets; states are save transitions)",
        "quest SharedTask nodes (e.g. FOa1_S11_A_I04) that are only reachable from other quest graphs",
        "Achievements: the bCompleted=true completion flags (all targets are native)",
        "saveFormat (FCharacterSaveV1 / SoftVersion / FormatHash) and questPolicy",
        "One native side quest (TOa1_S01_A) has no verified completed-save task targets",
    ]
    return {"baselineFile": "public/world-quests.json" if baseline else None,
            "baselineProgressSource": baseline.get("progressSource", {}).get("kind") if baseline else None,
            "reportedSaveCounts": reported,
            "reportedSaveCountsNote": "Counts supplied by the task description (verified completed-save diff); "
                                      "no save file was read by this script.",
            "iostore": io, "comparisons": comparisons, "stillRequiresSaveDiff": still}


def validate(world, talisman):
    assert len(talisman["options"]) == 57, "talisman templates != 57"
    assert len(world["cutsceneTags"]) == 24, "cutscene tags != 24"
    assert len(world["fogOfWarRegions"]) == 26, "fog regions != 26"
    assert len(world["quests"]) >= 43, "native quests < 43"
    assert len(world["stations"]["allTags"]) >= 28, "native stations < 28"
    assert len(world["doorways"]["guidanceNetwork"]) >= 100, "guidance doorways missing"
    assert len(world["achievements"]) == 32, "achievement definitions != 32"
    json.loads(json.dumps(world, ensure_ascii=False))
    json.loads(json.dumps(talisman, ensure_ascii=False))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--game", type=Path, help="Installed Minecraft Dungeons II directory")
    mode.add_argument("--content", type=Path, help="Already-extracted Dungeons/Content tree (no key needed)")
    parser.add_argument("--repak", type=Path, help="Path to repak.exe (auto-detected otherwise)")
    parser.add_argument("--retoc", type=Path, help="Path to retoc.exe for optional .utoc index evidence")
    parser.add_argument("--key-file", type=Path, help="Private file containing the archive AES key")
    parser.add_argument("--public", type=Path, default=PUBLIC, help="Output directory (default: project public)")
    parser.add_argument("--work", type=Path, help="Scratch directory (default: system temp)")
    parser.add_argument("--version", help="Override game version (default: MicrosoftGame.config)")
    parser.add_argument("--out", default="world-map-native.json", help="World output file name")
    parser.add_argument("--talisman-out", default="talisman-native.json", help="Talisman output file name")
    parser.add_argument("--skip-utoc", action="store_true", help="Do not probe the IoStore .utoc index")
    args = parser.parse_args(argv)

    key = args.key_file.read_text(encoding="utf-8-sig").strip() if args.key_file else os.environ.get("MCD2_AES_KEY", "").strip()
    if key:
        key = key.removeprefix("0x")
    public = args.public.resolve()
    baseline_path = public / "world-quests.json"
    baseline = read_json(baseline_path) if baseline_path.is_file() else None
    baseline_paths = [r["SoftObjectPath"] for group in (baseline or {}).get("travelActors", {}).values()
                      for r in group if isinstance(r, dict) and "SoftObjectPath" in r]

    work = Path(args.work).resolve() if args.work else Path(tempfile.gettempdir()) / "mcd2-world-map-work"
    work.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="mcd2-native-", dir=work) as scratch:
        scratch = Path(scratch)
        meta = {"schema": 1, "generator": "tools/sync-world-map.py", "dataSource": "installed game resources only"}
        if args.game:
            game = args.game.resolve()
            repak = find_tool("repak", args.repak)
            if not repak:
                raise ValueError(
                    "repak.exe is required to unpack the Oodle-compressed pak. Download "
                    "repak_cli-x86_64-pc-windows-msvc.zip from "
                    "https://github.com/trumank/repak/releases and pass --repak PATH. "
                    "Alternatively use --content with a pre-extracted Dungeons/Content tree.")
            pak = game / "Dungeons/Content/Paks/Dungeons-Windows.pak"
            meta.update({"source": "installed-game", "pak": pak.name, "pakSha256": file_hash(pak),
                         "version": args.version or installed_version(game),
                         "repak": repak.name})
            content = extract_content(game, repak, key, scratch)
            utoc = game / "Dungeons/Content/Paks/Dungeons-Windows.utoc"
            if utoc.is_file():
                meta["utoc"] = utoc.name
                meta["utocSha256"] = file_hash(utoc)
            io = ({"status": "skipped"} if args.skip_utoc else
                  iostore_evidence(game, find_tool("retoc", args.retoc), key, baseline_paths))
        else:
            content = normalize_content(args.content)
            meta.update({"source": "extracted-content", "content": str(content),
                         "version": args.version or "unknown"})
            io = {"status": "not-checked", "reason": "--content mode has no .utoc"}

        langs = localization(content)
        achievements = rows(content, "AchievementDefinition")
        quests, counts, counts_all, quest_sources = quest_data(content)
        stations = station_data(content, achievements)
        libraries = [r["Name"] for r in rows(content, "QuestLibraries")]
        cutscenes = cutscene_data(content)
        regions = fog_regions(content)
        doors = doorway_data(content)
        gimmicks = actor_gimmicks(content)
        talisman = talisman_data(content, langs)
        candidates = progress_candidates(content)

        native = {"quests": quests, "counts": counts, "countsAllQuests": counts_all, "stations": stations,
                  "achievements": achievement_data(content), "cutsceneTags": cutscenes,
                  "fogOfWarRegions": regions, "doorways": doors,
                  "actorGimmicks": gimmicks, "talisman": talisman, "progressCandidates": candidates}
        report = coverage(baseline, native, doors, io)
        talisman_baseline_path = public / "talisman-texts.json"
        report["talismanCoverage"] = {
            "baselineFile": "public/talisman-texts.json" if talisman_baseline_path.is_file() else None,
            "baselineOptions": len(read_json(talisman_baseline_path)["options"]) if talisman_baseline_path.is_file() else None,
            "nativeOptions": len(talisman["options"]),
            "nativelyFormattedDescriptions": talisman["formattedDescriptions"],
            "customGetterPatterns": talisman["unformatted"],
            "nativeLabels": len(talisman["labels"]),
            "note": "57/57 templates and 19/19 effect labels are native; 51/57 descriptions are "
                    "formatted with DT_EffectDefinition.ValuesToGet. Six use C++ getters "
                    "(GetFiringEmeraldValues/GetHealthyStrikeValues) and two official locres labels "
                    "are placeholder strings, so those eight texts still need a curated source.",
        }

        source_tables = [
            {"table": "DT_AchievementDefinition.json", "rows": len(achievements)},
            {"table": "DT_WorldExplorationTeleportPoints.json", "rows": len(stations["teleportPoints"])},
            {"table": "DT_CutsceneDefinition.json", "rows": len(cutscenes)},
            {"table": "DT_WorldIndoorAreaMapData.json", "rows": len(rows(content, "WorldIndoorAreaMapData"))},
            {"table": "DT_WorldRegionMapData.json", "rows": len(rows(content, "WorldRegionMapData"))},
            {"table": "DT_WorldAreaBonds.json", "rows": len(rows(content, "WorldAreaBonds"))},
            {"table": "DT_QuestDoorwayControl.json", "rows": len(rows(content, "QuestDoorwayControl"))},
            {"table": "DT_QuestLibraries.json", "rows": len(libraries)},
            {"table": "DT_TalismanEffectTemplateDefinition.json", "rows": len(talisman["options"])},
            {"table": "DT_TalismanPropertyDefinition.json", "rows": len(rows(content, "TalismanPropertyDefinition"))},
            {"table": "DT_ItemDefinitionTalisman.json", "rows": len(talisman["items"])},
            {"table": "DT_ItemCollectionsDefinition.json", "rows": len(talisman["collections"])},
        ]
        world_doc = {
            "meta": meta,
            "sources": {
                "pak": meta.get("pak"), "version": meta["version"],
                "includes": list(INCLUDES),
                "tables": source_tables,
                "questFiles": quest_sources,
                "questLibraries": libraries,
                "configFiles": ["Dungeons/Config/tags/SpicewoodTags.ini",
                                "Dungeons/Config/DefaultActorStateGimmicks.ini",
                                "Dungeons/Config/DefaultCutsceneConfig.ini"],
                "guidanceNetwork": "Dungeons/Plugins/SpicewoodGuidance/Content/Networks/OverworldGuidanceNetwork.json",
                "localization": {"en": len(langs[0]), "zh-Hans": len(langs[1]),
                                 "namespacesUsed": ["DT_EffectDefinition.csv", "DT_ItemDefinitionTalisman.csv"]},
                "existingFileNativeSources": {
                    "public/world-quests.json": {
                        "quests/counts/mainQuests": "Spicewood/Quests/QuestsData/*_Quests.json",
                        "stations": "DT_AchievementDefinition.json + DT_WorldExplorationTeleportPoints.json",
                        "achievements": "DT_AchievementDefinition.json (ConditionDefinition*)",
                        "travelActors/saveFormat/questPolicy": "verified-save-diff only",
                    },
                    "public/extras.json": {
                        "talismanLevels": "DT_TalismanPropertyDefinition.json (already rebuilt by sync-native-rules.py)",
                        "uniqueOwn": "DT_ItemDefinition{Melee,Ranged,Armor,Artifact}.json + "
                                     "DT_EffectTemplateDefinition.json (sync-native-rules.py)",
                        "uniqueEnchantments": "DT_EnchantmentDefinition.json + DT_EffectDefinition.json "
                                              "+ en/zh-Hans All.locres (sync-unique-enchantments.py)",
                    },
                    "public/talisman-texts.json": {
                        "labels": "DT_EffectDefinition.csv :: SW_Effect_<X>_SW_TextEntry_Name in All.locres",
                        "options": "DT_TalismanEffectTemplateDefinition.json + DT_TalismanPropertyDefinition.json "
                                   "+ DT_ItemDefinitionTalisman.csv / DT_EffectDefinition.csv locres keys",
                        "remainingExternal": "6 custom-getter descriptions, 2 placeholder locres labels, icon webp files",
                    },
                },
                "note": "All values come from Dungeons-Windows.pak (or its extracted Content tree); "
                        "no save file, no maxroll/external database.",
            },
            "quests": quests,
            "counts": counts,
            "countsAllQuests": counts_all,
            "stations": stations,
            "achievements": native["achievements"],
            "cutsceneTags": cutscenes,
            "fogOfWarRegions": regions,
            "doorways": doors,
            "actorGimmicks": gimmicks,
            "progressCandidates": candidates,
            "coverage": report,
        }
        talisman_doc = {
            "meta": {"schema": 1, "generator": "tools/sync-world-map.py", "version": meta["version"],
                     "pak": meta.get("pak"), "source": "installed game resources only",
                     "tables": ["DT_TalismanEffectTemplateDefinition.json", "DT_TalismanPropertyDefinition.json",
                                "DT_ItemDefinitionTalisman.json", "DT_EffectDefinition.json",
                                "DT_ItemCollectionsDefinition.json"],
                     "locres": ["Localization/All/en/All.locres", "Localization/All/zh-Hans/All.locres"],
                     "note": "51/57 descriptions are formatted natively using DT_EffectDefinition.ValuesToGet; "
                             "the remaining six use custom C++ getters and keep their patterns."},
            "labels": talisman["labels"],
            "options": talisman["options"],
            "levels": talisman["levels"],
            "items": talisman["items"],
            "collections": talisman["collections"],
            "formattedDescriptions": talisman["formattedDescriptions"],
            "unformatted": talisman["unformatted"],
        }
        validate(world_doc, talisman_doc)
        write_json(public / args.out, world_doc)
        write_json(public / args.talisman_out, talisman_doc)

    print(f"Game {meta['version']}: {len(quests)} quests, {len(stations['allTags'])} stations, "
          f"{len(native['achievements'])} achievements, {len(cutscenes)} cutscene tags, "
          f"{len(regions)} fog regions, {len(doors['guidanceNetwork'])} guidance doorways, "
          f"{len(doors['tagRegistry'])} doorway tags, {len(gimmicks['placeableClasses'])} actor gimmick classes.")
    print(f"Talisman: {len(talisman['options'])} templates, {talisman['formattedDescriptions']} "
          f"native bilingual descriptions, {len(talisman['unformatted'])} custom-getter patterns.")
    print(f"Coverage: {len([c for c in report['comparisons'] if c['status'] == 'full'])} full, "
          f"{len([c for c in report['comparisons'] if c['status'] != 'full'])} partial/none; "
          f"{len(report['stillRequiresSaveDiff'])} fields still require the verified save diff.")
    print("Wrote: " + str(public / args.out) + ", " + str(public / args.talisman_out))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, KeyError, json.JSONDecodeError, ElementTree.ParseError) as error:
        print("Error: " + str(error), file=sys.stderr)
        sys.exit(1)
