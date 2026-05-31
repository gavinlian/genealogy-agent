"""族谱智能体扫描：族谱内优化、跨谱匹配、大库对照。"""

from __future__ import annotations

import sqlite3
from typing import Any

from agent.smart_suggest import build_smart_suggest_from_source
from agent.validators import validate_genealogy_with_generations
from agent.person_matcher import (
    extract_persons_from_archive,
    find_person_matches,
    normalize_person_name,
)
from agent_discovery_store import (
    count_pending_discoveries,
    finish_scan_run,
    get_schedule_settings,
    list_snapshots,
    start_scan_run,
    touch_scan_run,
    upsert_discovery,
)
from db_schema import row_to_person
from source_versions import get_digitize_source_for_family
from user_store import list_families_for_user, list_followed_families, list_owned_families


def _load_family_graph(cursor: sqlite3.Cursor, family_id: str) -> tuple[list[dict], list[dict], dict | None]:
    family_row = cursor.execute("SELECT * FROM families WHERE id = ?", (family_id,)).fetchone()
    if not family_row:
        return [], [], None
    persons_rows = cursor.execute("SELECT * FROM persons WHERE family_id = ?", (family_id,)).fetchall()
    rel_rows = cursor.execute("SELECT * FROM relations WHERE family_id = ?", (family_id,)).fetchall()
    id_to_name = {r["id"]: r["name"] for r in persons_rows}
    persons = [row_to_person(r) for r in persons_rows]
    relations: list[dict] = []
    for r in rel_rows:
        fn = id_to_name.get(r["from_person_id"])
        tn = id_to_name.get(r["to_person_id"])
        if fn and tn:
            relations.append({
                "from": fn,
                "to": tn,
                "type": r["relation_type"] or "parent_child",
                "status": dict(r).get("status") or "confirmed",
            })
    return persons, relations, dict(family_row)


def _scan_intra_family_optimize(
    cursor: sqlite3.Cursor,
    user_id: str,
    family_id: str,
    family_name: str,
    settings: dict[str, Any],
) -> int:
    persons, relations, _family = _load_family_graph(cursor, family_id)
    if not persons:
        return 0
    new_count = 0
    source_text, source_version = get_digitize_source_for_family(cursor, family_id)
    source_text = (source_text or "").strip()
    if source_text:
        result = build_smart_suggest_from_source(
            persons,
            relations,
            source_text,
            source_version=source_version,
        )
        if result.get("success"):
            plan = result.get("plan") or {}
            diff = result.get("diff") or {}
            np = len(plan.get("new_persons") or [])
            nr = len(diff.get("relations_added") or plan.get("relations_add") or [])
            if np or nr:
                upsert_discovery(cursor, user_id, {
                    "family_id": family_id,
                    "discovery_type": "optimize_relation",
                    "title": f"「{family_name}」可优化关系",
                    "summary": plan.get("explanation") or f"可补 {np} 人、{nr} 条关系",
                    "plan": plan,
                    "confidence": 0.85,
                    "evidence": {
                        "source_label": (source_version or {}).get("label") or "原文",
                        "new_persons": np,
                        "new_relations": nr,
                    },
                })
                new_count += 1

    validation = validate_genealogy_with_generations(persons, relations)
    for issue in (validation.get("issues") or [])[:8]:
        level = issue.get("level") or "warning"
        if level != "error" and issue.get("field") == "name":
            continue
        upsert_discovery(cursor, user_id, {
            "family_id": family_id,
            "discovery_type": "data_conflict",
            "title": f"「{issue.get('person') or family_name}」需核查",
            "summary": issue.get("message") or "数据逻辑冲突",
            "confidence": 0.9 if level == "error" else 0.7,
            "evidence": issue,
        })
        new_count += 1
    return new_count


def _scan_cross_family_matches(
    cursor: sqlite3.Cursor,
    user_id: str,
    target_family_id: str,
    target_name: str,
    target_persons: list[dict],
    target_surname: str,
    source_family_id: str,
    source_name: str,
    source_persons: list[dict],
    source_surname: str,
    settings: dict[str, Any],
    *,
    source_snapshot_id: str | None = None,
) -> int:
    min_conf = float(settings.get("min_match_confidence") or 0.62)
    matches = find_person_matches(
        target_persons,
        source_persons,
        target_surname=target_surname,
        source_surname=source_surname,
        min_confidence=min_conf,
        limit=15,
    )
    new_count = 0
    existing_names = {normalize_person_name(p.get("name") or "") for p in target_persons}
    for m in matches:
        if m["target_name"] == m["source_name"] and m["target_name"] in existing_names:
            # 同名已在目标谱 — 可能是对照确认而非新人
            pass
        src_label = source_name
        if source_snapshot_id:
            src_label = f"大库「{source_name}」"
        upsert_discovery(cursor, user_id, {
            "family_id": target_family_id,
            "discovery_type": "snapshot_match" if source_snapshot_id else "cross_family_match",
            "title": f"「{m['target_name']}」≈ {src_label}「{m['source_name']}」",
            "summary": f"相似度 {int(m['confidence'] * 100)}%，建议核对是否为同一人或旁支关联",
            "confidence": m["confidence"],
            "source_family_id": source_family_id if not source_snapshot_id else None,
            "source_snapshot_id": source_snapshot_id,
            "evidence": {
                "person_name": m["target_name"],
                "match_name": m["source_name"],
                "target_generation": m["target_person"].get("generation"),
                "source_generation": m["source_person"].get("generation"),
                "source_label": src_label,
            },
        })
        new_count += 1
    return new_count


