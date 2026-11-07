"""Refresh fixed enchantment descriptions from UFS and the English/Chinese game locres.
For new icon references, supply --archive FILE.utoc --retoc EXE; MCD2_AES_KEY is read from the environment.
"""
import argparse
import base64
from decimal import Decimal, ROUND_HALF_UP
import importlib.util
import os
import re
from pathlib import Path
from tempfile import TemporaryDirectory


def sibling(name):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def dynamic_args(row, parent, entry):
    abilities = row.get("Abilities") or parent.get("Abilities", [])
    values = {v["TypeTag"]["TagName"]: v for ability in abilities
              for field in ("CommonKeyValues", "SpecificKeyValues") for v in ability.get(field, [])}
    for ability in row.get("AbilitySpecialization", {}).get("Specializations", []):
        for mod in ability.get("KeyValueSpecializations", []):
            v = mod["KeyValue"]
            if mod["ModOp"] == "Override":
                values[v["TypeTag"]["TagName"]] = v
    getter = entry["DynamicDataGetterFunction"]["TagName"].split(".")[-1]
    result = []
    for index, arg in enumerate(entry.get("ValuesToGet", [])):
        fmt = arg["FormattingData"]
        if getter == "GetEffectMagnitude":
            n = row["TemplateData"]["FixedEffectValue"]
        elif getter == "GetAllEffectModifiers":
            modifier = row["GameplayEffect"]["Modifiers"][index]["ModifierMagnitude"]
            if modifier["MagnitudeCalculationType"] != "ScalableFloat":
                raise ValueError(f"Unsupported modifier: {modifier['MagnitudeCalculationType']}")
            n = modifier["ScalableFloatMagnitude"]["Value"]
        elif getter == "GetGravityWellRadiusValue":
            n, = [instance["PullRadius"] for ability in abilities for instance in ability.get("InstanceData", [])
                  if "PullRadius" in instance]
        elif getter == "GetAbilityKeyValues":
            v = values[arg["TagToExtractFrom"]["TagName"]]
            n = v[v["Type"]]
        else:
            raise ValueError(f"Unsupported text getter: {getter}")
        n = (Decimal(str(n)) + Decimal(str(fmt["Offset"]))) * Decimal(str(fmt["Multiplier"]))
        if fmt["IsPercentage"] and fmt["ValueTypeToExtract"] != "Integer":
            n *= 100
        if fmt["RoundingMode"] != "HalfFromZero" or fmt["AlwaysSign"] or fmt["UseGrouping"]:
            raise ValueError(f"Unsupported formatting: {fmt}")
        n = n.quantize(Decimal(1).scaleb(-fmt["MaxFractionalDigits"]), rounding=ROUND_HALF_UP)
        number = format(n, "f")
        if "." in number:
            whole, fraction = number.split(".")
            fraction = fraction.rstrip("0").ljust(fmt["MinFractionalDigits"], "0")
            number = whole + ("." + fraction if fraction else "")
        result.append(number + ("%" if fmt["IsPercentage"] else ""))
    return result


def main(args):
    data = sibling("sync-game-data")
    public = args.public
    extras_path = public / "extras.json"
    chinese_path = public / "zh-unique.json"
    extras = data.read_json(extras_path) if extras_path.is_file() else {}
    # Do not use an older extras file as the definition of this build's fixed effects.
    current, _ = sibling("sync-native-rules").native_rules(args.content)
    extras.update(current)
    valid = {row["template"] for row in extras["uniqueOwn"].values()}
    chinese = {key: text for key, text in (data.read_json(chinese_path) if chinese_path.is_file() else {}).items()
               if key in valid}
    rows = {r["TypeTag"]["TagName"]: r for r in data.read_json(
        args.content / "Spicewood/Core/DataTables/UFS/DT_EnchantmentDefinition.json")}
    langs = [data.localization(args.content / f"Localization/All/{lang}/All.locres") for lang in ("en", "zh-Hans")]
    templates = {r["template"]: r["effect"] for r in extras["uniqueOwn"].values()
                 if r["template"].startswith("SW.Enchantment.")}
    records = {}
    pending = {}
    for tag, base in sorted(templates.items()):
        row, parent = rows[tag], rows[base]
        rec = records[tag] = {}
        for part, fields in (("Name", ("name", "zhName")), ("Description", ("text", "zhText"))):
            key = f'(TagName="SW.TextEntry.{part}")'
            entry = row.get("TypeTextData", {}).get("Texts", {}).get(key) or parent["TypeTextData"]["Texts"][key]
            loc = re.fullmatch(r'LOCTABLE\("([^"]+)", "([^"]+)"\)', entry["Text"]).groups()
            for field, lang in zip(fields, langs):
                pattern = lang[loc]
                rec[field] = pattern.format(*dynamic_args(row, parent, entry)) if "{" in pattern else pattern
        chinese[tag] = rec.pop("zhText")
        ref = row.get("IconReference")
        if ref and ref != "None":
            rec["iconSource"] = ref
            if args.defer_icons:
                rec["icon"] = None
                continue
            old = extras.get("uniqueEnchantments", {}).get(tag, {})
            if old.get("iconSource") == ref and old.get("icon") and not args.refresh_icons:
                rec["icon"] = old["icon"]
            else:
                pending[tag] = ref

    if pending:
        if not (args.archive and args.retoc):
            raise ValueError("New textures require --archive and --retoc")
        extractor = sibling("extract-game-icons")
        encoder = sibling("sync-game-icons")
        key = os.environ.get("MCD2_AES_KEY", "")
        listing = args.listing.read_text(encoding="utf-8-sig") if args.listing else extractor.run_retoc(
            args.retoc, key, "list", "--path", "--size", str(args.archive)).decode("utf-8")
        chunks = extractor.find_chunks(listing, set(pending.values()))
        with TemporaryDirectory() as temp:
            out = Path(temp)
            for tag, ref in pending.items():
                meta = extractor.extract(ref, chunks, args.retoc, key, args.archive, out)
                _, (_, image) = encoder.encode_texture(out, meta)
                records[tag]["icon"] = "data:image/webp;base64," + base64.b64encode(image).decode("ascii")
    extras["uniqueEnchantments"] = records
    public.mkdir(parents=True, exist_ok=True)
    data.write_json(extras_path, extras)
    data.write_json(chinese_path, chinese)
    print(f"{len(records)} fixed enchantments localized; {len(pending)} native textures decoded.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("content", type=Path)
    parser.add_argument("--public", type=Path, default=Path(__file__).resolve().parents[1] / "public")
    parser.add_argument("--defer-icons", action="store_true", help="Record iconSource only; decode images in the full refresh")
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--retoc", type=Path)
    parser.add_argument("--listing", type=Path, help="Existing retoc list --path output")
    parser.add_argument("--refresh-icons", action="store_true", help="Read textures again even when references match")
    main(parser.parse_args())
