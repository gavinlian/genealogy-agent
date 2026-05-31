"""多版本原文融合：汇总各版文字、合并人物关系、生成逐步叙述稿。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from agent.genealogy_builder import parse_genealogy_text_enhanced
from agent.relation_text import build_local_relation_description
from source_versions import (
    DEFAULT_LABELS,
    VERSION_KIND_CUSTOM,
    VERSION_KIND_FUSION,
    VERSION_KIND_OCR_RAW,
    VERSION_KIND_RELATION_DESC,
    list_source_versions,
    upsert_version_by_kind,
)

# 融合时各版本优先级（数字越大越优先采信字段）
_KIND_PRIORITY = {
    VERSION_KIND_OCR_RAW: 1,
    VERSION_KIND_RELATION_DESC: 2,
    VERSION_KIND_CUSTOM: 3,
    VERSION_KIND_FUSION: 4,
    "tree": 5,
    "legacy": 0,
}


def _kind_label(kind: str | None, label: str | None) -> str:
    if label:
        return label.strip()
    return DEFAULT_LABELS.get(kind or "", kind or "原文版本")


def _extract_relations_from_text(text: str) -> tuple[list[dict], list[dict]]:
    """从一段原文解析人物与关系。"""
    text = (text or "").strip()
    if not text:
        return [], []
    rel_text = build_local_relation_description(text)
    parsed = parse_genealogy_text_enhanced(rel_text or text)
    persons = parsed.get("persons") or []
    relations = parsed.get("relations") or []
    return persons, relations


def _relation_key(rel: dict) -> tuple[str, str, str]:
    fn = (rel.get("from") or rel.get("from_name") or "").strip()
    tn = (rel.get("to") or rel.get("to_name") or "").strip()
    rtype = (rel.get("type") or rel.get("relation_type") or "parent_child").strip() or "parent_child"
    return fn, tn, rtype


def _merge_relations(
    sources: list[tuple[str, list[dict]]],
) -> list[dict]:
    bucket: dict[tuple[str, str, str], dict] = {}
    for source_label, rels in sources:
        for r in rels:
            fn, tn, rtype = _relation_key(r)
            if not fn or not tn:
                continue
            key = (fn, tn, rtype)
            if key not in bucket:
                bucket[key] = {
                    "from": fn,
                    "to": tn,
                    "type": rtype,
                    "sources": [],
                    "status": r.get("status") or "inferred",
                }
            if source_label not in bucket[key]["sources"]:
                bucket[key]["sources"].append(source_label)
    out = list(bucket.values())
    out.sort(key=lambda x: (x["from"], x["to"], x["type"]))
    return out


def _merge_persons(
    sources: list[tuple[str, int, list[dict]]],
) -> list[dict]:
    """按姓名合并人物，高优先级版本覆盖空字段。"""
    by_name: dict[str, dict] = {}
    for source_label, _priority, persons in sorted(sources, key=lambda x: x[1]):
        for p in persons:
            name = (p.get("name") or "").strip()
            if not name:
                continue
            if name not in by_name:
                by_name[name] = {"name": name, "sources": []}
            row = by_name[name]
            if source_label not in row["sources"]:
                row["sources"].append(source_label)
            for field in (
                "generation", "generation_name", "gender", "birth_year", "death_year",
                "courtesy_name", "art_name",
            ):
                val = p.get(field)
                if val is not None and val != "":
                    row[field] = val
    return sorted(by_name.values(), key=lambda x: (x.get("generation") or 999, x.get("name") or ""))


def _relations_from_tree(
    persons: list[dict],
    relations: list[dict],
) -> list[dict]:
    id_to_name = {p["id"]: p.get("name", "") for p in persons if p.get("id")}
    out: list[dict] = []
    for r in relations:
        fn = id_to_name.get(r.get("from_person_id") or r.get("from_id") or "", "")
        tn = id_to_name.get(r.get("to_person_id") or r.get("to_id") or "", "")
        if not fn or not tn:
            continue
        out.append({
            "from": fn,
            "to": tn,
            "type": r.get("relation_type") or r.get("type") or "parent_child",
            "status": r.get("status") or "confirmed",
        })
    return out


def _format_relation_line(rel: dict) -> str:
    fn, tn = rel["from"], rel["to"]
    sources = "、".join(rel.get("sources") or [])
    src_note = f"〔{sources}〕" if sources else ""
    if rel.get("type") == "spouse":
        return f"{fn} 配 {tn}{src_note}"
    return f"{fn} → {tn}（父子）{src_note}"


def _build_step_narrative(merged_persons: list[dict], merged_relations: list[dict]) -> str:
    lines: list[str] = []
    by_gen: dict[int, list[dict]] = {}
    for p in merged_persons:
        gen = int(p.get("generation") or 1)
        by_gen.setdefault(gen, []).append(p)

    if by_gen:
        lines.append("按世代梳理（融合各版后）：")
        for gen in sorted(by_gen):
            chunk = by_gen[gen]
            names = []
            for p in chunk:
                n = p["name"]
                extra = []
                if p.get("courtesy_name"):
                    extra.append(f"字{p['courtesy_name']}")
                if p.get("generation_name"):
                    extra.append(p["generation_name"])
                names.append(n + (f"（{'，'.join(extra)}）" if extra else ""))
            lines.append(f"  第{gen}世：" + "、".join(names))

    if merged_relations:
        lines.append("")
        lines.append("关系链（已去重，标注来源版本）：")
        for r in merged_relations[:200]:
            lines.append("  " + _format_relation_line(r))
        if len(merged_relations) > 200:
            lines.append(f"  …共 {len(merged_relations)} 条关系")
    return "\n".join(lines).strip()


def build_source_fusion(
    cursor,
    family_id: str,
    *,
    tree_persons: list[dict] | None = None,
    tree_relations: list[dict] | None = None,
    include_tree: bool = True,
) -> dict[str, Any]:
    """
    提取族谱全部原文版本 + 可选主谱，融合关系并生成逐步文字稿。
    """
    payload = list_source_versions(cursor, family_id)
    versions = payload.get("versions") or []

    version_blocks: list[dict[str, Any]] = []
    relation_sources: list[tuple[str, list[dict]]] = []
    person_sources: list[tuple[str, int, list[dict]]] = []

    kind_order = [VERSION_KIND_OCR_RAW, VERSION_KIND_RELATION_DESC, VERSION_KIND_CUSTOM, VERSION_KIND_FUSION]
    ordered: list[dict] = []
    for k in kind_order:
        ordered.extend([v for v in versions if v.get("version_kind") == k])
    ordered.extend([v for v in versions if v.get("version_kind") not in kind_order])

    for v in ordered:
        kind = v.get("version_kind") or "legacy"
        label = _kind_label(kind, v.get("label"))
        raw = (v.get("source_text") or "").strip()
        if not raw:
            continue
        rel_desc = build_local_relation_description(raw)
        persons, rels = _extract_relations_from_text(raw)
        priority = _KIND_PRIORITY.get(kind, 1)
        version_blocks.append({
            "version_id": v.get("id"),
            "version_kind": kind,
            "label": label,
            "version_no": v.get("version_no"),
            "raw_excerpt": raw[:1200] + ("…" if len(raw) > 1200 else ""),
            "relation_description": rel_desc[:2000] + ("…" if len(rel_desc) > 2000 else ""),
            "person_count": len(persons),
            "relation_count": len(rels),
        })
        if rels:
            relation_sources.append((label, rels))
        if persons:
            person_sources.append((label, priority, persons))

    if include_tree and tree_persons:
        tree_rels = _relations_from_tree(tree_persons, tree_relations or [])
        if tree_rels:
            relation_sources.append(("主谱 · 已入库", tree_rels))
        tree_parsed = [
            {
                "name": p.get("name"),
                "generation": p.get("generation"),
                "generation_name": p.get("generation_name"),
                "gender": p.get("gender"),
                "birth_year": p.get("birth_year"),
                "death_year": p.get("death_year"),
                "courtesy_name": p.get("courtesy_name"),
                "art_name": p.get("art_name"),
            }
            for p in tree_persons
            if (p.get("name") or "").strip()
        ]
        if tree_parsed:
            person_sources.append(("主谱 · 已入库", _KIND_PRIORITY["tree"], tree_parsed))

    merged_relations = _merge_relations(relation_sources)
    merged_persons = _merge_persons(person_sources)
    step_narrative = _build_step_narrative(merged_persons, merged_relations)

    lines: list[str] = [
        "# 族谱多版本融合稿",
        f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
        "## 第一步 · 各版原文摘录",
    ]
    if not version_blocks:
        lines.append("（尚无已保存的原文版本，仅有主谱数据。）")
    else:
        for i, block in enumerate(version_blocks, 1):
            lines.append(f"### {i}. {block['label']}")
            lines.append(block["raw_excerpt"] or "（空）")
            if block.get("relation_description") and block["relation_description"] != block["raw_excerpt"]:
                lines.append("")
                lines.append("**关系描述摘要：**")
                lines.append(block["relation_description"])
            lines.append("")

    lines.append("## 第二步 · 人物关系融合（去重）")
    if merged_relations:
        for r in merged_relations:
            lines.append(_format_relation_line(r))
    else:
        lines.append("（未能从各版原文解析出关系，请检查文本或补充主谱。）")
    lines.append("")
    lines.append("## 第三步 · 逐步叙述")
    lines.append(step_narrative or "（待补充）")
    lines.append("")
    lines.append("## 第四步 · 使用建议")
    lines.append(
        "定稿优先级建议：版本三修正稿 > 版本二关系描述 > 主谱已确认关系 > 版本一 OCR 原文。"
        "保存融合稿后可在「原文」中作为新版本继续校对。"
    )

    stepped_text = "\n".join(lines).strip()

    return {
        "success": True,
        "stepped_text": stepped_text,
        "fusion_text": stepped_text,
        "step_narrative": step_narrative,
        "version_blocks": version_blocks,
        "merged_relations": merged_relations,
        "merged_persons": merged_persons,
        "stats": {
            "version_count": len(version_blocks),
            "merged_relation_count": len(merged_relations),
            "merged_person_count": len(merged_persons),
        },
    }


def save_fusion_as_version(
    cursor,
    family_id: str,
    stepped_text: str,
    *,
    set_active: bool = False,
) -> dict:
    """将融合逐步稿保存为「融合稿」原文版本。"""
    text = (stepped_text or "").strip()
    if not text:
        raise ValueError("融合稿内容为空")
    return upsert_version_by_kind(
        cursor,
        family_id,
        VERSION_KIND_FUSION,
        source_text=text,
        label=DEFAULT_LABELS[VERSION_KIND_FUSION],
        status="draft",
        set_active=set_active,
    )
