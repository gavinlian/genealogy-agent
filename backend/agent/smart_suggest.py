"""从原文快速推断整理方案（本地规则，无需等待大模型）。"""

from __future__ import annotations

from typing import Any

from .genealogy_builder import auto_build_genealogy, parse_genealogy_text_enhanced
from .genealogy_organizer import (
    compute_organize_diff,
    merge_plan_into_genealogy,
    reconcile_plan_with_genealogy,
    _normalize_plan,
)
from .relation_text import build_local_relation_description
from source_versions import VERSION_KIND_OCR_RAW


def _relation_key(r: dict) -> tuple[str, str, str]:
    return (
        (r.get("from") or "").strip(),
        (r.get("to") or "").strip(),
        r.get("type") or "parent_child",
    )


def _named_relations_from_rows(persons_rows: list, rel_rows: list) -> list[dict]:
    id_to_name = {r["id"]: r["name"] for r in persons_rows if r.get("id") and r.get("name")}
    out: list[dict] = []
    for r in rel_rows:
        fn = id_to_name.get(r.get("from_person_id"))
        tn = id_to_name.get(r.get("to_person_id"))
        if fn and tn:
            out.append({
                "from": fn,
                "to": tn,
                "type": r.get("relation_type") or "parent_child",
                "status": r.get("status") or "confirmed",
            })
    return out


def build_smart_suggest_from_source(
    persons: list[dict],
    relations: list[dict],
    source_text: str,
    *,
    source_version: dict | None = None,
    style: str = "su",
    generation_scheme: str = "absolute",
    generation_epoch_offset: int = 1,
) -> dict[str, Any]:
    text = (source_text or "").strip()
    if not text:
        return {
            "success": False,
            "error": "暂无原文。请先在「原文」中保存版本一 OCR 或版本二关系描述。",
        }

    version_label = (source_version or {}).get("label") or "族谱原文"
    version_kind = (source_version or {}).get("version_kind") or ""

    relation_text = text
    if version_kind == VERSION_KIND_OCR_RAW:
        relation_text = build_local_relation_description(text) or text

    enhanced = parse_genealogy_text_enhanced(
        relation_text,
        generation_scheme=generation_scheme,
        generation_epoch_offset=generation_epoch_offset,
    )
    parsed_persons = enhanced.get("persons") or []
    parsed_relations = enhanced.get("relations") or []

    built = auto_build_genealogy(relation_text, parsed_persons, parsed_relations, style=style)
    if not built.get("success") and not built.get("persons"):
        return {
            "success": False,
            "error": "未能从原文识别出人物，请先整理版本二关系描述格式。",
        }

    built_persons = built.get("persons") or []
    built_relations = built.get("relations") or []

    existing_names = {(p.get("name") or "").strip() for p in persons if (p.get("name") or "").strip()}
    current_rel_keys = {_relation_key(r) for r in relations}

    new_persons: list[dict] = []
    seen_new: set[str] = set()
    for p in built_persons:
        name = (p.get("name") or "").strip()
        if not name or name in existing_names or name in seen_new:
            continue
        seen_new.add(name)
        new_persons.append({"name": name})

    relations_add: list[dict] = []
    seen_add: set[tuple[str, str, str]] = set()
    for r in built_relations:
        key = _relation_key(r)
        if not key[0] or not key[1] or key in current_rel_keys or key in seen_add:
            continue
        seen_add.add(key)
        relations_add.append({
            "from": key[0],
            "to": key[1],
            "type": key[2],
            "status": r.get("status") or "inferred",
        })

    parts: list[str] = []
    if new_persons:
        parts.append(f"从「{version_label}」识别到 {len(new_persons)} 位尚未入库的成员")
    if relations_add:
        parts.append(f"可补全 {len(relations_add)} 条关系")
    spouse_n = sum(1 for r in relations_add if r.get("type") == "spouse")
    parent_n = len(relations_add) - spouse_n
    if parent_n:
        parts.append(f"其中父子 {parent_n} 条")
    if spouse_n:
        parts.append(f"配偶 {spouse_n} 条")
    if not parts:
        parts.append(f"「{version_label}」与当前主谱已基本一致，未发现需补项")

    plan = _normalize_plan({
        "explanation": "。".join(parts) + "。以下为本地智能分析结果，可一键应用或再点 AI 精修。",
        "relations_add": relations_add,
        "new_persons": new_persons,
        "clean_slate": len(persons) == 0 and bool(new_persons or relations_add),
    })
    plan = reconcile_plan_with_genealogy(plan, persons)
    use_clean = bool(plan.get("clean_slate"))
    merged = merge_plan_into_genealogy(
        persons, relations, plan,
        source_text=text,
        style=style,
        clean_slate=use_clean,
    )
    diff = compute_organize_diff(persons, relations, plan, merged)

    return {
        "success": True,
        "method": "local",
        "source_version_label": version_label,
        "source_version_kind": version_kind,
        "plan": plan,
        "diff": diff,
        "preview": merged,
        "stats": {
            "persons_in_source": len(built_persons),
            "relations_in_source": len(built_relations),
            "persons_to_add": len(diff.get("persons_to_add") or []),
            "relations_to_add": len(diff.get("relations_to_add") or []),
        },
    }
