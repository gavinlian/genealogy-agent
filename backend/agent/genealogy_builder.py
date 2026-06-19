"""
族谱自动整理引擎 — 智能体核心能力之一。

从 OCR/AI 解析的零散人物，自动推理父子、配偶关系，生成可展示的族谱树结构。
无 AI 时也能靠规则引擎整理。
"""

from __future__ import annotations

import re
from typing import Any

from .generation_model import apply_generation_model_to_persons, strip_canonical_generation_tag
from .name_extractor import (
    extract_names_from_line,
    is_valid_person_name,
    normalize_person_name,
    refine_persons_list,
)
from .tree import build_family_tree

CHINESE_GEN_NUM = {
    "一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10,
}


def _parse_generation_from_line(line: str) -> int | None:
    m = re.search(r"第\s*([一二三四五六七八九十百千万\d]+)\s*世", line)
    if not m:
        m = re.search(r"([一二三四五六七八九十]+)\s*世", line)
    if not m:
        m = re.search(r"第\s*(\d+)\s*代", line)
    if not m:
        return None
    token = m.group(1)
    if token.isdigit():
        return int(token)
    if token in CHINESE_GEN_NUM:
        return CHINESE_GEN_NUM[token]
    total = 0
    for ch in token:
        if ch in CHINESE_GEN_NUM:
            total = total * 10 + CHINESE_GEN_NUM[ch]
        elif ch == "十":
            total = max(total, 1) * 10
    return total or None


def _extract_person_from_line(line: str, default_gen: int) -> list[dict]:
    """从一行提取人物（专名人名模块 + 生卒/字辈）"""
    found = extract_names_from_line(line, default_gen)
    if not found:
        return found

    birth_m = (
        re.search(r"(?:生[于]?|出生于?)(\d{4})", line)
        or re.search(r"(\d{4})\s*年[^。\n]{0,8}生", line)
    )
    death_m = (
        re.search(r"卒[于]?(\d{4}|今)", line)
        or re.search(r"(\d{4})\s*年[^。\n]{0,8}卒", line)
    )
    death_year = None
    if death_m:
        token = death_m.group(1)
        death_year = None if token == "今" else int(token)
    courtesy_m = re.search(r"字\s*([\u4e00-\u9fff]{1,4})", line)
    art_m = re.search(r"号\s*([\u4e00-\u9fff]{2,6})", line)

    from .source_person_sync import extract_line_profile_fields
    line_profile = extract_line_profile_fields(line)

    for entry in found:
        for key, val in line_profile.items():
            if entry.get(key) in (None, "", "unknown"):
                entry[key] = val
        if entry.get("_role") == "main":
            if birth_m and not entry.get("birth_year"):
                entry["birth_year"] = int(birth_m.group(1))
            if death_year is not None and not entry.get("death_year"):
                entry["death_year"] = death_year
            if courtesy_m and not entry.get("courtesy_name"):
                cn = normalize_person_name(courtesy_m.group(1))
                if cn and cn != entry.get("name") and is_valid_person_name(cn, allow_single_char=True):
                    entry["courtesy_name"] = cn
            if art_m and not entry.get("art_name"):
                an = normalize_person_name(art_m.group(1))
                if an and is_valid_person_name(an, allow_single_char=True):
                    entry["art_name"] = an
            cleaned = line.strip()
            if len(cleaned) > len(entry.get("name") or "") + 2 and not entry.get("biography"):
                if any(kw in cleaned for kw in ("生", "卒", "字", "号", "配", "葬")):
                    entry["biography"] = cleaned[:500]
    return found


