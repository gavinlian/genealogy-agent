"""多张族谱照片批量 OCR → 合并为版本一原文。"""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from agent.pipeline import run_ocr_only
from pdf_import import merge_page_texts

MAX_BATCH_IMAGES = 40


async def run_batch_ocr_pipeline(
    images_base64: list[str],
    *,
    ocr_provider: str,
    ocr_model: str,
    ocr_fn: Callable[[str, str, str, str], Awaitable[tuple[str, str]]],
) -> dict[str, Any]:
    images = [img for img in images_base64 if (img or "").strip()]
    if not images:
        return {"success": False, "error": "缺少图片数据", "step": "input"}
    if len(images) > MAX_BATCH_IMAGES:
        return {
            "success": False,
            "error": f"单次最多 {MAX_BATCH_IMAGES} 张图片，请分批上传",
            "step": "input",
        }

    page_results: list[dict[str, Any]] = []
    errors: list[str] = []

    for idx, img_b64 in enumerate(images, start=1):
        result = await run_ocr_only(
            img_b64,
            ocr_provider=ocr_provider,
            ocr_model=ocr_model,
            ocr_fn=ocr_fn,
        )
        if not result.get("success"):
            msg = result.get("error") or "OCR 失败"
            errors.append(f"第{idx}张：{msg}")
            page_results.append({"page": idx, "text": "", "success": False})
            continue
        page_results.append({
            "page": idx,
            "text": result.get("text") or "",
            "success": True,
        })

    merged = merge_page_texts(page_results)
    ok_pages = sum(1 for p in page_results if p.get("success") and (p.get("text") or "").strip())

    if not merged.strip():
        return {
            "success": False,
            "error": "；".join(errors[:3]) or "所有图片 OCR 均未识别到文字",
            "step": "ocr",
            "page_count": len(images),
            "pages": page_results,
        }

    return {
        "success": True,
        "step": "batch_ocr",
        "text": merged,
        "page_count": len(images),
        "pages_recognized": ok_pages,
        "pages": page_results,
        "page_errors": errors,
        "ocr": {"provider": ocr_provider, "model": ocr_model},
    }
