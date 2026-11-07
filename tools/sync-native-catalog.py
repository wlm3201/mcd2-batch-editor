"""Rebuild the editor's bilingual inventory and effect catalog from an extracted Dungeons/Content.
Reads UFS and two official locres files. --defer-icons records original texture
references without requiring any previous output. The legacy single-step mode
can reuse fingerprinted textures, bound by their complete Unreal references.
"""
import argparse
from collections import defaultdict
from hashlib import sha256
import importlib.util
from pathlib import Path
import re


def sibling(name):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


source = sibling("sync-game-data")
dynamic_args = sibling("sync-unique-enchantments").dynamic_args
ITEM_TABLES = {
    "ItemDefinitionArmor": "armor", "ItemDefinitionArtifact": "artifact",
    "ItemDefinitionMelee": "melee", "ItemDefinitionRanged": "ranged",
    "ItemDefinitionEnchantmentBook": "book", "ItemDefinitionTalisman": "talisman",
    "ItemDefinitionPet": "pet", "ItemDefinitionCape": "cape",
    "ItemDefinitionThrowable": "throwable", "FoodDefinition": "food", "QuestItemDefinition": "quest",
}
RANKS = ("I", "II", "III")
TIER_TRAITS = dict(zip(["SW.EffectTemplate.Tier" + t for t in ("1", "2", "3", "Unique")], (*RANKS, "Unique")))
SLOTS = {"MeleeWeapon": "melee-weapon", "RangedWeapon": "ranged-weapon",
         **{"Armor." + part: "armor-" + part.lower() for part in ("Helmet", "Chest", "Leggings", "Boots")}}
GROUP_PREFIX = "SW.EffectTemplateGroup."
SLOT_PROFILES = {
    "melee": {"SW.Item.Property.MeleeWeapon"},
    "bow": {"SW.Item.Property.RangedWeapon", "SW.Item.Property.Bow"},
    "crossbow": {"SW.Item.Property.RangedWeapon", "SW.Item.Property.Crossbow"},
    "armor": {"SW.Item.Property.Armor"},
    "artifact": {"SW.Item.Property.Artifact"},
    "quiver": {"SW.Item.Property.Artifact", "SW.Item.Artifact.Quiver"},
}


def template_slots(traits, queries):
    # Describe the template's native incompatibility queries using the standard
    # equipment tag combinations; do not infer a slot from the effect's name.
    return [slot for slot, item_tags in SLOT_PROFILES.items()
            if not any(source.incompatible(queries[t], item_tags) for t in traits & queries.keys())]


def tags(row, field):
    return [x["TagName"] for x in row.get(field, {}).get("GameplayTags", [])]


def inherited(tag, definitions):
    found, todo = set(), [tag]
    while todo:
        current = todo.pop()
        if current not in found:
            found.add(current)
            todo.extend(source.tag_set(definitions.get(current, {})) - found)
    return found


