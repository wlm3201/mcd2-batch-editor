#!/usr/bin/env python3
"""把 database.json 转成结构化 SQLite 数据库。

生成的表：
  meta                 源文件 meta 键值
  categories           分类表
  generic_data         genericData（本文件为空，仍保留结构）
  entity_<类型>        每种实体一张表：标量字段为列，对象/数组字段为 JSON 文本列，
                       并带 raw_json 保存完整原始记录（无损）
  entity_index         全局 id / type / name / slug / icon 速查表
  entity_list_items    数组字段逐项展开，便于按数组元素反查
  entity_object_items  对象字段逐键展开，便于查询嵌套键

用法：python json_to_sqlite.py [--json 路径] [--db 路径] [--overwrite]
"""

import argparse
import json
import re
import sqlite3
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

INDEX_FIELDS = {
    "slug", "type", "name", "area", "item", "enemy", "enchantment", "category",
    "parent", "kind", "quest", "npc", "effect", "slot", "pool", "armorset",
    "variantof", "uniqueof", "soulcorruptedform", "soulcorruptedof",
    "primarycategory", "rawitemid", "rawarea", "rarity", "region", "tier",
    "book", "companion", "library", "role", "location", "container", "enemyclass",
}


def q(identifier):
    return '"' + identifier.replace('"', '""') + '"'


def snake(name):
    return re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", name).lower()


def dump(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def encode(value):
    """标量原样保存；容器转 JSON 文本。"""
    if value is None:
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float, str)):
        return value
    return dump(value)


def sql_type(values):
    kinds = {type(v) for v in values if v is not None}
    if not kinds or kinds <= {bool, int}:
        return "INTEGER" if kinds else "TEXT"
    if kinds <= {bool, int, float}:
        return "REAL"
    return "TEXT"


def build_flat_table(conn, table, rows):
    """按记录字段并集建表；返回 (字段, 声明, 是否为 JSON 列) 列表。"""
    if not rows:
        return []
    fields = list(dict.fromkeys(f for row in rows for f in row))
    if "id" in fields:
        fields.remove("id")
        fields.insert(0, "id")

    columns = []
    for field in fields:
        values = [row[field] for row in rows if field in row]
        is_json_col = any(isinstance(v, (list, dict)) for v in values)
        columns.append((field, "TEXT" if is_json_col else sql_type(values), is_json_col))

    definitions = [
        f"{q(field)} {decl}" + (" PRIMARY KEY" if field == "id" else "")
        for field, decl, _ in columns
    ]
    definitions.append(f'{q("raw_json")} TEXT NOT NULL')
    conn.execute(f"CREATE TABLE {q(table)} ({', '.join(definitions)})")

    placeholders = ", ".join("?" for _ in range(len(columns) + 1))
    conn.executemany(
        f"INSERT INTO {q(table)} VALUES ({placeholders})",
        [tuple(cell(row.get(field), decl, is_json_col)
               for field, decl, is_json_col in columns)
         + (dump(row),) for row in rows],
    )

    for i, (field, _, is_json_col) in enumerate(columns):
        if field != "id" and not is_json_col and field.lower() in INDEX_FIELDS:
            idx = f"idx_{table}_{i}_{snake(field)}"
            conn.execute(f"CREATE INDEX {q(idx)} ON {q(table)} ({q(field)})")
    return columns


def cell(value, decl, is_json_col):
    if value is None:
        return None
    if is_json_col:
        return dump(value)
    if decl == "TEXT":
        return value if isinstance(value, str) else str(value)
    if isinstance(value, bool):
        return int(value)
    return value


def split_nested(value):
    """标量 -> (value, None)；对象/数组 -> (None, JSON 文本)。"""
    if isinstance(value, (list, dict)):
        return None, dump(value)
    return encode(value), None


