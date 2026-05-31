"""跨族谱合并：将源族谱成员/关系/原文增量并入目标族谱。"""

from __future__ import annotations

import uuid
from typing import Any

from db_schema import row_to_person
from source_versions import (
    VERSION_KIND_OCR_RAW,
    find_version_by_kind,
    merge_version_note,
    migrate_legacy_family_source,
    upsert_version_by_kind,
)


def _user_can_access_family(cursor, user_id: str, family_id: str) -> bool:
    from user_store import list_owned_families, list_followed_families

    owned = {f["id"] for f in list_owned_families(cursor, user_id)}
    if family_id in owned:
        return True
    followed = {f["id"] for f in list_followed_families(cursor, user_id)}
    return family_id in followed


def resolve_source_family_id(
    cursor,
    user_id: str,
    *,
    source_family_id: str | None = None,
    source_family_name: str | None = None,
    exclude_family_id: str | None = None,
) -> str | None:
    if source_family_id:
        fid = source_family_id.strip()
        if fid and fid != exclude_family_id and _user_can_access_family(cursor, user_id, fid):
            return fid
    name = (source_family_name or "").strip()
    if not name:
        return None
    from user_store import list_owned_families

    for f in list_owned_families(cursor, user_id):
        fid = f.get("id")
        if not fid or fid == exclude_family_id:
            continue
        fname = (f.get("name") or "").strip()
        if name == fname or name in fname or fname in name:
            return fid
    return None


def _get_family_source_text(cursor, family_id: str) -> tuple[str, dict | None]:
    """取族谱可用于合并的原文：优先版本一 OCR，否则活跃版/legacy。"""
    src_v1 = find_version_by_kind(cursor, family_id, VERSION_KIND_OCR_RAW)
    if (src_v1 or {}).get("source_text"):
        return ((src_v1 or {}).get("source_text") or "").strip(), src_v1

    migrate_legacy_family_source(cursor, family_id)
    row = cursor.execute(
        "SELECT source_text, active_source_version_id FROM families WHERE id = ?",
        (family_id,),
    ).fetchone()
    active_id = row["active_source_version_id"] if row else None
    if active_id:
        from source_versions import get_source_version

        active = get_source_version(cursor, family_id, active_id)
        if (active or {}).get("source_text"):
            return ((active or {}).get("source_text") or "").strip(), active

    legacy = ((row["source_text"] or "").strip() if row else "")
    if legacy:
        return legacy, src_v1
    return "", src_v1


def _relations_named(cursor, family_id: str, persons: list[dict]) -> list[dict]:
    id_to_name = {p["id"]: p.get("name", "") for p in persons if p.get("id")}
    rows = cursor.execute(
        "SELECT * FROM relations WHERE family_id = ?",
        (family_id,),
    ).fetchall()
    out: list[dict] = []
    for r in rows:
        rd = dict(r)
        fn = id_to_name.get(rd.get("from_person_id") or "", "")
        tn = id_to_name.get(rd.get("to_person_id") or "", "")
        if fn and tn:
            out.append({
                "from": fn,
                "to": tn,
                "type": rd.get("relation_type") or "parent_child",
                "status": rd.get("status") or "inferred",
                "confidence": rd.get("confidence") or 0.85,
                "relation_subtype": rd.get("relation_subtype") or "birth",
            })
    return out