class Tables:
    def __init__(self, content, public=source.PUBLIC, defer_icons=False):
        self.root = content / "Spicewood/Core/DataTables/UFS"
        self.langs = [source.localization(content / f"Localization/All/{lang}/All.locres")
                      for lang in ("en", "zh-Hans")]
        self.defer_icons = defer_icons
        self.art = {}
        catalog_path = public / "catalog.json"
        if not defer_icons and catalog_path.is_file():
            cached = source.read_json(catalog_path)
            checked = set()
            for category in ("items", "effects", "enchantments"):
                for entry in cached.get(category, {}).values():
                    ref, name = entry.get("iconSource"), entry.get("icon")
                    if not ref or not name:
                        continue
                    if not re.fullmatch(r"[A-Za-z0-9_-]+\.([a-f0-9]{12})\.webp", name):
                        raise ValueError(f"Invalid cached texture filename: {name}")
                    if name not in checked:
                        file = public / "icons" / name
                        if file.is_symlink() or sha256(file.read_bytes()).hexdigest()[:12] != name.split(".")[-2]:
                            raise ValueError(f"Invalid texture fingerprint: {name}")
                        checked.add(name)
                    if ref in self.art and self.art[ref] != name:
                        raise ValueError(f"Ambiguous cached texture reference: {ref}")
                    self.art[ref] = name

    def rows(self, name):
        rows = source.read_json(self.root / f"DT_{name}.json")
        result = {}
        for row in rows:
            tag = row["TypeTag"]["TagName"]
            if tag in result:
                raise ValueError(f"Duplicate TypeTag in {name}: {tag}")
            result[tag] = row
        return result

    def text(self, row, key, parent=None):
        field = f'(TagName="SW.TextEntry.{key}")'
        def get(r):
            return r.get("TypeTextData", {}).get("Texts", {}).get(field)
        entry = get(row) or get(parent or {})
        if not entry:
            return "", ""
        loc = re.fullmatch(r'LOCTABLE\("([^"]+)", "([^"]+)"\)', entry["Text"])
        if not loc:
            raise ValueError(f"Unsupported localization reference: {entry['Text']}")
        texts = [lang[loc.groups()] for lang in self.langs]
        if any("{" in text for text in texts):
            args = dynamic_args(row, parent or row, entry)
            texts = [text.format(*args) for text in texts]
        return tuple(texts)

    def art_for(self, row):
        ref = row.get("IconReference")
        if not ref or ref == "None":
            return {"icon": None}
        if not isinstance(ref, str):
            raise ValueError(f"Invalid IconReference: {ref}")
        if self.defer_icons:
            return {"icon": None, "iconSource": ref}
        if ref not in self.art:
            raise ValueError(f"Texture has not been decoded: {ref}. Use --defer-icons for a full refresh.")
        return {"icon": self.art[ref], "iconSource": ref}

    def native_labels(self):
        labels = {"pools": {}, "categories": {}}
        for path in sorted(self.root.glob("*.json")):
            rows = source.read_json(path)
            if not isinstance(rows, list):
                continue
            for row in rows:
                if not isinstance(row, dict):
                    continue
                tag = row.get("TypeTag", {}).get("TagName", "")
                if tag.startswith(GROUP_PREFIX):
                    family, key = "pools", tag.removeprefix(GROUP_PREFIX)
                elif tag.startswith("SW.Archetype."):
                    family, key = "pools", "Archetype." + tag.removeprefix("SW.Archetype.")
                elif tag.startswith("SW.EffectCategory."):
                    family, key = "categories", tag.removeprefix("SW.EffectCategory.").lower()
                else:
                    continue
                en, zh = self.text(row, "Name")
                if not en or not zh or zh.startswith("TextRelease"):
                    continue
                value = {"en": en, "zh": zh}
                if key in labels[family] and labels[family][key] != value:
                    raise ValueError(f"Conflicting native label for {tag}")
                labels[family][key] = value
        return labels


def members(group):
    for t in group.get("Tags", []):
        if t["Operation"] not in ("Set", "Multiply"):
            raise ValueError(f"Unsupported effect group operation: {t}")
        if t["Weight"] > 0:
            yield t["TypeTag"]["TagName"]


def unique(values, key):
    v = set(values)
    if len(v) != 1:
        raise ValueError(f"Expected one value for {key}: {v}")
    return v.pop()


def items_for(db, templates, zh):
    groups = db.rows("EffectTemplateGroupDropTableDefinition")
    by_kind = {kind: db.rows(table) for table, kind in ITEM_TABLES.items()}
    all_rows = db.rows("ItemDefinition")
    for rows in by_kind.values():
        all_rows.update(rows)
    substitution = {tag: row["UniqueSubstitutionData"]["UniqueSubstitution"]["TagName"]
                    for tag, row in all_rows.items() if "UniqueSubstitutionData" in row
                    and row["UniqueSubstitutionData"]["UniqueSubstitution"]["TagName"] != "None"}
    base = {v: k for k, v in substitution.items()}
    queries = {k: v["TemplateData"]["IncompatibleTagsQuery"] for k, v in templates.items()
               if "IncompatibleTagsQuery" in v["TemplateData"]}
    result, books, own = {}, {}, set()
    for kind, rows in by_kind.items():
        for tag, row in rows.items():
            name, cn = db.text(row, "Name")
            # Exclude abstract/incomplete/placeholder item definitions using the game's own localization.
            if not name or not cn or cn.startswith("TextRelease"):
                continue
            zh["items"].setdefault(name, cn)
            traits = inherited(tag, all_rows)
            pools = set()
            for k in traits & groups.keys():
                for field in ("PrimaryETG", "SecondaryETG"):
                    pools.update(v.removeprefix(GROUP_PREFIX) for v in members(groups[k][field]))
            # Catalog keys use an uppercase namespace; saves retain e.g. sw.Item.Talisman.Llama.
            key = "SW." + tag.split(".", 1)[1]
            zh["itemsById"][key] = cn
            rec = result[key] = {"id": key, "name": name, "kind": kind, **db.art_for(row),
                                 "unique": "SW.Item.Property.Unique" in traits, "base": base.get(tag, tag),
                                 "classes": sorted(t.removeprefix("SW.Archetype.") for t in traits
                                                   if t.startswith("SW.Archetype.")),
                                 "pools": sorted(pools)}
            if key != tag:
                rec["saveId"] = tag
            if tag in substitution:
                rec["uniqueId"] = substitution[tag]
            if kind == "armor":
                rec["slot"] = unique((v.rsplit(".", 1)[1].lower() for v in traits
                                      if v.startswith("SW.Item.Property.Armor.")), tag)
            if kind in ("armor", "melee", "ranged", "artifact"):
                rec["blockedRollTypes"] = sorted(k.rsplit(".", 1)[1] for k, query in queries.items()
                                                 if source.incompatible(query, traits))
                own.update(tags(row, "Effects"))
            if kind == "book":
                first = unique((v["GameplayTag"]["TagName"] for v in row["KeyValues"]
                                if v["TypeTag"]["TagName"] == "SW.KeyValue.AssociatedEnchantment"), tag)
                books[first.casefold()] = row
    return dict(sorted(result.items())), books, own, queries


