"""数据库字段迁移与成员序列化"""

import sqlite3

PERSON_EXTRA_COLUMNS = [
    ("courtesy_name", "TEXT"),
    ("art_name", "TEXT"),
    ("county", "TEXT"),
    ("town", "TEXT"),
    ("village", "TEXT"),
    ("biography", "TEXT"),
    ("ai_confidence", "REAL"),
    ("review_status", "TEXT DEFAULT 'confirmed'"),
    ("is_placeholder", "INTEGER DEFAULT 0"),
]

RELATION_EXTRA_COLUMNS = [
    ("confidence", "REAL DEFAULT 1.0"),
    ("note", "TEXT"),
    ("relation_subtype", "TEXT DEFAULT 'birth'"),
]

FAMILY_EXTRA_COLUMNS = [
    ("start_generation", "INTEGER DEFAULT 1"),
    ("source_text", "TEXT"),
    ("source_annotations", "TEXT"),
]


def migrate_schema(cursor: sqlite3.Cursor) -> None:
    for col, typedef in PERSON_EXTRA_COLUMNS:
        try:
            cursor.execute(f"ALTER TABLE persons ADD COLUMN {col} {typedef}")
        except sqlite3.OperationalError:
            pass
    for col, typedef in RELATION_EXTRA_COLUMNS:
        try:
            cursor.execute(f"ALTER TABLE relations ADD COLUMN {col} {typedef}")
        except sqlite3.OperationalError:
            pass
    for col, typedef in FAMILY_EXTRA_COLUMNS:
        try:
            cursor.execute(f"ALTER TABLE families ADD COLUMN {col} {typedef}")
        except sqlite3.OperationalError:
            pass


def row_to_person(row: sqlite3.Row | dict) -> dict:
    if row is None:
        return {}
    keys = row.keys() if hasattr(row, "keys") else row
    data = dict(row)
    loc_parts = [data.get("county"), data.get("town"), data.get("village")]
    data["location_text"] = " ".join(p for p in loc_parts if p)
    if "is_placeholder" in data:
        data["is_placeholder"] = bool(data["is_placeholder"])
    return data