def main():
    base = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description="database.json -> SQLite")
    parser.add_argument("--json", type=Path, default=base / "database.json")
    parser.add_argument("--db", type=Path, default=base / "database.sqlite")
    parser.add_argument("--overwrite", action="store_true", help="覆盖已存在的数据库")
    args = parser.parse_args()

    if args.db.exists() and not args.overwrite:
        parser.error(f"数据库已存在：{args.db}（如需重建请加 --overwrite）")
    if args.db.exists():
        args.db.unlink()

    with args.json.open(encoding="utf-8") as fh:
        doc = json.load(fh)
    data = doc.get("data") or {}
    entities = data.get("entities") or {}

    conn = sqlite3.connect(args.db)
    try:
        conn.execute("PRAGMA synchronous = OFF")
        conn.execute("BEGIN")

        conn.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT)")
        conn.executemany(
            "INSERT INTO meta VALUES (?, ?)",
            [(k, encode(v)) for k, v in (doc.get("meta") or {}).items()],
        )

        build_flat_table(conn, "categories", data.get("categories") or [])

        conn.execute(
            "CREATE TABLE generic_data ("
            "section TEXT, position INTEGER, value, value_json TEXT, raw_json TEXT)"
        )
        generic = data.get("genericData")
        if isinstance(generic, dict):
            sections = list(generic.items())
        elif isinstance(generic, list):
            sections = list(enumerate(generic))
        else:
            sections = [("", generic)]
        for section, value in sections:
            items = value if isinstance(value, list) else [value]
            for pos, item in enumerate(items):
                scalar, nested = split_nested(item)
                conn.execute(
                    "INSERT INTO generic_data VALUES (?, ?, ?, ?, ?)",
                    (str(section), pos if isinstance(value, list) else None,
                     scalar, nested,
                     dump(item) if isinstance(item, (list, dict)) else None),
                )

        conn.execute(
            "CREATE TABLE entity_index ("
            "id TEXT PRIMARY KEY, type TEXT NOT NULL, name TEXT, slug TEXT, icon TEXT)"
        )
        conn.execute(
            "CREATE TABLE entity_list_items ("
            "owner_type TEXT NOT NULL, owner_id TEXT NOT NULL, field TEXT NOT NULL, "
            "position INTEGER NOT NULL, value, value_json TEXT, "
            "PRIMARY KEY (owner_type, owner_id, field, position))"
        )
        conn.execute(
            "CREATE TABLE entity_object_items ("
            "owner_type TEXT NOT NULL, owner_id TEXT NOT NULL, field TEXT NOT NULL, "
            '"key" TEXT NOT NULL, value, value_json TEXT, '
            'PRIMARY KEY (owner_type, owner_id, field, "key"))'
        )

        for entity_type, rows in entities.items():
            table = "entity_" + snake(entity_type)
            build_flat_table(conn, table, rows)

            for row in rows:
                owner_id = row["id"]
                conn.execute(
                    "INSERT INTO entity_index VALUES (?, ?, ?, ?, ?)",
                    (owner_id, entity_type, encode(row.get("name")),
                     encode(row.get("slug")), encode(row.get("icon"))),
                )
                for field, value in row.items():
                    if isinstance(value, list):
                        conn.executemany(
                            "INSERT INTO entity_list_items VALUES (?, ?, ?, ?, ?, ?)",
                            [(entity_type, owner_id, field, pos, *split_nested(item))
                             for pos, item in enumerate(value)],
                        )
                    elif isinstance(value, dict):
                        conn.executemany(
                            "INSERT INTO entity_object_items VALUES (?, ?, ?, ?, ?, ?)",
                            [(entity_type, owner_id, field, str(key), *split_nested(v))
                             for key, v in value.items()],
                        )

        conn.execute("CREATE INDEX idx_entity_index_type ON entity_index (type)")
        conn.execute("CREATE INDEX idx_entity_index_slug ON entity_index (slug)")
        conn.execute("CREATE INDEX idx_entity_index_name ON entity_index (name)")
        conn.execute(
            "CREATE INDEX idx_list_owner ON entity_list_items (owner_type, owner_id)"
        )
        conn.execute(
            "CREATE INDEX idx_list_value ON entity_list_items (owner_type, field, value)"
        )
        conn.execute(
            "CREATE INDEX idx_object_owner ON entity_object_items (owner_type, owner_id, field)"
        )
        conn.execute(
            'CREATE INDEX idx_object_key ON entity_object_items (owner_type, field, "key")'
        )
        conn.commit()

        print(f"源文件：{args.json}  ({args.json.stat().st_size:,} bytes)")
        print(f"数据库：{args.db}  ({args.db.stat().st_size:,} bytes)")
        tables = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
        print(f"\n共 {len(tables)} 张表：")
        for table in tables:
            count = conn.execute(f"SELECT count(*) FROM {q(table)}").fetchone()[0]
            print(f"  {table:<32} {count:>6} 行")
        print("\nintegrity_check:", conn.execute("PRAGMA integrity_check").fetchone()[0])
        bad = 0
        for (table,) in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND sql LIKE '%raw_json%'"
        ).fetchall():
            bad += conn.execute(
                f'SELECT count(*) FROM {q(table)} '
                f'WHERE {q("raw_json")} IS NOT NULL '
                f'AND json_valid({q("raw_json")}) = 0'
            ).fetchone()[0]
        print("无效 raw_json / 嵌套 JSON 记录:", bad)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
