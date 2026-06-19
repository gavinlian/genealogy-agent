"""族谱原文按页拆分/合并（版本一 OCR、版本二关系描述共用页码）。"""

from __future__ import annotations

import re
from typing import Any

PAGE_HEADER_RE = re.compile(
    r"^===== 第\s*(\d+)\s*(?:页|张)(?:\s*·.*?)?\s*=====\s*$",
    re.MULTILINE,
)


def split_paged_text(text: str) -> list[dict[str, Any]]:
    """将带页码分隔符的全文拆成 [{page, text}, ...]；无分隔符时视为第 1 页。"""
    raw = (text or "").strip()
    if not raw:
        return []

    matches = list(PAGE_HEADER_RE.finditer(raw))
    if not matches:
        return [{"page": 1, "text": raw}]

    out: list[dict[str, Any]] = []
    for idx, match in enumerate(matches):
        page = int(match.group(1))
        start = match.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(raw)
        chunk = raw[start:end].strip()
        out.append({"page": page, "text": chunk})
    return out


def merge_paged_text(pages: list[dict[str, Any]], *, unit: str = "页") -> str:
    """合并分页文本，页码分隔符与 OCR 批量识别一致。"""
    parts: list[str] = []
    for item in pages:
        page = int(item.get("page") or len(parts) + 1)
        text = (item.get("text") or "").strip()
        if not text:
            continue
        parts.append(f"===== 第 {page} {unit} =====\n{text}")
    return "\n\n".join(parts)


def get_page_text(text: str, page: int) -> str:
    for item in split_paged_text(text):
        if int(item.get("page") or 0) == page:
            return (item.get("text") or "").strip()
    return ""


def set_page_text(text: str, page: int, new_text: str) -> str:
    pages = split_paged_text(text)
    if not pages:
        pages = [{"page": 1, "text": ""}]
    found = False
    for item in pages:
        if int(item.get("page") or 0) == page:
            item["text"] = (new_text or "").strip()
            found = True
            break
    if not found:
        pages.append({"page": page, "text": (new_text or "").strip()})
        pages.sort(key=lambda x: int(x.get("page") or 0))
    return merge_paged_text(pages)


def page_count(text: str) -> int:
    pages = split_paged_text(text)
    return max((int(p.get("page") or 0) for p in pages), default=1) if pages else 1
