"""原文版本之间的文本差异对比。"""

from __future__ import annotations

import difflib


def compare_source_texts(
    text_a: str,
    text_b: str,
    *,
    label_a: str = "版本 A",
    label_b: str = "版本 B",
) -> dict:
    """对比两版原文，返回统计与 unified diff 行。"""
    a_lines = (text_a or "").splitlines()
    b_lines = (text_b or "").splitlines()
    diff_lines = list(
        difflib.unified_diff(
            a_lines,
            b_lines,
            fromfile=label_a,
            tofile=label_b,
            lineterm="",
        )
    )
    matcher = difflib.SequenceMatcher(None, text_a or "", text_b or "")
    ratio = round(matcher.ratio(), 4) if (text_a or text_b) else 1.0
    added = sum(1 for tag, _, _, _, _ in matcher.get_opcodes() if tag == "insert")
    removed = sum(1 for tag, _, _, _, _ in matcher.get_opcodes() if tag == "delete")
    changed = sum(1 for tag, _, _, _, _ in matcher.get_opcodes() if tag == "replace")
    return {
        "similarity": ratio,
        "lines_a": len(a_lines),
        "lines_b": len(b_lines),
        "change_blocks": changed,
        "diff_lines": diff_lines[:500],
        "diff_truncated": len(diff_lines) > 500,
        "summary": f"相似度 {int(ratio * 100)}% · {label_a} {len(a_lines)} 行 → {label_b} {len(b_lines)} 行",
    }
