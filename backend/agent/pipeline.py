"""扫描建谱流水线：OCR → 关系描述 → 数字化 → 校验"""

from typing import Any, Awaitable, Callable

from .genealogy_prompts import OCR_PROMPT
from .two_stage_parse import run_two_stage_genealogy_parse

# 向后兼容导出
PARSE_PROMPT_TEMPLATE = OCR_PROMPT


async def run_ocr_only(
    image_base64: str,
    *,
    ocr_provider: str,
    ocr_model: str,
    ocr_fn: Callable[[str, str, str, str], Awaitable[tuple[str, str]]],
) -> dict[str, Any]:
    """仅 OCR：图片 → 版本一原文（不整理关系）。"""
    if not image_base64:
        return {"success": False, "error": "缺少图片数据", "step": "input"}

    recognized_text, ocr_error = await ocr_fn(ocr_provider, ocr_model, image_base64, OCR_PROMPT)
    if ocr_error:
        return {
            "success": False,
            "error": ocr_error,
            "step": "ocr",
            "provider": ocr_provider,
            "model": ocr_model,
        }

    raw_text = recognized_text.strip()
    if not raw_text:
        return {
            "success": False,
            "error": "OCR 未识别到文字",
            "step": "ocr",
            "provider": ocr_provider,
            "model": ocr_model,
        }

    return {
        "success": True,
        "step": "ocr",
        "text": raw_text,
        "ocr": {"provider": ocr_provider, "model": ocr_model},
    }


async def run_scan_pipeline(
    image_base64: str,
    *,
    ocr_provider: str,
    ocr_model: str,
    parse_provider: str,
    parse_model: str,
    ocr_fn: Callable[[str, str, str, str], Awaitable[tuple[str, str]]],
    parse_fn: Callable[[str, str, str], Awaitable[tuple[str, str]]],
) -> dict[str, Any]:
    """
    族谱智能体核心任务：扫描建谱。
    ocr_fn(provider, model, image_b64, prompt) -> (text, error)
    parse_fn(provider, model, prompt) -> (content, error)
    """
    if not image_base64:
        return {"success": False, "error": "缺少图片数据", "step": "input"}

    recognized_text, ocr_error = await ocr_fn(ocr_provider, ocr_model, image_base64, OCR_PROMPT)
    if ocr_error:
        return {
            "success": False,
            "error": ocr_error,
            "step": "ocr",
            "provider": ocr_provider,
            "model": ocr_model,
        }

    raw_text = recognized_text.strip()
    if not raw_text:
        return {
            "success": False,
            "error": "OCR 未识别到文字",
            "step": "ocr",
            "provider": ocr_provider,
            "model": ocr_model,
        }

    async def text_parse_fn(prompt: str) -> tuple[str, str]:
        return await parse_fn(parse_provider, parse_model, prompt)

    parsed = await run_two_stage_genealogy_parse(raw_text, text_parse_fn)

    return {
        "success": parsed.get("success", True),
        "step": "complete",
        "text": raw_text,
        "relation_description": parsed.get("relation_description", ""),
        "relation_text_used": parsed.get("relation_text_used", raw_text),
        "persons": parsed.get("persons", []),
        "relations": parsed.get("relations", []),
        "needs_review": parsed.get("needs_review", False),
        "ocr": {"provider": ocr_provider, "model": ocr_model},
        "parse": {
            "provider": parse_provider,
            "model": parse_model,
            "used_ai": parsed.get("used_ai_digitize", False),
            "used_ai_describe": parsed.get("used_ai_describe", False),
            "steps": parsed.get("parse_steps", []),
        },
        "validation": parsed.get("validation"),
        "warning": parsed.get("warning"),
        "tree_preview": parsed.get("tree_preview"),
        "genealogy_stats": parsed.get("genealogy_stats"),
    }
