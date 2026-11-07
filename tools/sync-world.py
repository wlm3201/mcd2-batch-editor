"""Build native quest/station lists and merge verified save-diff transitions."""
import argparse
import json
from pathlib import Path


def merge_save_profile(world, profile=None):
    """Carry verified save transitions through a native resource rebuild."""
    if profile is None:
        path = Path(__file__).resolve().parents[1] / "data/world-actions.json"
        if not path.is_file():
            return world
        profile = json.loads(path.read_bytes())
    if profile.get("schema") != 1:
        raise ValueError("Unsupported world-operation save-diff profile")
    result = json.loads(json.dumps(world))
    # Completed-save evidence also contains shared task nodes referenced from
    # other quest graphs; the inline goal tree alone does not enumerate them.
    for name in result["mainQuests"]:
        result["quests"][name] = list(dict.fromkeys([
            *result["quests"][name], *profile["quests"].get(name, [])]))
    for name in result.get("sideQuests", []):
        if name not in result["mainQuests"]:
            result["quests"].pop(name, None)
    result["sideQuests"] = list(profile["sideQuests"])
    for name in result["sideQuests"]:
        result["quests"][name] = profile["quests"][name]
    result["stations"] = list(dict.fromkeys([*world["stations"], *profile["stations"]]))
    for field in ("questPolicy", "travelActors", "achievements", "saveFormat"):
        result[field] = profile[field]
    result["progressSource"] = {"kind": "verified-save-diff", "sources": profile["sources"]}
    return result


def world_data(content):
    read = lambda p: json.loads(p.read_bytes())
    spice = content / "Spicewood"
    quests, counts = {}, {}
    for file in sorted((spice / "Quests/QuestsData").glob("*_Quests.json")):
        for quest in read(file)["Quests"]:
            if quest["quest_type"] != "CoreQuest":
                continue
            name = quest["id"]
            if name in quests:
                raise ValueError("Duplicate core quest " + name)
            steps = []
            def visit(goal):
                steps.append(goal["name"])
                for key in ("kill_count", "howmany_count"):
                    if goal.get(key, 0) > 0:
                        counts[goal["name"]] = goal[key]
                for child in goal.get("subgoals", []):
                    visit(child)
            visit(quest["goals"])
            quests[name] = list(dict.fromkeys(steps[1:] + steps[:1]))
    tables = spice / "Core/DataTables/UFS"
    achievement, = [r for r in read(tables / "DT_AchievementDefinition.json")
                    if r["Name"] == "DISCOVER_ALL_MINECART_STATIONS"]
    stations = [t["TagName"] for t in achievement["Condition"]["CollectionTags"]["GameplayTags"]]
    destinations = {r["ActorTag"]["TagName"] for r in read(tables / "DT_WorldExplorationTeleportPoints.json")}
    if not quests or not stations or len(set(stations)) != len(stations) or not set(stations) <= destinations:
        raise ValueError("Incomplete or inconsistent native world tables")
    return merge_save_profile({"quests": quests, "counts": counts, "mainQuests": sorted(quests), "stations": stations})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("content", type=Path)
    parser.add_argument("--public", type=Path, default=Path(__file__).resolve().parents[1] / "public")
    args = parser.parse_args()
    args.public.mkdir(parents=True, exist_ok=True)
    out = args.public / "world-quests.json"
    out.write_bytes(json.dumps(world_data(args.content), separators=(",", ":")).encode())