def parse_genealogy_text_enhanced(
    text: str,
    *,
    generation_scheme: str = "absolute",
    generation_epoch_offset: int = 1,
) -> dict:
    """增强版本地解析：世代 + 行内关系 + 父子链；支持 [全世N] 与支谱 offset。"""
    persons: list[dict] = []
    relations: list[dict] = []
    generation = 1
    last_main_by_gen: dict[int, str] = {}
    order = 0

    for raw_line in text.strip().split("\n"):
        line = raw_line.strip()
        if not line or line.startswith("====="):
            continue

        line, canonical_override = strip_canonical_generation_tag(line)

        gen_from_line = _parse_generation_from_line(line)
        if gen_from_line is not None:
            generation = gen_from_line
            line = re.sub(
                r"^(?:第\s*)?[一二三四五六七八九十百千万\d]+\s*[世代]\s*",
                "",
                line,
            ).strip()
            if not line:
                continue

        if any(kw in line for kw in ["族谱", "碑记", "序言"]) and len(line) <= 8:
            continue

        source_gen = generation

        wife_only = re.match(r"^配\s*([\u4e00-\u9fff]{2,4})", line)
        if wife_only:
            spouse_name = normalize_person_name(wife_only.group(1))
            if not is_valid_person_name(spouse_name):
                continue
            parent_name = last_main_by_gen.get(generation)
            if parent_name:
                gen_val = canonical_override if canonical_override is not None else generation
                persons.append({
                    "name": spouse_name,
                    "gender": "female",
                    "generation": gen_val,
                    "source_generation": source_gen,
                    "_order": order,
                })
                order += 1
                relations.append({
                    "from": parent_name,
                    "to": spouse_name,
                    "type": "spouse",
                    "status": "inferred",
                    "confidence": 0.85,
                })
            continue

        entries = _extract_person_from_line(line, generation)
        for entry in entries:
            entry["_order"] = order
            order += 1
            gen_val = canonical_override if canonical_override is not None else entry.get("generation", generation)
            entry["generation"] = gen_val
            entry["source_generation"] = source_gen
            persons.append({k: v for k, v in entry.items() if not k.startswith("_") or k == "_order"})
            role = entry.get("_role")
            name = entry["name"]

            if role == "child" and generation > 1:
                parent_gen = generation - 1
                parent_name = last_main_by_gen.get(parent_gen)
                if parent_name:
                    relations.append({
                        "from": parent_name, "to": name, "type": "parent_child",
                        "status": "inferred", "confidence": 0.8,
                    })
            elif role == "spouse" and last_main_by_gen.get(generation):
                relations.append({
                    "from": last_main_by_gen[generation], "to": name, "type": "spouse",
                    "status": "inferred", "confidence": 0.85,
                })
            elif role == "main":
                last_main_by_gen[generation] = name
                if generation > 1:
                    parent_gen = generation - 1
                    parent_name = last_main_by_gen.get(parent_gen)
                    if parent_name:
                        relations.append({
                            "from": parent_name, "to": name, "type": "parent_child",
                            "status": "inferred", "confidence": 0.75,
                        })

    persons = apply_generation_model_to_persons(
        persons,
        scheme=generation_scheme,
        epoch_offset=generation_epoch_offset,
    )
    return {"persons": persons, "relations": relations}


def dedupe_persons(persons: list[dict]) -> list[dict]:
    seen: dict[str, dict] = {}
    for p in persons:
        name = normalize_person_name(p.get("name") or "")
        if not is_valid_person_name(name):
            continue
        p = dict(p)
        p["name"] = name
        if name in seen:
            old = seen[name]
            for key in ("birth_year", "death_year", "generation", "gender", "generation_name"):
                if p.get(key) is not None and old.get(key) in (None, "", "unknown"):
                    old[key] = p[key]
                elif key == "generation" and p.get(key) and old.get(key):
                    # 合并时取较大世代，避免 text 补漏把 gen 压成 1
                    old["generation"] = max(int(old["generation"]), int(p["generation"]))
        else:
            seen[name] = dict(p)
    return list(seen.values())


def _relation_key(rel: dict) -> tuple:
    return (rel.get("from"), rel.get("to"), rel.get("type") or "parent_child")


def merge_relations(existing: list[dict], inferred: list[dict]) -> list[dict]:
    merged: dict[tuple, dict] = {}
    for r in existing + inferred:
        if not r.get("from") or not r.get("to"):
            continue
        key = _relation_key(r)
        if key not in merged:
            merged[key] = dict(r)
        else:
            if r.get("status") == "confirmed":
                merged[key]["status"] = "confirmed"
                merged[key]["confidence"] = 1.0
    return list(merged.values())


def infer_relations_by_generation(
    persons: list[dict],
    existing: list[dict] | None = None,
) -> list[dict]:
    """按世代顺序：下一代第一个人连上一代最后一个主系人物"""
    existing = existing or []
    existing_children = {
        r.get("to") for r in existing if r.get("type") == "parent_child" and r.get("to")
    }
    by_gen: dict[int, list[dict]] = {}
    for p in persons:
        g = int(p.get("generation") or 1)
        by_gen.setdefault(g, []).append(p)

    relations = []
    gens = sorted(by_gen.keys())
    for i in range(1, len(gens)):
        parent_gen, child_gen = gens[i - 1], gens[i]
        if child_gen != parent_gen + 1:
            continue
        parents = by_gen[parent_gen]
        children = by_gen[child_gen]
        if not parents or not children:
            continue
        # 上一代：优先男性，否则最后一个
        parent = next((p for p in reversed(parents) if p.get("gender") == "male"), parents[-1])
        parent_name = parent.get("name")
        child_names_with_parent = {
            r.get("to") for r in relations
            if r.get("type") == "parent_child" and r.get("from")
        }
        for child in children:
            cname = child.get("name")
            if cname in child_names_with_parent or cname in existing_children:
                continue
            relations.append({
                "from": parent_name,
                "to": child.get("name"),
                "type": "parent_child",
                "status": "inferred",
                "confidence": 0.7,
            })
    return relations


