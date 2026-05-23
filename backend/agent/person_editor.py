"""成员与关系编辑：保持 persons.parent_id 与 relations 表一致"""

from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime
from typing import Any


def _now() -> str:
    return datetime.now().isoformat()


def get_spouse_id(cursor: sqlite3.Cursor, person_id: str) -> str | None:
    row = cursor.execute(
        """SELECT from_person_id, to_person_id FROM relations
           WHERE relation_type = 'spouse'
             AND (from_person_id = ? OR to_person_id = ?)
           LIMIT 1""",
        (person_id, person_id),
    ).fetchone()
    if not row:
        return None
    data = dict(row)
    if data["from_person_id"] == person_id:
        return data["to_person_id"]
    return data["from_person_id"]


def enrich_person_with_spouse(cursor: sqlite3.Cursor, person: dict) -> dict:
    out = dict(person)
    out["spouse_id"] = get_spouse_id(cursor, person["id"]) if person.get("id") else None
    return out


def clear_parent_relations(cursor: sqlite3.Cursor, family_id: str, person_id: str) -> None:
    cursor.execute(
        """DELETE FROM relations
           WHERE family_id = ? AND to_person_id = ? AND relation_type = 'parent_child'""",
        (family_id, person_id),
    )
    cursor.execute("UPDATE persons SET parent_id = NULL WHERE id = ?", (person_id,))


def sync_parent_relation(
    cursor: sqlite3.Cursor,
    family_id: str,
    person_id: str,
    parent_id: str | None,
    now: str | None = None,
) -> None:
    """设置或清除某人的父亲/母亲（parent_child：from=父, to=子）"""
    now = now or _now()
    clear_parent_relations(cursor, family_id, person_id)
    if not parent_id or parent_id == person_id:
        return
    cursor.execute("UPDATE persons SET parent_id = ? WHERE id = ?", (parent_id, person_id))
    rid = str(uuid.uuid4())[:8]
    cursor.execute(
        """INSERT INTO relations (
            id, family_id, from_person_id, to_person_id, relation_type, status, confidence, created_at
        ) VALUES (?, ?, ?, ?, 'parent_child', 'confirmed', 1.0, ?)""",
        (rid, family_id, parent_id, person_id, now),
    )


def clear_spouse_relations(cursor: sqlite3.Cursor, person_id: str) -> None:
    cursor.execute(
        """DELETE FROM relations
           WHERE relation_type = 'spouse'
             AND (from_person_id = ? OR to_person_id = ?)""",
        (person_id, person_id),
    )


def sync_spouse_relation(
    cursor: sqlite3.Cursor,
    family_id: str,
    person_id: str,
    spouse_id: str | None,
    now: str | None = None,
) -> None:
    now = now or _now()
    clear_spouse_relations(cursor, person_id)
    if not spouse_id or spouse_id == person_id:
        return
    clear_spouse_relations(cursor, spouse_id)
    rid = str(uuid.uuid4())[:8]
    cursor.execute(
        """INSERT INTO relations (
            id, family_id, from_person_id, to_person_id, relation_type, status, confidence, created_at
        ) VALUES (?, ?, ?, ?, 'spouse', 'confirmed', 1.0, ?)""",
        (rid, family_id, person_id, spouse_id, now),
    )


def relation_exists(
    cursor: sqlite3.Cursor,
    family_id: str,
    from_id: str,
    to_id: str,
    relation_type: str,
) -> bool:
    row = cursor.execute(
        """SELECT 1 FROM relations
           WHERE family_id = ? AND from_person_id = ? AND to_person_id = ? AND relation_type = ?
           LIMIT 1""",
        (family_id, from_id, to_id, relation_type),
    ).fetchone()
    return row is not None


def create_relation_record(
    cursor: sqlite3.Cursor,
    family_id: str,
    from_id: str,
    to_id: str,
    relation_type: str,
    *,
    status: str = "confirmed",
    confidence: float = 1.0,
    relation_subtype: str = "birth",
    now: str | None = None,
) -> str:
    """创建关系并同步 parent_id（若为父子关系）"""
    now = now or _now()
    if relation_exists(cursor, family_id, from_id, to_id, relation_type):
        raise ValueError("关系已存在")

    rid = str(uuid.uuid4())[:8]
    cursor.execute(
        """INSERT INTO relations (
            id, family_id, from_person_id, to_person_id, relation_type,
            status, confidence, relation_subtype, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (rid, family_id, from_id, to_id, relation_type, status, confidence, relation_subtype, now),
    )

    if relation_type == "parent_child":
        cursor.execute("UPDATE persons SET parent_id = ? WHERE id = ?", (from_id, to_id))
    return rid


def apply_person_relations(
    cursor: sqlite3.Cursor,
    family_id: str,
    person_id: str,
    person: dict[str, Any],
    *,
    is_new: bool,
    now: str | None = None,
) -> None:
    """创建/更新成员后同步父母、配偶关系"""
    now = now or _now()
    if "parent_id" in person:
        sync_parent_relation(cursor, family_id, person_id, person.get("parent_id") or None, now)
    elif is_new and person.get("parent_id"):
        sync_parent_relation(cursor, family_id, person_id, person["parent_id"], now)

    if "spouse_id" in person:
        sync_spouse_relation(cursor, family_id, person_id, person.get("spouse_id") or None, now)
    elif is_new and person.get("spouse_id"):
        sync_spouse_relation(cursor, family_id, person_id, person["spouse_id"], now)