def label(db, tag, row, zh):
    name, cn = db.text(row, "Name")
    if not (name and cn):
        raise ValueError(f"Missing name: {tag}")
    category = unique((v.split(".")[-1].lower() for v in source.tag_set(row)
                       if v.startswith("SW.EffectCategory.")), tag)
    zh["effects"].setdefault(name, cn)
    zh["effectsById"][tag] = cn
    return {"id": tag, "name": name, "category": category, **db.art_for(row), "tiers": []}


def effects_for(db, templates, queries, own, zh, fixed_text):
    definitions = db.rows("EffectDefinition")
    template_groups = defaultdict(set)
    for group, row in db.rows("EffectTemplateGroupDefinition").items():
        for member in members(row["TagList"]):
            template_groups[member].add(group.removeprefix(GROUP_PREFIX))
    # Keep names and art for named effects even if this build has no rollable template.
    # Older/imported saves may still reference one in a static effect batch.
    out = {tag: label(db, tag, row, zh) for tag, row in definitions.items()
           if all(db.text(row, "Name"))}
    for tag, row in sorted(templates.items()):
        data = row["TemplateData"]
        effect = data["Effect"]["TagName"]
        if effect == "None":
            continue  # type rules and tier markers, not actual effects
        if not data["HasFixedEffectValue"]:
            raise ValueError(f"Unexpected variable gear effect: {tag}")
        parent = definitions[effect]
        traits = source.tag_set(row)
        rank = unique((TIER_TRAITS[t] for t in traits & TIER_TRAITS.keys()), tag)
        # Some fixed .Unique templates inherit Tier3's trait but are not the
        # rerollable .III template. Keep their ID, description and intensity together.
        if tag.endswith(".Unique"):
            if template_groups[tag]:
                raise ValueError(f"Unexpected roll group for unique template: {tag}")
            rank = "Unique"
        en, cn = db.text(row, "Description", parent)
        if not (en and cn):
            raise ValueError(f"Missing description: {tag}")
        out[effect]["tiers"].append({"template": tag, "tier": rank, "kind": "gear",
                                     "intensity": data["FixedEffectValue"], "text": en,
                                     "groups": sorted(template_groups[tag]),
                                     "slots": template_slots(traits, queries),
                                     "rollTypes": sorted(v.rsplit(".", 1)[1] for v in traits & queries.keys())})
        zh["templates"][tag] = cn
        if tag in own:
            fixed_text[tag] = cn
    return dict(sorted(out.items()))


