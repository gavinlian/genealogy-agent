"""多页 PDF 批量 OCR。"""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from agent.pipeline import run_ocr_only
from pdf_import import merge_page_texts, pdf_pages_to_jpeg_base64


async def run_pdf_ocr_pipeline(
    pdf_bytes: bytes,
    *,
    ocr_provider: str,
    ocr_model: str,
    ocr_fn: Callable[[str, str, str, str], Awaitable[tuple[str, str]]],
    page_from: int = 1,
    page_to: int | None = None,
    dpi: int = 160,
) -> dict[str, Any]:
    pages = pdf_pages_to_jpeg_base64(
        pdf_bytes,
        dpi=dpi,
        page_from=page_from,
        page_to=page_to,
    )
    if not pages:
        return {"success": False, "error": "未能从 PDF 提取页面", "step": "pdf"}

    preview_image_base64 = pages[0].get("image_base64")

    page_results: list[dict[str, Any]] = []
    errors: list[str] = []

    for pg in pages:
        result = await run_ocr_only(
            pg["image_base64"],
            ocr_provider=ocr_provider,
            ocr_model=ocr_model,
            ocr_fn=ocr_fn,
        )
        if not result.get("success"):
            errors.append(f"第{pg['page']}页：{result.get('error') or 'OCR 失败'}")
            page_results.append({"page": pg["page"], "text": "", "success": False})
            continue
        page_results.append({
            "page": pg["page"],
            "text": result.get("text") or "",
            "success": True,
            "width": pg.get("width"),
            "height": pg.get("height"),
        })

    merged = merge_page_texts(page_results)
    ok_pages = sum(1 for p in page_results if p.get("success") and (p.get("text") or "").strip())

    if not merged.strip():
        return {
            "success": False,
            "error": "；".join(errors[:3]) or "所有页面 OCR 均未识别到文字",
            "step": "ocr",
            "page_count": len(pages),
            "pages": page_results,
        }

    return {
        "success": True,
        "step": "pdf_ocr",
        "text": merged,
        "page_count": len(pages),
        "pages_recognized": ok_pages,
        "pages": page_results,
        "page_errors": errors,
        "preview_image_base64": preview_image_base64,
        "ocr": {"provider": ocr_provider, "model": ocr_model},
    }
