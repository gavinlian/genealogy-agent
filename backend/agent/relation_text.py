"""将 OCR/族谱原文转为关系描述稿（文字版），供整理与 AI 使用。"""

from __future__ import annotations

import re

from .genealogy_builder import parse_genealogy_text_enhanced

_META_LINE_PATTERNS = (
    re.compile(r"^#{1,6}\s"),
    re.compile(r"^```"),
    re.compile(r"^【?(说明|总结|备注|分析|提示)】?"),
    re.compile(r"^(根据|以下|综上|总之|请注意|温馨提示)"),
    re.compile(r"分析如下"),
    re.compile(r"^版本[一二三2-3]\s*[·:：]"),
    re.compile(r"^关系描述稿"),
)


def clean_relation_description(text: str) -> str:
    """去掉 AI 输出的说明/分析段落，保留可解析的关系描述正文。"""
    raw = (text or "").strip()
    if not raw:
        return ""

    cleaned = re.sub(r"^```[\w-]*\s*\n?", "", raw)
    cleaned = re.sub(r"\n?```\s*$", "", cleaned)

    kept: list[str] = []
    blank_pending = False
    for line in cleaned.splitlines():
        stripped = line.strip()
        if not stripped:
            if kept and kept[-1] != "":
                blank_pending = True
            continue
        if any(p.search(stripped) for p in _META_LINE_PATTERNS):
            continue
        if stripped.startswith("【") and stripped.endswith("】") and len(stripped) <= 12:
            if any(k in stripped for k in ("说明", "总结", "分析", "备注")):
                continue
        if blank_pending:
            kept.append("")
            blank_pending = False
        kept.append(line.rstrip())

    out = "\n".join(kept).strip()
    return out or raw


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