def build_family_merge_preview(
    cursor,
    target_family_id: str,
    source_family_id: str,
    user_id: str,
) -> dict[str, Any]:
    if target_family_id == source_family_id:
        raise ValueError("不能合并到自身")
    if not _user_can_access_family(cursor, user_id, target_family_id):
        raise ValueError("无权操作目标族谱")
    if not _user_can_access_family(cursor, user_id, source_family_id):
        raise ValueError("无权读取源族谱")

    target_row = cursor.execute("SELECT * FROM families WHERE id = ?", (target_family_id,)).fetchone()
    source_row = cursor.execute("SELECT * FROM families WHERE id = ?", (source_family_id,)).fetchone()
    if not target_row or not source_row:
        raise ValueError("族谱不存在")

    target_persons = [row_to_person(r) for r in cursor.execute(
        "SELECT * FROM persons WHERE family_id = ?", (target_family_id,)
    ).fetchall()]
    source_persons = [row_to_person(r) for r in cursor.execute(
        "SELECT * FROM persons WHERE family_id = ?", (source_family_id,)
    ).fetchall()]
    source_relations = _relations_named(cursor, source_family_id, source_persons)

    target_names = {(p.get("name") or "").strip() for p in target_persons if (p.get("name") or "").strip()}
    new_persons: list[str] = []
    updated_persons: list[str] = []
    for p in source_persons:
        name = (p.get("name") or "").strip()
        if not name:
            continue
        if name in target_names:
            updated_persons.append(name)
        else:
            new_persons.append(name)

    target_rel_keys = {
        (r["from"], r["to"], r.get("type") or "parent_child")
        for r in _relations_named(cursor, target_family_id, target_persons)
    }
    new_relations = [
        r for r in source_relations
        if (r["from"], r["to"], r.get("type") or "parent_child") not in target_rel_keys
    ]

    src_text, src_v1 = _get_family_source_text(cursor, source_family_id)
    tgt_v1 = find_version_by_kind(cursor, target_family_id, VERSION_KIND_OCR_RAW)
    source_ocr_chars = len(src_text)

    return {
        "success": True,
        "target_family_id": target_family_id,
        "target_family_name": target_row["name"],
        "source_family_id": source_family_id,
        "source_family_name": source_row["name"],
        "stats": {
            "source_person_count": len(source_persons),
            "source_relation_count": len(source_relations),
            "persons_to_add": len(new_persons),
            "persons_to_update": len(updated_persons),
            "relations_to_add": len(new_relations),
            "source_ocr_chars": source_ocr_chars,
            "target_has_ocr": bool((tgt_v1 or {}).get("source_text")),
        },
        "preview": {
            "new_persons": new_persons[:30],
            "updated_persons": updated_persons[:30],
            "new_relations": new_relations[:20],
        },
        "summary": (
            f"将「{source_row['name']}」合并进「{target_row['name']}」："
            f"新增 {len(new_persons)} 人、更新 {len(updated_persons)} 人、"
            f"追加 {len(new_relations)} 条关系"
            + (f"、合并 OCR 原文 {source_ocr_chars} 字" if source_ocr_chars else "")
        ),
    }


