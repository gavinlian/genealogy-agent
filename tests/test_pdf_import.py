"""PDF 导入工具测试（需 pymupdf）。"""

import base64
import pytest

from pdf_import import get_pdf_info, merge_page_texts, normalize_pdf_base64, pdf_pages_to_jpeg_base64


def _minimal_pdf_bytes() -> bytes:
    fitz = pytest.importorskip("fitz")
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "测试族谱第一页")
    data = doc.tobytes()
    doc.close()
    return data


def test_normalize_pdf_base64_accepts_data_url():
    raw = base64.b64encode(_minimal_pdf_bytes()).decode("ascii")
    data = normalize_pdf_base64(f"data:application/pdf;base64,{raw}")
    assert data.startswith(b"%PDF")


def test_get_pdf_info_and_render_page():
    pdf_bytes = _minimal_pdf_bytes()
    info = get_pdf_info(pdf_bytes)
    assert info["page_count"] == 1

    pages = pdf_pages_to_jpeg_base64(pdf_bytes, dpi=100)
    assert len(pages) == 1
    assert pages[0]["page"] == 1
    assert pages[0]["image_base64"]
    assert pages[0]["width"] > 0


def test_merge_page_texts_with_markers():
    merged = merge_page_texts([
        {"page": 1, "text": "张三 长子"},
        {"page": 2, "text": "李四 次子"},
    ])
    assert "===== 第 1 页 =====" in merged
    assert "===== 第 2 页 =====" in merged
    assert "张三" in merged and "李四" in merged
