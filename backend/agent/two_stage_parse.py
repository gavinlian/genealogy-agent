"""族谱两阶段解析：OCR 原文 → 关系描述稿 → 数字化 JSON。"""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from .genealogy_builder import auto_build_genealogy
from .genealogy_prompts import build_digitize_prompt, build_relation_describe_prompt
from .name_extractor import refine_persons_list, score_name_confidence
from .parser import extract_json_content, parse_genealogy_text
from .review import annotate_persons_for_review, annotate_relations_for_review
from .validators import validate_genealogy_persons, validate_relations

ParseFn = Callable[[str], Awaitable[tuple[str, str]]]


async def run_two_stage_genealogy_parse(
    raw_text: str,
    parse_fn: ParseFn,
    *,
    skip_describe: bool = False,
) -> dict[str, Any]:
    """两阶段解析族谱文字，返回人物、关系及中间关系描述稿。"""
    raw_text = (raw_text or "").strip()
    if not raw_text:
        return {
            "success": True,
            "persons": [],
            "relations": [],
            "relation_description": "",
            "raw_text": "",
            "parse_steps": [],
        }

    relation_description = ""
    describe_warning: str | None = None
    digitize_warning: str | None = None
    used_ai_describe = False
    used_ai_digitize = False
    parse_steps: list[str] = []

    relation_text = raw_text
    if not skip_describe:
        parse_steps.append("describe")
        prompt1 = build_relation_describe_prompt(raw_text)
        content1, err1 = await parse_fn(prompt1)
        cleaned1 = (content1 or "").strip()
        if cleaned1 and len(cleaned1) >= 4:
            relation_description = cleaned1
            relation_text = cleaned1
            used_ai_describe = True
        elif err1:
            describe_warning = err1

    parse_steps.append("digitize")
    prompt2 = build_digitize_prompt(relation_text, raw_text)
    content2, err2 = await parse_fn(prompt2)
    parsed = extract_json_content(content2) if content2 else None
    if parsed:
        used_ai_digitize = True
    else:
        parsed = parse_genealogy_text(relation_text or raw_text)
        if err2:
            digitize_warning = f"AI 数字化失败，已用本地规则：{err2}"
        else:
            digitize_warning = "AI 数字化 JSON 解析失败，已用本地规则"

    persons = refine_persons_list(parsed.get("persons", []), raw_text)
    relations = parsed.get("relations", [])

    built = auto_build_genealogy(raw_text, persons, relations)
    persons = built.get("persons", persons)
    relations = built.get("relations", relations)

    person_validation = validate_genealogy_persons(persons)
    relation_validation = validate_relations(persons, relations)
    for p in persons:
        p["ai_confidence"] = score_name_confidence(p, relation_text or raw_text)
    persons = annotate_persons_for_review(persons, person_validation)
    relations = annotate_relations_for_review(relations, relation_validation)

    warnings: list[str] = []
    if describe_warning:
        warnings.append(f"关系描述稿生成失败，已直接用 OCR 原文数字化：{describe_warning}")
    if digitize_warning:
        warnings.append(digitize_warning)

    return {
        "success": built.get("success", True),
        "raw_text": raw_text,
        "relation_description": relation_description,
        "relation_text_used": relation_text,
        "persons": persons,
        "relations": relations,
        "tree_preview": built.get("tree"),
        "genealogy_stats": built.get("stats"),
        "validation": {
            "persons": person_validation,
            "relations": relation_validation,
            "passed": person_validation["valid"] and relation_validation["valid"],
        },
        "parse_steps": parse_steps,
        "used_ai_describe": used_ai_describe,
        "used_ai_digitize": used_ai_digitize,
        "warning": "；".join(warnings) if warnings else None,
        "needs_review": any(p.get("review_status") != "confirmed" for p in persons),
    }