def apply_family_merge(
    cursor,
    target_family_id: str,
    source_family_id: str,
    user_id: str,
    now: str,
    *,
    merge_ocr_text: bool = True,
) -> dict[str, Any]:
    preview = build_family_merge_preview(cursor, target_family_id, source_family_id, user_id)
    source_persons = [row_to_person(r) for r in cursor.execute(
        "SELECT * FROM persons WHERE family_id = ?", (source_family_id,)
    ).fetchall()]
    source_relations = _relations_named(cursor, source_family_id, source_persons)

    name_to_id: dict[str, str] = {}
    for row in cursor.execute(
        "SELECT id, name FROM persons WHERE family_id = ?", (target_family_id,)
    ).fetchall():
        name_to_id[row["name"]] = row["id"]

    persons_added = 0
    persons_updated = 0

    for p in source_persons:
        name = (p.get("name") or "").strip()
        if not name:
            continue
        if name in name_to_id:
            pid = name_to_id[name]
            cursor.execute(
                """UPDATE persons SET
                   gender=COALESCE(?, gender),
                   birth_year=COALESCE(?, birth_year),
                   death_year=COALESCE(?, death_year),
                   generation=COALESCE(?, generation),
                   generation_name=COALESCE(?, generation_name),
                   generation_prefix=COALESCE(?, generation_prefix),
                   courtesy_name=COALESCE(?, courtesy_name),
                   art_name=COALESCE(?, art_name),
                   county=COALESCE(?, county),
                   town=COALESCE(?, town),
                   village=COALESCE(?, village),
                   biography=COALESCE(?, biography),
                   review_status=COALESCE(?, review_status)
                   WHERE id=?""",
                (
                    p.get("gender") if p.get("gender") not in (None, "", "unknown") else None,
                    p.get("birth_year"),
                    p.get("death_year"),
                    p.get("generation"),
                    p.get("generation_name"),
                    p.get("generation_prefix"),
                    p.get("courtesy_name"),
                    p.get("art_name"),
                    p.get("county"),
                    p.get("town"),
                    p.get("village"),
                    p.get("biography"),
                    p.get("review_status"),
                    pid,
                ),
            )
            persons_updated += 1
            continue

        pid = str(uuid.uuid4())[:8]
        name_to_id[name] = pid
        cursor.execute(
            """INSERT INTO persons (
                id, family_id, name, gender, birth_year, death_year, generation,
                generation_name, generation_prefix, parent_id, spouse_ids, status, created_at,
                courtesy_name, art_name, county, town, village, biography,
                ai_confidence, review_status, is_placeholder
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                pid, target_family_id, name,
                p.get("gender") or "unknown",
                p.get("birth_year"), p.get("death_year"),
                p.get("generation"), p.get("generation_name"), p.get("generation_prefix"),
                None,
                p.get("spouse_ids") if isinstance(p.get("spouse_ids"), str) else "[]",
                p.get("status") or "confirmed", now,
                p.get("courtesy_name"), p.get("art_name"),
                p.get("county"), p.get("town"), p.get("village"), p.get("biography"),
                p.get("ai_confidence"), p.get("review_status") or "pending_review",
                1 if p.get("is_placeholder") else 0,
            ),
        )
        persons_added += 1

    relations_added = 0
    for rel in source_relations:
        fn, tn = rel.get("from"), rel.get("to")
        rtype = rel.get("type") or "parent_child"
        if not fn or not tn or fn not in name_to_id or tn not in name_to_id:
            continue
        from_id, to_id = name_to_id[fn], name_to_id[tn]
        exists = cursor.execute(
            """SELECT id FROM relations
               WHERE family_id=? AND from_person_id=? AND to_person_id=? AND relation_type=?""",
            (target_family_id, from_id, to_id, rtype),
        ).fetchone()
        if exists:
            if rtype == "parent_child":
                cursor.execute("UPDATE persons SET parent_id = ? WHERE id = ?", (from_id, to_id))
            continue
        rid = str(uuid.uuid4())[:8]
        cursor.execute(
            """INSERT INTO relations (
                id, family_id, from_person_id, to_person_id, relation_type,
                status, confidence, relation_subtype, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                rid, target_family_id, from_id, to_id, rtype,
                rel.get("status") or "inferred",
                rel.get("confidence") or 0.85,
                rel.get("relation_subtype") or "birth",
                now,
            ),
        )
        relations_added += 1
        if rtype == "parent_child":
            cursor.execute("UPDATE persons SET parent_id = ? WHERE id = ?", (from_id, to_id))

    ocr_merged = False
    if merge_ocr_text:
        src_text, src_v1 = _get_family_source_text(cursor, source_family_id)
        if src_text:
            src_name = preview.get("source_family_name") or source_family_id
            tgt_v1 = find_version_by_kind(cursor, target_family_id, VERSION_KIND_OCR_RAW)
            tgt_text, _ = _get_family_source_text(cursor, target_family_id)
            block = f"===== 合并自「{src_name}」 =====\n{src_text}"
            merged_text = f"{tgt_text}\n\n{block}".strip() if tgt_text else block
            note = merge_version_note(
                tgt_v1.get("note") if tgt_v1 else None,
                image_path=(tgt_v1 or {}).get("image_path") or (src_v1 or {}).get("image_path"),
            )
            upsert_version_by_kind(
                cursor,
                target_family_id,
                VERSION_KIND_OCR_RAW,
                source_text=merged_text,
                source_annotations=(tgt_v1 or src_v1 or {}).get("source_annotations"),
                status="confirmed",
                note=note,
            )
            ocr_merged = True

    from agent.generation_engine import recalculate_generations
    from datetime import datetime

    family_row = cursor.execute("SELECT * FROM families WHERE id = ?", (target_family_id,)).fetchone()
    persons_rows = cursor.execute("SELECT * FROM persons WHERE family_id = ?", (target_family_id,)).fetchall()
    rel_rows = cursor.execute("SELECT * FROM relations WHERE family_id = ?", (target_family_id,)).fetchall()
    if persons_rows:
        persons_list = [dict(r) for r in persons_rows]
        relations_list = [dict(r) for r in rel_rows]
        start_gen = int((dict(family_row) if family_row else {}).get("start_generation") or 1)
        root_id = (dict(family_row) if family_row else {}).get("root_person_id")
        result = recalculate_generations(persons_list, relations_list, root_person_id=root_id, start_generation=start_gen)
        now_gen = datetime.now().isoformat()
        for p in result["persons"]:
            cursor.execute("UPDATE persons SET generation = ? WHERE id = ?", (p.get("generation"), p["id"]))
        new_root = result.get("root_person_id")
        if new_root and family_row and new_root != family_row["root_person_id"]:
            cursor.execute(
                "UPDATE families SET root_person_id = ?, updated_at = ? WHERE id = ?",
                (new_root, now_gen, target_family_id),
            )

    return {
        "success": True,
        **preview["stats"],
        "persons_added": persons_added,
        "persons_updated": persons_updated,
        "relations_added": relations_added,
        "ocr_text_merged": ocr_merged,
        "message": preview.get("summary"),
    }
