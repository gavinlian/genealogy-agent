"""族谱归档：统一导出/导入本系统全部数据结构，兼容国际字段命名。"""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime
from typing import Any

from db_schema import row_to_person
from source_versions import ensure_versions_table, list_source_versions

ARCHIVE_SCHEMA = "genealogy-archive/1.0"
INTERNATIONAL_FIELD_MAP = {
    "name": "name",
    "given_name": "given_name",
    "surname": "surname",
    "gender": "sex",
    "birth_year": "birth_date_approx",
    "death_year": "death_date_approx",
    "generation": "generation",
    "generation_name": "generation_name",
    "courtesy_name": "courtesy_name",
    "art_name": "art_name",
    "county": "place_county",
    "town": "place_town",
    "village": "place_village",
    "biography": "biography",
    "parent_id": "parent_id",
    "spouse_ids": "spouse_ids",
}


def _person_export_row(row: sqlite3.Row | dict) -> dict:
    p = row_to_person(row)
    intl = {INTERNATIONAL_FIELD_MAP.get(k, k): v for k, v in p.items() if v is not None}
    intl["id"] = p.get("id")
    intl["family_id"] = p.get("family_id")
    intl["status"] = p.get("status")
    intl["review_status"] = p.get("review_status")
    intl["is_placeholder"] = p.get("is_placeholder")
    return {"native": p, "international": intl}


def _relation_export_row(row: sqlite3.Row | dict) -> dict:
    r = dict(row)
    return {
        "native": r,
        "international": {
            "id": r.get("id"),
            "family_id": r.get("family_id"),
            "from_person_id": r.get("from_person_id"),
            "to_person_id": r.get("to_person_id"),
            "relation_type": r.get("relation_type"),
            "relation_subtype": r.get("relation_subtype"),
            "status": r.get("status"),
            "confidence": r.get("confidence"),
            "note": r.get("note"),
        },
    }


def build_family_archive(cursor: sqlite3.Cursor, family_id: str) -> dict[str, Any]:
    ensure_versions_table(cursor)
    family = cursor.execute("SELECT * FROM families WHERE id = ?", (family_id,)).fetchone()
    if not family:
        raise ValueError("Family not found")

    persons = cursor.execute("SELECT * FROM persons WHERE family_id = ?", (family_id,)).fetchall()
    relations = cursor.execute("SELECT * FROM relations WHERE family_id = ?", (family_id,)).fetchall()
    ocr_rows = cursor.execute("SELECT * FROM ocr_records WHERE family_id = ?", (family_id,)).fetchall()
    versions_payload = list_source_versions(cursor, family_id)

    return {
        "schema": ARCHIVE_SCHEMA,
        "exported_at": datetime.now().isoformat(),
        "family": dict(family),
        "persons": [_person_export_row(p) for p in persons],
        "relations": [_relation_export_row(r) for r in relations],
        "source_versions": versions_payload.get("versions") or [],
        "active_source_version_id": versions_payload.get("active_version_id"),
        "ocr_records": [dict(o) for o in ocr_rows],
        "field_map": INTERNATIONAL_FIELD_MAP,
        "stats": {
            "person_count": len(persons),
            "relation_count": len(relations),
            "source_version_count": len(versions_payload.get("versions") or []),
        },
    }


def build_user_archive(cursor: sqlite3.Cursor, user_id: str) -> dict[str, Any]:
    from user_store import list_families_for_user

    families_meta = list_families_for_user(cursor, user_id)
    archives = []
    for meta in families_meta:
        fid = meta["id"]
        try:
            archives.append(build_family_archive(cursor, fid))
        except ValueError:
            continue
    return {
        "schema": ARCHIVE_SCHEMA,
        "exported_at": datetime.now().isoformat(),
        "user_id": user_id,
        "families": families_meta,
        "family_archives": archives,
        "stats": {
            "family_count": len(archives),
            "person_count": sum(a["stats"]["person_count"] for a in archives),
        },
    }


def import_family_archive(
    cursor: sqlite3.Cursor,
    data: dict[str, Any],
    *,
    owner_user_id: str | None = None,
    new_family_id: str | None = None,
) -> dict[str, Any]:
    """从归档 JSON 导入一族谱（新建 family_id）。"""
    family_in = data.get("family") or {}
    if not family_in.get("name"):
        raise ValueError("归档缺少 family.name")

    fid = new_family_id or str(uuid.uuid4())[:8]
    now = datetime.now().isoformat()
    cursor.execute(
        """INSERT INTO families (id, name, surname, description, root_person_id, created_at, updated_at,
           start_generation, source_text, source_annotations, owner_user_id)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            fid,
            family_in.get("name"),
            family_in.get("surname"),
            family_in.get("description"),
            family_in.get("root_person_id"),
            family_in.get("created_at") or now,
            now,
            family_in.get("start_generation") or 1,
            family_in.get("source_text") or "",
            family_in.get("source_annotations") or "[]",
            owner_user_id or family_in.get("owner_user_id"),
        ),
    )

    id_map: dict[str, str] = {}
    for item in data.get("persons") or []:
        native = item.get("native") if isinstance(item, dict) and "native" in item else item
        if not native:
            continue
        old_id = native.get("id") or str(uuid.uuid4())[:8]
        pid = str(uuid.uuid4())[:8]
        id_map[old_id] = pid
        cursor.execute(
            """INSERT INTO persons (
                id, family_id, name, gender, birth_year, death_year, generation, generation_name,
                generation_prefix, parent_id, spouse_ids, status, created_at,
                courtesy_name, art_name, county, town, village, biography,
                ai_confidence, review_status, is_placeholder
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                pid, fid, native.get("name"), native.get("gender"), native.get("birth_year"),
                native.get("death_year"), native.get("generation"), native.get("generation_name"),
                native.get("generation_prefix"),
                None,
                json.dumps(native.get("spouse_ids") or [], ensure_ascii=False) if not isinstance(native.get("spouse_ids"), str) else native.get("spouse_ids"),
                native.get("status") or "confirmed", now,
                native.get("courtesy_name"), native.get("art_name"),
                native.get("county"), native.get("town"), native.get("village"), native.get("biography"),
                native.get("ai_confidence"), native.get("review_status") or "confirmed",
                1 if native.get("is_placeholder") else 0,
            ),
        )

    for item in data.get("relations") or []:
        native = item.get("native") if isinstance(item, dict) and "native" in item else item
        if not native:
            continue
        rid = str(uuid.uuid4())[:8]
        f_old = native.get("from_person_id")
        t_old = native.get("to_person_id")
        cursor.execute(
            """INSERT INTO relations (
                id, family_id, from_person_id, to_person_id, relation_type, status, created_at,
                confidence, note, relation_subtype
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                rid, fid,
                id_map.get(f_old, f_old),
                id_map.get(t_old, t_old),
                native.get("relation_type") or "parent_child",
                native.get("status") or "confirmed", now,
                native.get("confidence") or 1.0,
                native.get("note"),
                native.get("relation_subtype") or "birth",
            ),
        )

    ensure_versions_table(cursor)
    from source_versions import create_source_version

    for ver in data.get("source_versions") or []:
        create_source_version(
            cursor,
            fid,
            source_text=ver.get("source_text") or "",
            source_annotations=ver.get("source_annotations"),
            label=ver.get("label"),
            status=ver.get("status") or "draft",
            note=ver.get("note"),
            version_kind=ver.get("version_kind") or "custom",
            set_active=ver.get("id") == data.get("active_source_version_id"),
        )

    return {"success": True, "family_id": fid, "person_count": len(id_map)}