def enchants_for(db, books, own, zh, fixed_text):
    definitions = db.rows("EnchantmentDefinition")
    actual = {k.casefold(): k for k in definitions}
    tier_traits = {f"sw.effect.tier.{i + 1}": rank for i, rank in enumerate(RANKS)}
    by_effect = defaultdict(dict)
    template_parents = {}
    for tag, row in definitions.items():
        effect = row["TemplateData"]["Effect"]["TagName"]
        ranks = {tier_traits[trait.casefold()] for trait in source.tag_set(row)
                 if trait.casefold() in tier_traits}
        if not ranks:
            continue  # Fixed Unique templates have their own native tier marker.
        rank = unique(ranks, tag)
        if effect != "None":
            base = actual[effect.casefold()]
        else:
            # A few shipped tiers omit TemplateData.Effect but still explicitly
            # inherit the base enchantment definition through their Traits.
            parents = {actual[trait.casefold()] for trait in source.tag_set(row)
                       if trait.casefold() in actual and definitions[actual[trait.casefold()]]
                       .get("EnchantmentData", {}).get("RelevantSlots", {}).get("GameplayTags")}
            base = unique(parents, tag)
        if rank in by_effect[base]:
            raise ValueError(f"Duplicate native enchantment tier {rank} for {base}")
        by_effect[base][rank] = tag
        template_parents[tag] = base
    out = {}
    for first, book in sorted(books.items()):
        associated = actual[first]
        effect = definitions[associated]["TemplateData"]["Effect"]["TagName"]
        base = template_parents.get(associated) or (actual[effect.casefold()] if effect != "None" else associated)
        parent = definitions[base]
        rec = out[base] = label(db, base, parent, zh)
        rec["slots"] = sorted(SLOTS[s.removeprefix("SW.ItemSlot.Equipment.")] for s in
                              tags(parent["EnchantmentData"], "RelevantSlots"))
        zh["enchants"][base] = {"name": zh["effectsById"][base], "desc": db.text(book, "Description")[1]}
        for rank in RANKS:
            if rank not in by_effect[base]:
                raise ValueError(f"Missing native enchantment tier {rank} for {base}")
            tag = by_effect[base][rank]
            row = definitions[tag]
            data = row["TemplateData"]
            en, cn = db.text(row, "Description", parent)
            if not (en and cn):
                raise ValueError(f"Missing enchantment text: {tag}")
            # Four enchantments have variable, non-display intensities. Creating a
            # new roll uses the native minimum rather than copying another save's random roll.
            intensity = data["FixedEffectValue"] if data["HasFixedEffectValue"] else data["EffectMinValue"]
            rec["tiers"].append({"template": tag, "tier": rank, "intensity": intensity, "text": en})
            zh["templates"][tag] = cn
    for tag in own & definitions.keys():
        row = definitions[tag]
        parent = definitions[row["TemplateData"]["Effect"]["TagName"]]
        fixed_text[tag] = db.text(row, "Description", parent)[1]
    return dict(sorted(out.items()))


def main(content, public=source.PUBLIC, defer_icons=False):
    db = Tables(content, public, defer_icons)
    zh = {k: {} for k in ("items", "itemsById", "effects", "effectsById", "templates", "enchants")}
    fixed_text = {}
    templates = db.rows("EffectTemplateDefinition")
    items, books, own, queries = items_for(db, templates, zh)
    effects = effects_for(db, templates, queries, own, zh, fixed_text)
    enchants = enchants_for(db, books, own, zh, fixed_text)
    if fixed_text.keys() != own:
        raise ValueError(f"Missing unique effect descriptions: {own - fixed_text.keys()}")
    rarities = []
    for tag, row in db.rows("RarityDefinition").items():
        rank = tag.rsplit(".", 1)[1]
        if rank not in ("Common", "Rare", "Special", "Unique"):
            continue
        spec = row["RarityDefinition"]["NumberOfEffectsData"]
        rarities.append({"id": rank, "rerollable": spec["BaseNumberOfRerollableEffects"],
                         "stormBonus": spec.get("AdditionalEffectChances", {}).get(
                             '(TagName="SW.Item.Property.StorminatorReward")', 0)})
    # Rules and image provenance are rebuilt by their own subsequent stages.
    labels = db.native_labels()
    meta = {"labels": labels} if any(labels.values()) else {}
    catalog = {"meta": meta, "items": items, "effects": effects,
               "enchantments": enchants, "rarities": rarities}
    public.mkdir(parents=True, exist_ok=True)
    source.write_json(public / "catalog.json", catalog)
    source.write_json(public / "zh.json", zh)
    source.write_json(public / "zh-unique.json", dict(sorted(fixed_text.items())))
    print(f"Native bilingual catalog: {len(items)} items, {len(effects)} effects, {len(enchants)} enchantments; "
          f"{sum(len(v['tiers']) for v in (*effects.values(), *enchants.values()))} effect templates, "
          f"{len(fixed_text)} unique descriptions.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("content", type=Path)
    parser.add_argument("--public", type=Path, default=source.PUBLIC)
    parser.add_argument("--defer-icons", action="store_true", help="Record iconSource only; decode images in the full refresh")
    main(**vars(parser.parse_args()))