def run_agent_scan(
    cursor: sqlite3.Cursor,
    user_id: str,
    *,
    trigger: str = "manual",
    family_ids: list[str] | None = None,
) -> dict[str, Any]:
    settings = get_schedule_settings(cursor, user_id)
    if not settings.get("enabled") and trigger not in ("manual", "on_open"):
        return {"success": True, "skipped": True, "reason": "disabled"}

    before_pending = count_pending_discoveries(cursor, user_id)
    run_id = start_scan_run(cursor, user_id, trigger)
    scanned = 0
    discoveries_added = 0
    max_per_scan = int(settings.get("max_discoveries_per_scan") or 50)

    owned = list_owned_families(cursor, user_id)
    owned_ids = [f["id"] for f in owned]
    target_ids = family_ids or owned_ids

    owned_map = {f["id"]: f for f in owned}

    for fid in target_ids:
        if discoveries_added >= max_per_scan:
            break
        fam = owned_map.get(fid)
        if not fam:
            row = cursor.execute("SELECT * FROM families WHERE id = ?", (fid,)).fetchone()
            if not row:
                continue
            fam = dict(row)
        fname = fam.get("name") or fid
        scanned += 1
        discoveries_added += _scan_intra_family_optimize(cursor, user_id, fid, fname, settings)

        target_persons, _, family_row = _load_family_graph(cursor, fid)
        if not target_persons:
            continue
        target_surname = (family_row or {}).get("surname") or ""

        if settings.get("compare_owned_families"):
            for other in owned:
                if other["id"] == fid:
                    continue
                if discoveries_added >= max_per_scan:
                    break
                op, _, orow = _load_family_graph(cursor, other["id"])
                if not op:
                    continue
                discoveries_added += _scan_cross_family_matches(
                    cursor, user_id, fid, fname, target_persons, target_surname,
                    other["id"], other.get("name") or other["id"], op,
                    (orow or {}).get("surname") or "",
                    settings,
                )

        if settings.get("compare_followed_families"):
            for followed in list_followed_families(cursor, user_id):
                if followed["id"] == fid:
                    continue
                if discoveries_added >= max_per_scan:
                    break
                fp, _, frow = _load_family_graph(cursor, followed["id"])
                if not fp:
                    continue
                discoveries_added += _scan_cross_family_matches(
                    cursor, user_id, fid, fname, target_persons, target_surname,
                    followed["id"], followed.get("name") or followed["id"], fp,
                    (frow or {}).get("surname") or "",
                    settings,
                )

        if settings.get("compare_snapshots"):
            for snap_meta in list_snapshots(cursor, user_id):
                if discoveries_added >= max_per_scan:
                    break
                from agent_discovery_store import get_snapshot
                snap = get_snapshot(cursor, snap_meta["id"], user_id)
                if not snap:
                    continue
                sp = extract_persons_from_archive(snap.get("archive") or {})
                if not sp:
                    continue
                discoveries_added += _scan_cross_family_matches(
                    cursor, user_id, fid, fname, target_persons, target_surname,
                    "", snap.get("name") or "大库", sp, "",
                    settings,
                    source_snapshot_id=snap["id"],
                )

    after_pending = count_pending_discoveries(cursor, user_id)
    new_items = max(0, after_pending - before_pending)
    summary = f"扫描 {scanned} 份族谱，新增 {new_items} 条待确认发现"
    finish_scan_run(
        cursor, run_id,
        families_scanned=scanned,
        discoveries_new=new_items,
        summary=summary,
    )
    if trigger == "on_open":
        touch_scan_run(cursor, user_id, field="last_open_scan_at")
    else:
        touch_scan_run(cursor, user_id, field="last_run_at")

    return {
        "success": True,
        "run_id": run_id,
        "families_scanned": scanned,
        "discoveries_new": new_items,
        "pending_total": after_pending,
        "summary": summary,
    }
