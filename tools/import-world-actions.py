"""Import verified world-operation targets from an ordered set of save diffs.

Only quest/task identities, travel actor states and achievement targets are kept;
character metadata, inventory and unrelated world data are never imported.
"""
import argparse
from hashlib import sha256
import importlib.util
import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile


ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def changed_paths(before, after, path=""):
    if isinstance(before, dict) and isinstance(after, dict):
        result = set()
        for key in before.keys() | after.keys():
            child = path + "/" + key
            if key not in before or key not in after:
                result.add(child)
            else:
                result.update(changed_paths(before[key], after[key], child))
        return result
    return set() if before == after else {path}


def select(files, predicate):
    matches = [file for file in files if predicate(file.stem)]
    if len(matches) != 1:
        raise ValueError("The save folder must contain one unambiguous file for each operation")
    return matches[0]


def quest_map(body):
    result = {}
    for quest in body["quest"]["Quests"]:
        name = quest["QuestName"]
        tasks = quest["TaskData"]
        if name in result or len({task["TaskName"] for task in tasks}) != len(tasks):
            raise ValueError("Duplicate quest or task identity: " + name)
        if any(set(task) != {"TaskName", "State", "PartialProgress"} for task in tasks):
            raise ValueError("Review the new task save layout before importing it")
        result[name] = quest
    return result


