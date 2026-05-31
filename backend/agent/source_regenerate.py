"""原文版本 AI 重生：版本一 OCR、版本二关系描述。"""

from __future__ import annotations

import base64
import os
from typing import Any, Awaitable, Callable

from agent.genealogy_prompts import build_relation_describe_prompt
from agent.pipeline import run_ocr_only
from agent.relation_text import build_local_relation_description
from source_versions import (
    VERSION_KIND_CUSTOM,
    VERSION_KIND_OCR_RAW,
    VERSION_KIND_RELATION_DESC,
    find_version_by_kind,
    upsert_version_by_kind,
)

VisionFn = Callable[[str, str, str, str], Awaitable[tuple[str, str]]]
TextFn = Callable[..., Awaitable[tuple[str, str]]]


async def regenerate_ocr_raw(
    cursor,
    family_id: str,
    upload_dir: str,
    *,
    ocr_provider: str,
    ocr_model: str,
    vision_fn: VisionFn,
) -> dict[str, Any]:
    """从版本一关联的扫描图重新 OCR，覆盖版本一文字。"""
    v1 = find_version_by_kind(cursor, family_id, VERSION_KIND_OCR_RAW)
    if not v1:
        return {"success": False, "error": "尚无版本一，请先在整理页上传族谱扫描图。"}

    image_path = (v1.get("image_path") or "").strip()
    if not image_path:
        return {"success": False, "error": "版本一无扫描图，请先在整理页上传族谱图片后再说「重新识别」。"}

    safe = os.path.basename(image_path)
    filepath = os.path.join(upload_dir, safe)
    if not os.path.isfile(filepath):
        return {"success": False, "error": "扫描图文件丢失，请重新上传图片。"}

    with open(filepath, "rb") as fh:
        image_b64 = base64.b64encode(fh.read()).decode("ascii")

    result = await run_ocr_only(
        image_b64,
        ocr_provider=ocr_provider,
        ocr_model=ocr_model,
        vision_fn=vision_fn,
    )
    if not result.get("success"):
        return {
            "success": False,
            "error": result.get("error") or "OCR 识别失败",
            "step": result.get("step"),
            "used_ai": False,
        }

    text = (result.get("text") or "").strip()
    if not text:
        return {"success": False, "error": "OCR 未识别到文字，请检查图片是否清晰。", "used_ai": False}

    version = upsert_version_by_kind(
        cursor,
        family_id,
        VERSION_KIND_OCR_RAW,
        source_text=text,
        status="confirmed",
    )
    return {
        "success": True,
        "kind": VERSION_KIND_OCR_RAW,
        "text": text,
        "char_count": len(text),
        "version": version,
        "used_ai": True,
        "provider": ocr_provider,
        "model": ocr_model,
    }


async def regenerate_relation_desc(
    cursor,
    family_id: str,
    *,
    parse_provider: str,
    parse_model: str,
    text_fn: TextFn,
    ocr_text: str | None = None,
    target_kind: str = VERSION_KIND_RELATION_DESC,
    context_notes: str = "",
    previous_draft: str = "",
    allow_rule_fallback: bool = True,
) -> dict[str, Any]:
    """用 AI（+可选规则降级）从版本一 OCR 重新生成关系描述，并写入版本库。"""
    raw = (ocr_text or "").strip()
    v1 = find_version_by_kind(cursor, family_id, VERSION_KIND_OCR_RAW)
    if not raw and v1:
        raw = (v1.get("source_text") or "").strip()
    if not raw:
        return {
            "success": False,
            "error": "请先保存版本一 OCR 原文（或上传扫描图并识别），再说「重新生成关系描述」。",
            "used_ai": False,
        }

    kind = target_kind if target_kind in (VERSION_KIND_RELATION_DESC, VERSION_KIND_CUSTOM) else VERSION_KIND_RELATION_DESC
    ai_error = ""
    relation_text = ""

    prompt = build_relation_describe_prompt(
        raw,
        context_notes=context_notes,
        previous_draft=previous_draft,
    )
    content, err = await text_fn(parse_provider, parse_model, prompt)
    relation_text = (content or "").strip()
    if not relation_text or len(relation_text) < 4:
        ai_error = err or "AI 未能生成关系描述稿"
        if allow_rule_fallback:
            relation_text = build_local_relation_description(raw)
        if not relation_text or len(relation_text) < 4:
            return {
                "success": False,
                "error": ai_error or "无法生成关系描述稿。请在设置中配置 API Key，或手工编辑关系文字。",
                "used_ai": False,
                "ai_error": ai_error,
            }

    used_ai = not ai_error and bool(content and len(content.strip()) >= 4)
    fallback_reason = ""
    if ai_error and relation_text:
        fallback_reason = f"AI 不可用（{ai_error}），已用本地规则引擎生成草稿，请核对后保存。"

    v1_id = v1["id"] if v1 else None
    if not v1_id:
        v1_row = upsert_version_by_kind(
            cursor,
            family_id,
            VERSION_KIND_OCR_RAW,
            source_text=raw,
            status="confirmed",
        )
        v1_id = v1_row["id"]

    version = upsert_version_by_kind(
        cursor,
        family_id,
        kind,
        source_text=relation_text,
        parent_version_id=v1_id,
        status="draft",
        set_active=kind == VERSION_KIND_RELATION_DESC,
    )
    label = "版本二 · 关系描述" if kind == VERSION_KIND_RELATION_DESC else "版本三 · 修正稿"
    return {
        "success": True,
        "kind": kind,
        "text": relation_text,
        "relation_description": relation_text,
        "char_count": len(relation_text),
        "version": version,
        "used_ai": used_ai,
        "provider": parse_provider if used_ai else "local_rules",
        "model": parse_model if used_ai else "genealogy_builder",
        "fallback_reason": fallback_reason,
        "ai_error": ai_error or None,
        "message": (
            f"已用 AI（{parse_provider}/{parse_model}）生成【{label}】，共 {len(relation_text)} 字。"
            if used_ai
            else fallback_reason or f"已生成【{label}】草稿，共 {len(relation_text)} 字。"
        ),
    }


def preview_excerpt(text: str, limit: int = 280) -> str:
    t = (text or "").strip()
    if len(t) <= limit:
        return t
    return t[:limit] + "…"
