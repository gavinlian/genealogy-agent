"""按页拆分/合并测试"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from source_pages import get_page_text, merge_paged_text, set_page_text, split_paged_text


def test_split_and_merge_paged_text():
    merged = merge_paged_text([
        {"page": 1, "text": "第一页 OCR"},
        {"page": 2, "text": "第二页 OCR"},
    ])
    pages = split_paged_text(merged)
    assert len(pages) == 2
    assert pages[0]["text"] == "第一页 OCR"
    assert pages[1]["text"] == "第二页 OCR"


def test_set_page_text_preserves_other_pages():
    full = merge_paged_text([
        {"page": 1, "text": "A"},
        {"page": 2, "text": "B"},
    ])
    updated = set_page_text(full, 2, "B2")
    assert get_page_text(updated, 1) == "A"
    assert get_page_text(updated, 2) == "B2"
