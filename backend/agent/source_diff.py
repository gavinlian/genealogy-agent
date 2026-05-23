"""族谱主谱与原文（版本）差异对比"""

from __future__ import annotations

from typing import Any

from .genealogy_builder import auto_build_genealogy, parse_genealogy_text_enhanced


def _rel_key(rel: dict) -> tuple[str, str, str] | None:
    fn = (rel.get("from") or rel.get("from_name") or "").strip()
    tn = (rel.get("to") or rel.get("to_name") or "").strip()
    if not fn or not tn:
        return None
    rtype = rel.get("type") or rel.get("relation_type") or "parent_child"
    return fn, tn, rtype


def _relations_to_set(relations: list[dict]) -> set[tuple[str, str, str]]:
    out: set[tuple[str, str, str]] = set()
    for rel in relations:
        key = _rel_key(rel)
        if key:
            out.add(key)
    return out


def _rel_dict(key: tuple[str, str, str], status: str = "inferred") -> dict:
    return {"from": key[0], "to": key[1], "type": key[2], "status": status}


def _type_label(rtype: str) -> str:
    return "配偶" if rtype == "spouse" else "父子"


def compare_parsed_with_genealogy(
    persons: list[dict],
    relations: list[dict],
    parsed_persons: list[dict],
    parsed_relations: list[dict],
) -> dict[str, Any]:
    """对比两阶段解析结果与当前主谱，仅列出可新增项（不直接合并）。"""
    current_names = {p.get("name") for p in persons if p.get("name")}
    parsed_name_set = {p.get("name") for p in parsed_persons if p.get("name")}

    persons_to_add: list[dict] = []
    persons_skipped: list[str] = []
    seen_add: set[str] = set()
    for p in parsed_persons:
        name = (p.get("name") or "").strip()
        if not name:
            continue
        if name in current_names:
            if name not in persons_skipped:
                persons_skipped.append(name)
            continue
        if name in seen_add:
            continue
        seen_add.add(name)
        persons_to_add.append(dict(p))

    current_rel_set = _relations_to_set(relations)
    parsed_rel_rows = []
    for rel in parsed_relations:
        key = _rel_key(rel)
        if key:
            parsed_rel_rows.append(_rel_dict(key, rel.get("status") or "inferred"))
    parsed_rel_set = _relations_to_set(parsed_rel_rows)

    effective_names = current_names | parsed_name_set
    relations_to_add: list[dict] = []
    relations_skipped: list[dict] = []
    relations_unresolved: list[dict] = []
    for rel in parsed_rel_rows:
        key = _rel_key(rel)
        if not key:
            continue
        fn, tn, _ = key
        if fn not in effective_names or tn not in effective_names:
            relations_unresolved.append(rel)
            continue
        if key in current_rel_set:
            relations_skipped.append(rel)
            continue
        if key in _relations_to_set(relations_to_add):
            continue
        relations_to_add.append(rel)

    extra_persons = sorted(current_names - parsed_name_set)

    hints: list[str] = []
    if persons_to_add:
        names = [p.get("name") for p in persons_to_add if p.get("name")]
        hints.append(
            f"解析结果中有 {len(persons_to_add)} 名将新增到主谱：{'、'.join(names[:8])}"
            + ("…" if len(names) > 8 else "")
        )
    if persons_skipped:
        hints.append(
            f"主谱已存在 {len(persons_skipped)} 人，不会重复入库：{'、'.join(persons_skipped[:8])}"
            + ("…" if len(persons_skipped) > 8 else "")
        )
    if relations_to_add:
        sample = relations_to_add[:3]
        hints.append(
            "将新增关系："
            + "；".join(f"{r['from']}→{r['to']}（{_type_label(r['type'])}）" for r in sample)
            + ("…" if len(relations_to_add) > 3 else "")
        )
    if relations_skipped:
        hints.append(f"已有 {len(relations_skipped)} 条关系与主谱相同，将跳过")
    if relations_unresolved:
        hints.append(
            f"有 {len(relations_unresolved)} 条关系因成员未齐暂未纳入（需先入库相关人物）"
        )
    if extra_persons and parsed_name_set:
        hints.append(
            f"主谱另有 {len(extra_persons)} 人未出现在本次解析中（不会被删除）"
        )

    has_changes = bool(persons_to_add or relations_to_add)

    return {
        "compare_mode": "parse_import",
        "has_source": True,
        "current": {
            "person_count": len(current_names),
            "relation_count": len(current_rel_set),
        },
        "from_source": {
            "person_count": len(parsed_name_set),
            "relation_count": len(parsed_rel_set),
        },
        "persons_to_add": [p.get("name") for p in persons_to_add if p.get("name")],
        "persons_to_add_detail": persons_to_add,
        "persons_skipped": sorted(persons_skipped),
        "relations_to_add": relations_to_add,
        "relations_skipped": relations_skipped,
        "relations_unresolved": relations_unresolved,
        "missing_persons": [p.get("name") for p in persons_to_add if p.get("name")],
        "missing_relations": relations_to_add,
        "extra_persons": extra_persons,
        "proposed_relations": relations_to_add,
        "hints": hints,
        "aligned": not has_changes,
        "issues_count": len(persons_to_add) + len(relations_to_add) + len(relations_unresolved),
        "persons_to_add_count": len(persons_to_add),
        "relations_to_add_count": len(relations_to_add),
    }


