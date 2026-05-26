"""OCR 三版文字流水线测试"""

import os
import sqlite3
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from source_versions import (
    VERSION_KIND_CUSTOM,
    VERSION_KIND_OCR_RAW,
    VERSION_KIND_RELATION_DESC,
    ensure_versions_table,
    find_version_by_kind,
    get_digitize_source_for_family,
    save_ocr_scan_versions,
)
from source_version_diff import compare_source_texts


def _mem_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute(
        """CREATE TABLE families (
            id TEXT PRIMARY KEY, name TEXT, source_text TEXT, source_annotations TEXT,
            active_source_version_id TEXT, updated_at TEXT)"""
    )
    c.execute("INSERT INTO families (id, name) VALUES ('f1', '测试')")
    ensure_versions_table(c)
    conn.commit()
    return conn


def test_save_ocr_scan_versions_creates_v1_v2():
    conn = _mem_db()
    c = conn.cursor()
    result = save_ocr_scan_versions(
        c,
        "f1",
        ocr_text="一世 张三",
        relation_description="一世 张三 男",
        custom_text="",
    )
    conn.commit()
    assert result["version_ocr_raw"]["version_kind"] == VERSION_KIND_OCR_RAW
    assert result["version_relation_desc"]["version_kind"] == VERSION_KIND_RELATION_DESC
    assert find_version_by_kind(c, "f1", VERSION_KIND_OCR_RAW)
    assert find_version_by_kind(c, "f1", VERSION_KIND_RELATION_DESC)


def test_save_ocr_scan_versions_with_custom_v3():
    conn = _mem_db()
    c = conn.cursor()
    save_ocr_scan_versions(
        c,
        "f1",
        ocr_text="一世 张三",
        relation_description="一世 张三 男",
        custom_text="一世 张三 男 配李氏",
        active_kind=VERSION_KIND_CUSTOM,
    )
    conn.commit()
    v3 = find_version_by_kind(c, "f1", VERSION_KIND_CUSTOM)
    assert v3
    text, active = get_digitize_source_for_family(c, "f1")
    assert "李氏" in text
    assert active["version_kind"] == VERSION_KIND_CUSTOM


def test_parse_version_note_layout_and_image():
    from source_versions import merge_version_note, parse_version_note

    note = merge_version_note(None, layout="vertical_rl", image_path="abc.jpg")
    assert "layout:vertical_rl" in note
    assert "image:abc.jpg" in note
    parsed = parse_version_note(note)
    assert parsed["layout"] == "vertical_rl"
    assert parsed["image_path"] == "abc.jpg"


def test_save_ocr_scan_versions_with_layout():
    from source_versions import VERSION_KIND_OCR_RAW, find_version_by_kind

    conn = _mem_db()
    c = conn.cursor()
    save_ocr_scan_versions(
        c,
        "f1",
        ocr_text="一世 张三",
        relation_description="一世 张三 男",
        layout_hint="horizontal_rtl",
    )
    conn.commit()
    v1 = find_version_by_kind(c, "f1", VERSION_KIND_OCR_RAW)
    assert v1
    assert "layout:horizontal_rtl" in (v1.get("note") or "")
    assert v1.get("layout_hint") == "horizontal_rtl"

    diff = compare_source_texts("一世 张三", "一世 张三 男 配李氏", label_a="V2", label_b="V3")
    assert diff["lines_a"] == 1
    assert diff["similarity"] < 1.0
    assert diff["diff_lines"]
