"""多页 PDF → 分页图片 → OCR 合并（族谱扫描入库）。"""

from __future__ import annotations

import base64
import re
from typing import Any

MAX_PDF_BYTES = 50 * 1024 * 1024
MAX_PDF_PAGES = 80
DEFAULT_DPI = 160

_DATA_URL_RE = re.compile(r"^data:application/pdf;base64,", re.I)


def normalize_pdf_base64(raw: str) -> bytes:
    text = (raw or "").strip()
    if not text:
        raise ValueError("缺少 PDF 数据")
    text = _DATA_URL_RE.sub("", text)
    text = re.sub(r"\s+", "", text)
    pad = (-len(text)) % 4
    if pad:
        text += "=" * pad
    try:
        data = base64.b64decode(text, validate=True)
    except Exception as exc:
        raise ValueError(f"PDF base64 无效：{exc}") from exc
    if not data:
        raise ValueError("PDF 数据为空")
    if len(data) > MAX_PDF_BYTES:
        raise ValueError(f"PDF 过大（上限 {MAX_PDF_BYTES // (1024 * 1024)}MB）")
    if not data.startswith(b"%PDF"):
        raise ValueError("不是有效的 PDF 文件")
    return data


def _require_pymupdf():
    try:
        import fitz  # pymupdf
    except ImportError as exc:
        raise RuntimeError(
            "服务器未安装 PDF 支持，请在 backend 目录运行：pip install pymupdf"
        ) from exc
    return fitz


def get_pdf_info(pdf_bytes: bytes) -> dict[str, Any]:
    fitz = _require_pymupdf()
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        count = doc.page_count
        if count < 1:
            raise ValueError("PDF 没有可识别的页面")
        if count > MAX_PDF_PAGES:
            raise ValueError(f"PDF 页数过多（{count} 页），当前上限 {MAX_PDF_PAGES} 页，请拆分后上传")
        meta = doc.metadata or {}
        return {
            "page_count": count,
            "title": (meta.get("title") or "").strip(),
        }
    finally:
        doc.close()


def pdf_pages_to_jpeg_base64(
    pdf_bytes: bytes,
    *,
    dpi: int = DEFAULT_DPI,
    page_from: int = 1,
    page_to: int | None = None,
) -> list[dict[str, Any]]:
    """将 PDF 指定页转为 JPEG base64，供 OCR 使用。"""
    fitz = _require_pymupdf()
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        total = doc.page_count
        start = max(1, int(page_from))
        end = int(page_to) if page_to else total
        end = min(end, total)
        if start > end:
            raise ValueError("页码范围无效")
        if end - start + 1 > MAX_PDF_PAGES:
            raise ValueError(f"单次最多处理 {MAX_PDF_PAGES} 页")

        scale = max(72, min(300, int(dpi))) / 72.0
        matrix = fitz.Matrix(scale, scale)
        out: list[dict[str, Any]] = []
        for page_num in range(start, end + 1):
            page = doc.load_page(page_num - 1)
            pix = page.get_pixmap(matrix=matrix, alpha=False)
            img_bytes = pix.tobytes("jpeg")
            out.append({
                "page": page_num,
                "image_base64": base64.b64encode(img_bytes).decode("ascii"),
                "width": pix.width,
                "height": pix.height,
            })
        return out
    finally:
        doc.close()


def merge_page_texts(page_results: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for item in page_results:
        page = item.get("page")
        text = (item.get("text") or "").strip()
        if not text:
            continue
        parts.append(f"===== 第 {page} 页 =====\n{text}")
    return "\n\n".join(parts)