def compare_genealogy_with_source(
    persons: list[dict],
    relations: list[dict],
    source_text: str,
    *,
    source_version: dict | None = None,
    style: str = "su",
) -> dict[str, Any]:
    """对比当前入库主谱与原文解析期望之间的差异。"""
    text = (source_text or "").strip()
    version_info = None
    if source_version:
        version_info = {
            "id": source_version.get("id"),
            "label": source_version.get("label"),
            "version_no": source_version.get("version_no"),
            "status": source_version.get("status"),
        }

    current_names = {p.get("name") for p in persons if p.get("name")}
    current_rel_rows = []
    for rel in relations:
        key = _rel_key(rel)
        if key:
            current_rel_rows.append(_rel_dict(key, rel.get("status") or "confirmed"))
    current_rel_set = _relations_to_set(current_rel_rows)

    if not text:
        return {
            "has_source": False,
            "source_version": version_info,
            "message": "暂无原文或确认版本，无法对比",
            "current": {"person_count": len(current_names), "relation_count": len(current_rel_set)},
            "aligned": True,
            "issues_count": 0,
        }

    parsed = parse_genealogy_text_enhanced(text)
    from_source = auto_build_genealogy(
        text,
        parsed.get("persons") or [],
        parsed.get("relations") or [],
        style=style,
    )
    expected_persons = from_source.get("persons") or []
    expected_relations = from_source.get("relations") or []
    expected_names = {p.get("name") for p in expected_persons if p.get("name")}
    expected_rel_set = _relations_to_set(expected_relations)

    missing_persons = sorted(expected_names - current_names)
    extra_persons = sorted(current_names - expected_names)

    missing_relations = [
        _rel_dict(k) for k in sorted(expected_rel_set - current_rel_set)
    ]
    extra_relations = [
        _rel_dict(k, "confirmed") for k in sorted(current_rel_set - expected_rel_set)
    ]

    rebuilt = auto_build_genealogy(text, persons, current_rel_rows, style=style)
    proposed_relations: list[dict] = []
    for rel in rebuilt.get("relations") or []:
        key = _rel_key(rel)
        if key and key not in current_rel_set:
            proposed_relations.append({
                "from": key[0],
                "to": key[1],
                "type": key[2],
                "status": rel.get("status") or "inferred",
            })

    hints: list[str] = []
    if missing_persons:
        hints.append(f"原文中有 {len(missing_persons)} 个姓名尚未录入主谱：{'、'.join(missing_persons[:8])}{'…' if len(missing_persons) > 8 else ''}")
    if extra_persons:
        hints.append(f"主谱中有 {len(extra_persons)} 人未在原文解析中出现：{'、'.join(extra_persons[:8])}{'…' if len(extra_persons) > 8 else ''}")
    if missing_relations:
        sample = missing_relations[:3]
        hints.append(
            "原文暗示但主谱缺失的关系："
            + "；".join(f"{r['from']}→{r['to']}（{_type_label(r['type'])}）" for r in sample)
            + ("…" if len(missing_relations) > 3 else "")
        )
    if extra_relations:
        sample = extra_relations[:3]
        hints.append(
            "主谱有但原文未体现的关系："
            + "；".join(f"{r['from']}→{r['to']}（{_type_label(r['type'])}）" for r in sample)
            + ("…" if len(extra_relations) > 3 else "")
        )
    if proposed_relations:
        hints.append(f"快速整理可补全 {len(proposed_relations)} 条关系")

    issues_count = (
        len(missing_persons) + len(extra_persons)
        + len(missing_relations) + len(extra_relations)
    )
    aligned = issues_count == 0 and not proposed_relations

    return {
        "has_source": True,
        "source_version": version_info,
        "source_length": len(text),
        "current": {
            "person_count": len(current_names),
            "relation_count": len(current_rel_set),
        },
        "from_source": {
            "person_count": len(expected_names),
            "relation_count": len(expected_rel_set),
        },
        "missing_persons": missing_persons,
        "extra_persons": extra_persons,
        "missing_relations": missing_relations,
        "extra_relations": extra_relations,
        "proposed_relations": proposed_relations,
        "hints": hints,
        "aligned": aligned,
        "issues_count": issues_count,
    }
