"""将 OCR/族谱原文转为关系描述稿（文字版），供整理与 AI 使用。"""

from __future__ import annotations

from .genealogy_builder import parse_genealogy_text_enhanced


def build_local_relation_description(raw_text: str) -> str:
    """本地规则：从原文提取人物与关系，格式化为可读的关系描述稿。"""
    text = (raw_text or "").strip()
    if not text:
        return ""

    # 若已是「A → B」或「A 配 B」风格，直接返回
    sample = text[:800]
    if sample.count("→") >= 2 or sample.count(" 配 ") >= 2:
        return text

    parsed = parse_genealogy_text_enhanced(text)
    persons = parsed.get("persons") or []
    relations = parsed.get("relations") or []
    lines: list[str] = []

    by_gen: dict[int, list[str]] = {}
    for p in persons:
        name = (p.get("name") or "").strip()
        if not name:
            continue
        gen = int(p.get("generation") or 1)
        by_gen.setdefault(gen, []).append(name)

    for gen in sorted(by_gen):
        names = by_gen[gen]
        if len(names) == 1:
            lines.append(f"第{gen}世 {names[0]}")
        else:
            lines.append(f"第{gen}世 " + "、".join(names))

    if relations:
        lines.append("")
        lines.append("【关系】")
        for r in relations:
            fn = (r.get("from") or "").strip()
            tn = (r.get("to") or "").strip()
            if not fn or not tn:
                continue
            if (r.get("type") or "parent_child") == "spouse":
                lines.append(f"{fn} 配 {tn}")
            else:
                lines.append(f"{fn} → {tn}（父子）")

    if lines:
        return "\n".join(lines).strip()
    return text
