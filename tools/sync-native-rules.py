"""Verify or rebuild inventory rules using only an extracted game's UFS JSON tables.

Usage: python tools/sync-native-rules.py <Dungeons/Content> [--write]
"""
import argparse
from itertools import accumulate
import json
from pathlib import Path
import re


def read(path):
    return json.loads(path.read_bytes())


def tags(group):
    return [x["TagName"] for x in group.get("GameplayTags", [])]


def native_rules(content):
    tables = content / "Spicewood/Core/DataTables/UFS"

    def rows(name):
        return read(tables / f"DT_{name}.json")

    def indexed(*names):
        return {r["TypeTag"]["TagName"]: r for name in names for r in rows(name)}

    def fixed(template, templates):
        spec = templates[template]["TemplateData"]
        if not spec["HasFixedEffectValue"] or spec["Effect"]["TagName"] == "None":
            raise ValueError(f"Unsupported non-fixed template: {template}")
        return spec["Effect"]["TagName"], spec["FixedEffectValue"]

    templates = indexed("EffectTemplateDefinition", "EnchantmentDefinition")
    own = {}
    for name in ("Melee", "Ranged", "Armor", "Artifact"):
        for row in rows("ItemDefinition" + name):
            item = row["TypeTag"]["TagName"]
            native = tags(row.get("Effects", {}))
            if not native:
                continue
            if len(native) != 1 or item in own:
                raise ValueError(f"Multiple fixed templates on {item}: {native}")
            template, = native
            effect, value = fixed(template, templates)
            own[item] = {"effect": effect, "strength": value, "template": template}

    talismans = {}
    xp_costs = set()
    templates = indexed("TalismanEffectTemplateDefinition")
    for row in rows("TalismanPropertyDefinition"):
        levels = row["ItemLevels"].get("Levels", [])
        if not levels:
            continue  # the abstract BaseTalisman supplies no progression
        item = row["TypeTag"]["TagName"]
        actual = [level["Level"]["TagName"] for level in levels]
        if actual != [f"SW.Item.Property.Level.{i+1}" for i in range(len(levels))]:
            raise ValueError(f"Unexpected progression order: {item}")
        if levels[-1]["XPRequiredForNextLevel"] != 0:
            raise ValueError(f"Final level of {item} requires XP")
        xp_costs.add(tuple(level["XPRequiredForNextLevel"] for level in levels[:-1]))
        progression = talismans[item] = []
        for level in levels:
            effects = []
            for template in tags(level.get("Effects", {})):
                effect, strength = fixed(template, templates)
                # The game writes these defaults on newly generated, unenchanted items.
                effects.append({"TypeTag": effect, "Intensity": strength, "Quality": 0,
                                "EnchantmentPointsInvested": 0, "GeneratorData": {
                                    "GeneratorParentTemplate": template, "Locked": False}})
            progression.append({"LevelEffects": effects, "LevelTags": tags(level.get("GrantedTags", {}))})
    if not own or not talismans or len(xp_costs) != 1:
        raise ValueError("Incomplete data or talismans no longer have a shared XP curve")

    balance = indexed("GameBalanceDefinition")
    active = balance["SW.GameplayRuleSet.Active"]
    progression_rules, = [balance[t]["LevelProgressionConstants"]["EconomyProgression"] for t in
                          [active["TypeTag"]["TagName"], *tags(active["Traits"])] if t in balance
                          and balance[t]["LevelProgressionConstants"].get("EconomyProgression")]
    player, = [r for r in rows("PlayerDefinition") if r["Name"] == "DefaultPlayer"]
    attributes = {a["Attribute"]["TagName"]: a["Value"] for a in player["AttributeValues"]}
    limits = {key: attributes["SW.Attribute." + key + "Max"] for key in
              ("Level", "Emeralds", "SpringStone", "EnchantmentPoints", "VillageMerchantRefreshCharges")}
    # The highest configured upgrade for each merchant in the active economy progression.
    for target, column in [("VillageMerchantUpgradeLevel", "UpgradeLevelMerchant"),
                           ("EnchantsmithUpgradeLevel", "UpgradeLevelEnchantsmith"),
                           ("OldBlacksmithUpgradeLevel", "UpgradeLevelBlacksmith")]:
        limits[target] = max(step[column] for step in progression_rules.values())

    cost_map, = [entry["EnchantCostMap"] for ability in player["Abilities"]
                 if ability["Ability"] == "/Script/InventorySystem.GA_ItemEnchant"
                 for entry in ability["InstanceData"] if "EnchantCostMap" in entry]
    points = {}
    for key, rule in cost_map.items():
        match = re.fullmatch(r'\(TagName="SW\.Rarity\.(\w+)"\)', key)
        if not match:
            raise ValueError(f"Unexpected enchant rarity: {key}")
        base, delta = rule["EnchantmentPointCost"], rule["EnchantmentPointAdditionalCostPerLevel"]
        # The save stores total invested points, not the price of the latest tier.
        points[match[1]] = list(accumulate(base + i * delta for i in range(3)))
    if not points:
        raise ValueError("Empty enchantment price schedule")
    meta = {"maxEffects": active["ItemCreatorConstants"]["NumberOfEffectsMax"],
            "talismanXp": list(next(iter(xp_costs))), "enchantPoints": points, "heroMaxStats": limits}
    return {"uniqueOwn": own, "talismanLevels": talismans}, meta


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("content", type=Path)
    parser.add_argument("--public", type=Path, default=Path(__file__).resolve().parents[1] / "public")
    parser.add_argument("--write", action="store_true", help="Replace the generated fields in place")
    args = parser.parse_args()
    extras, meta = native_rules(args.content)
    changes = []
    for file, key, updates in [("extras.json", None, extras), ("catalog.json", "meta", meta)]:
        path = args.public / file
        document = read(path) if path.is_file() else {}
        node = document.setdefault(key, {}) if key else document
        for field, value in updates.items():
            if node.get(field) != value:
                changes.append(f"{file}:{field}")
            node[field] = value
        if args.write:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(json.dumps(document, ensure_ascii=False, separators=(",", ":")).encode("utf8"))
    print(f"{len(extras['uniqueOwn'])} fixed item effects, {len(extras['talismanLevels'])} talismans, "
          f"{sum(map(len, meta['enchantPoints'].values()))} enchantment prices, "
          f"{len(meta['heroMaxStats'])} hero attributes.")
    if changes:
        print(("Updated: " if args.write else "Mismatch: ") + ", ".join(changes))
    if changes and not args.write:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