def build_profile(directory):
    files = sorted(directory.glob("*.sav"))
    selected = {name: select(files, lambda stem, prefix=prefix: stem.startswith(prefix))
                for name, prefix in (("beforeStations", "2"), ("stations", "3"), ("main", "4"),
                                     ("available", "5"), ("side", "6"), ("achievements", "7"))}
    selected["gates"] = select(files, lambda stem: "\u5927\u95e8" in stem)
    selected["shortcuts"] = select(files, lambda stem: "\u6377\u5f84" in stem)
    payloads = {name: file.read_bytes() for name, file in selected.items()}
    docs = {name: json.loads(payload) for name, payload in payloads.items()}
    formats = [doc["SerializeMeta"] for doc in docs.values()]
    if any(value != formats[0] for value in formats) or formats[0]["HardFormat"] != "FCharacterSaveV1":
        raise ValueError("All diff saves must use the same verified character save format")
    bodies = {name: doc["CharacterSaveV1"] for name, doc in docs.items()}
    allowed = {
        ("beforeStations", "stations"): {"/WorldExploration/DiscoveredMinecartStationTags"},
        ("stations", "main"): {"/quest/Quests"},
        ("main", "available"): {"/quest/Quests"},
        ("available", "side"): {"/quest/Quests", "/quest/FocusedQuestId"},
        ("side", "achievements"): {"/Achievements"},
        ("achievements", "gates"): {"/WorldExploration/SavedActorStates"},
        ("achievements", "shortcuts"): {"/WorldExploration/SavedActorStates"},
    }
    for (before, after), paths in allowed.items():
        changes = changed_paths(bodies[before], bodies[after])
        if not changes or any(not any(path == scope or path.startswith(scope + "/") for scope in paths)
                              for path in changes):
            raise ValueError(f"Unrelated or missing changes in {before} -> {after}: {sorted(changes)}")
    main, available, completed = (quest_map(bodies[name]) for name in ("main", "available", "side"))
    main_ids = [name for name, quest in main.items() if quest["State"] == "Completed"]
    side_ids = [name for name, quest in available.items() if name not in main_ids]
    if not main_ids or not side_ids or set(available) != set(completed):
        raise ValueError("Incomplete main/side quest diff pair")
    for name in main_ids:
        if main[name] != available[name] or available[name] != completed[name]:
            raise ValueError("Side quest actions changed a completed main quest: " + name)
    for name, quest in available.items():
        desired = "Completed" if name in main_ids else "NotSet"
        if quest["State"] != ("Completed" if name in main_ids else "Available"):
            raise ValueError("Unexpected available quest state: " + name)
        if any(task["State"] != desired or task["PartialProgress"] != 0 for task in quest["TaskData"]):
            raise ValueError("Review the new quest task transition: " + name)
        finished = completed[name]
        if finished["State"] != "Completed" or any(task["State"] != "Completed" or task["PartialProgress"] != 0
                                                    for task in finished["TaskData"]):
            raise ValueError("Incomplete side quest target: " + name)
        if [task["TaskName"] for task in quest["TaskData"]] != [task["TaskName"] for task in finished["TaskData"]]:
            raise ValueError("Quest completion replaced task identities: " + name)
    actors = {}
    for kind in ("gates", "shortcuts"):
        before = {row["SoftObjectPath"]: row for row in bodies["achievements"]["WorldExploration"]["SavedActorStates"]}
        rows = bodies[kind]["WorldExploration"]["SavedActorStates"]
        targets = [row for row in rows if before.get(row["SoftObjectPath"]) != row]
        if not targets or len({row["SoftObjectPath"] for row in targets}) != len(targets):
            raise ValueError("Missing or duplicate travel actor identities")
        if any(set(row) != {"SoftObjectPath", "PreviousState", "CurrentState", "Version"} for row in targets):
            raise ValueError("Review the new actor-state save layout")
        if any(not isinstance(row["SoftObjectPath"], str) or not row["SoftObjectPath"]
               or any(type(row[field]) is not int or row[field] < 0 for field in ("PreviousState", "CurrentState", "Version"))
               for row in targets):
            raise ValueError("Invalid travel actor state values")
        actors[kind] = targets
    all_paths = [row["SoftObjectPath"] for rows in actors.values() for row in rows]
    if len(set(all_paths)) != len(all_paths):
        raise ValueError("Gate/shortcut targets overlap; review their states")
    achievements = bodies["achievements"]["Achievements"]
    if set(achievements) != {"QuestAchievements", "BoolAchievements", "CollectionAchievements", "CountAchievements"}:
        raise ValueError("Review the new achievement save layout")
    for kind, entries in achievements.items():
        for name, target in entries.items():
            field = "Count" if kind == "CountAchievements" else "CollectedTags" if kind == "CollectionAchievements" else "bCompleted"
            if set(target) != {field}:
                raise ValueError("Unexpected achievement target fields: " + name)
            value = target[field]
            if (field == "bCompleted" and value is not True or field == "Count" and (type(value) is not int or value <= 0)
                    or field == "CollectedTags" and (not isinstance(value, list) or not value or len(set(value)) != len(value))):
                raise ValueError("Incomplete achievement target: " + name)
            if field == "CollectedTags" and any(not isinstance(tag, str) or not tag for tag in value):
                raise ValueError("Invalid achievement collection tags: " + name)
    stations = bodies["stations"]["WorldExploration"]["DiscoveredMinecartStationTags"]
    if (not isinstance(stations, list) or not stations or any(not isinstance(tag, str) or not tag for tag in stations)
            or len(set(stations)) != len(stations)):
        raise ValueError("Invalid station discovery targets")
    return {
        "schema": 1,
        "saveFormat": formats[0],
        "sources": {name: {"file": file.name, "sha256": sha256(payloads[name]).hexdigest()} for name, file in selected.items()},
        "mainQuests": main_ids,
        "sideQuests": side_ids,
        "quests": {name: [task["TaskName"] for task in quest["TaskData"]] for name, quest in available.items()},
        "questPolicy": {"completedPartialProgress": 0, "availableTaskState": "NotSet"},
        "stations": stations,
        "travelActors": actors,
        "achievements": achievements,
    }


def write_atomic(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = NamedTemporaryFile(dir=path.parent, delete=False)
    try:
        with temp:
            temp.write(payload)
        os.replace(temp.name, path)
    finally:
        Path(temp.name).unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--saves", type=Path, required=True)
    parser.add_argument("--profile", type=Path, default=ROOT / "data/world-actions.json")
    parser.add_argument("--public", type=Path, default=ROOT / "public")
    args = parser.parse_args()
    profile = build_profile(args.saves)
    spec = importlib.util.spec_from_file_location("sync_world", Path(__file__).with_name("sync-world.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    world_path = args.public / "world-quests.json"
    world = module.merge_save_profile(read(world_path), profile)
    write_atomic(args.profile, (json.dumps(profile, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    write_atomic(world_path, json.dumps(world, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    print(f"Imported {len(profile['mainQuests'])} main quests, {len(profile['sideQuests'])} side quests, "
          f"{len(profile['stations'])} stations, {sum(map(len, profile['travelActors'].values()))} actor states, "
          f"{sum(map(len, profile['achievements'].values()))} achievements")


if __name__ == "__main__":
    main()