def infer_relations_from_child_roles(persons: list[dict], text: str) -> list[dict]:
    relations = []
    for line in text.split("\n"):
        parent_m = re.search(r"([\u4e00-\u9fff]{2,4}).*?(?:子|儿|孫|孙)\s*([\u4e00-\u9fff]{2,4})", line)
        if parent_m:
            parent_name = normalize_person_name(parent_m.group(1))
            child_name = normalize_person_name(parent_m.group(2))
            if not is_valid_person_name(parent_name) or not is_valid_person_name(child_name):
                continue
            relations.append({
                "from": parent_name,
                "to": child_name,
                "type": "parent_child",
                "status": "inferred",
                "confidence": 0.85,
            })
    return relations


def assign_temp_ids(persons: list[dict]) -> list[dict]:
    for i, p in enumerate(persons):
        p["id"] = p.get("id") or f"tmp_{i}_{p.get('name', '')}"
    return persons


def build_tree_preview(persons: list[dict], relations: list[dict], style: str = "su") -> dict:
    persons = assign_temp_ids(persons)
    rels = []
    name_to_id = {p["name"]: p["id"] for p in persons if p.get("name")}
    for r in relations:
        fid = name_to_id.get(r.get("from"))
        tid = name_to_id.get(r.get("to"))
        if fid and tid:
            rels.append({
                "from_person_id": fid,
                "to_person_id": tid,
                "relation_type": r.get("type") or "parent_child",
                "status": r.get("status", "inferred"),
            })
    for p in persons:
        if p.get("parent_id"):
            continue
        parent_name = None
        for r in relations:
            if r.get("to") == p.get("name") and r.get("type") == "parent_child":
                parent_name = r.get("from")
                break
        if parent_name and parent_name in name_to_id:
            p["parent_id"] = name_to_id[parent_name]

    return build_family_tree(persons, rels, style=style)


def auto_build_genealogy(
    text: str = "",
    persons: list[dict] | None = None,
    relations: list[dict] | None = None,
    *,
    style: str = "su",
    generation_scheme: str = "absolute",
    generation_epoch_offset: int = 1,
) -> dict[str, Any]:
    """
    自动整理族谱：合并 AI/规则解析结果，推理缺失关系，生成树预览。
    """
    persons = list(persons or [])
    relations = list(relations or [])

    if text:
        persons = refine_persons_list(persons, text)

    if text and len(persons) < 2:
        parsed = parse_genealogy_text_enhanced(
            text,
            generation_scheme=generation_scheme,
            generation_epoch_offset=generation_epoch_offset,
        )
        persons = parsed.get("persons", [])
        relations = parsed.get("relations", [])

    if text and not relations:
        enhanced = parse_genealogy_text_enhanced(
            text,
            generation_scheme=generation_scheme,
            generation_epoch_offset=generation_epoch_offset,
        )
        persons = dedupe_persons(persons + enhanced.get("persons", []))
        relations = relations + enhanced.get("relations", [])

    persons = dedupe_persons(persons)
    if not persons:
        return {
            "success": False,
            "error": "未识别到可整理的人物",
            "persons": [],
            "relations": [],
            "tree": build_family_tree([], [], style=style),
            "stats": {"person_count": 0, "relation_count": 0, "generation_count": 0},
        }

    for p in persons:
        if not p.get("generation"):
            p["generation"] = 1

    inferred: list[dict] = []
    inferred.extend(infer_relations_by_generation(persons, relations))
    inferred.extend(infer_relations_from_child_roles(persons, text))
    all_relations = merge_relations(relations, inferred)

    tree = build_tree_preview(persons, all_relations, style=style)
    gens = {p.get("generation") for p in persons}

    return {
        "success": True,
        "persons": persons,
        "relations": all_relations,
        "tree": tree,
        "stats": {
            "person_count": len(persons),
            "relation_count": len(all_relations),
            "generation_count": len(gens),
            "parent_child_count": sum(1 for r in all_relations if r.get("type") == "parent_child"),
            "spouse_count": sum(1 for r in all_relations if r.get("type") == "spouse"),
            "inferred_count": sum(1 for r in all_relations if r.get("status") == "inferred"),
            "root_count": tree.get("root_count", 0),
        },
    }
