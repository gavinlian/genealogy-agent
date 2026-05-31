"""Auto 模型调度：平台额度 → 自带 Key → 本地降级。"""

from __future__ import annotations

import os
import sqlite3
from typing import Any, Callable

from agent.ai_plans import get_platform_defaults, get_routes, load_ai_plans, source_label
from agent.ai_quota import can_use_platform_quota, get_quota_summary, pick_tier

CredentialFn = Callable[[str], tuple[str, str, str]]
ConfiguredFn = Callable[[str], bool]

VISION_TASKS = frozenset({"ocr"})


def get_platform_api_key() -> str:
    return (os.environ.get("PLATFORM_AI_API_KEY") or "").strip()


def is_platform_available() -> bool:
    return bool(get_platform_api_key())


def load_routing_settings(cursor: sqlite3.Cursor) -> dict[str, str]:
    row = cursor.execute("SELECT * FROM ai_settings WHERE id = 'default'").fetchone()
    defaults = {
        "routing_mode": "auto",
        "ocr_tier": "auto",
        "parse_tier": "auto",
        "user_plan": "free",
    }
    if not row:
        return defaults
    keys = row.keys() if hasattr(row, "keys") else []
    for key in defaults:
        if key in keys and row[key]:
            defaults[key] = row[key]
    return defaults


def _provider_supports_task(provider_id: str, task: str, ai_providers: dict[str, Any]) -> bool:
    preset = ai_providers.get(provider_id) or {}
    if task in VISION_TASKS:
        return bool(preset.get("supports_vision"))
    return bool(preset.get("text_model") or preset.get("text_models"))


def _candidate_available(
    candidate: dict[str, Any],
    task: str,
    tier: str,
    user_id: str,
    plan_id: str,
    cursor: sqlite3.Cursor,
    is_configured_fn: ConfiguredFn,
    ai_providers: dict[str, Any],
) -> bool:
    provider = candidate.get("provider") or ""
    if not _provider_supports_task(provider, task, ai_providers):
        return False
    source = candidate.get("source") or "byok"
    if source == "platform":
        if not is_platform_available():
            return False
        return can_use_platform_quota(cursor, user_id, task, tier, plan_id)
    if source == "byok":
        return is_configured_fn(provider)
    return False


def resolve_route(
    cursor: sqlite3.Cursor,
    task: str,
    user_id: str,
    *,
    data: dict | None = None,
    ai_providers: dict[str, Any],
    is_configured_fn: ConfiguredFn,
    load_selection_fn: Callable[[], dict],
) -> dict[str, Any]:
    """解析任务应使用的 provider/model。"""
    data = data or {}
    settings = load_routing_settings(cursor)
    routing_mode = (data.get("routing_mode") or settings.get("routing_mode") or "auto").strip()
    plan_id = settings.get("user_plan") or "free"
    tier_pref_key = "ocr_tier" if task == "ocr" else "parse_tier"
    tier_pref = (data.get(tier_pref_key) or settings.get(tier_pref_key) or "auto").strip()

    incoming = data.get(task) or {}
    manual_override = bool(incoming.get("provider") and incoming.get("model"))

    if routing_mode == "manual" or manual_override:
        saved = load_selection_fn()[task]
        provider = incoming.get("provider") or saved["provider"]
        model = incoming.get("model") or saved["model"]
        source = "manual"
        if is_configured_fn(provider):
            return _result(
                provider=provider,
                model=model,
                source=source,
                tier="fast",
                queue_wait_ms=0,
                label=f"{source_label(source)} · {provider}",
                fallback_local=False,
            )
        if task == "parse":
            return _local_fallback("手动指定的模型未配置 Key")
        return _result(
            provider=provider,
            model=model,
            source=source,
            tier="fast",
            queue_wait_ms=0,
            label=f"{source_label(source)} · {provider}",
            fallback_local=False,
            error_hint="未配置 API Key，OCR 无法执行",
        )

    tier, queue_wait_ms = pick_tier(cursor, user_id, task, tier_pref, plan_id)
    routes = get_routes(task).get(tier) or []
    for candidate in routes:
        if _candidate_available(
            candidate, task, tier, user_id, plan_id, cursor, is_configured_fn, ai_providers
        ):
            provider = candidate["provider"]
            model = candidate.get("model") or ""
            platform = get_platform_defaults()
            if candidate.get("source") == "platform":
                if task == "ocr":
                    provider = platform["ocr_provider"]
                    model = platform.get("ocr_model") or model
                else:
                    provider = platform["parse_provider"]
                    model = platform.get("parse_model") or model
            return _result(
                provider=provider,
                model=model,
                source=candidate.get("source") or "platform",
                tier=tier,
                queue_wait_ms=queue_wait_ms,
                label=candidate.get("label") or f"{source_label(candidate.get('source', ''))} · {provider}",
                fallback_local=False,
            )

    if task == "parse":
        return _local_fallback("额度已用尽且未配置 Key，将使用本地规则")

    return _result(
        provider="",
        model="",
        source="none",
        tier=tier,
        queue_wait_ms=queue_wait_ms,
        label="暂无可用模型",
        fallback_local=False,
        error_hint="请配置 API Key 或等待下月额度重置；也可在设置中切换到手动模式",
    )


def _local_fallback(reason: str) -> dict[str, Any]:
    return _result(
        provider="",
        model="",
        source="local",
        tier="slow",
        queue_wait_ms=0,
        label=source_label("local"),
        fallback_local=True,
        error_hint=reason,
    )


def _result(
    *,
    provider: str,
    model: str,
    source: str,
    tier: str,
    queue_wait_ms: int,
    label: str,
    fallback_local: bool,
    error_hint: str = "",
) -> dict[str, Any]:
    return {
        "provider": provider,
        "model": model,
        "source": source,
        "tier": tier,
        "queue_wait_ms": queue_wait_ms,
        "label": label,
        "fallback_local": fallback_local,
        "error_hint": error_hint,
    }


def build_routing_status(
    cursor: sqlite3.Cursor,
    user_id: str,
    *,
    ai_providers: dict[str, Any],
    is_configured_fn: ConfiguredFn,
    load_selection_fn: Callable[[], dict],
) -> dict[str, Any]:
    settings = load_routing_settings(cursor)
    plan_id = settings.get("user_plan") or "free"
    quota = get_quota_summary(cursor, user_id, plan_id)
    cfg = load_ai_plans()
    pro = (cfg.get("plans") or {}).get("pro") or {}

    byok_any = any(is_configured_fn(pid) for pid in ai_providers)
    recommendations: dict[str, Any] = {}
    for task in ("ocr", "parse"):
        routed = resolve_route(
            cursor,
            task,
            user_id,
            ai_providers=ai_providers,
            is_configured_fn=is_configured_fn,
            load_selection_fn=load_selection_fn,
        )
        recommendations[task] = {
            "provider": routed.get("provider"),
            "model": routed.get("model"),
            "source": routed.get("source"),
            "tier": routed.get("tier"),
            "label": routed.get("label"),
            "queue_wait_ms": routed.get("queue_wait_ms", 0),
            "fallback_local": routed.get("fallback_local", False),
            "error_hint": routed.get("error_hint") or "",
        }

    return {
        "routing_mode": settings.get("routing_mode") or "auto",
        "ocr_tier": settings.get("ocr_tier") or "auto",
        "parse_tier": settings.get("parse_tier") or "auto",
        "plan_id": plan_id,
        "quota": quota,
        "platform_available": is_platform_available(),
        "byok_any_configured": byok_any,
        "recommendations": recommendations,
        "pro": {
            "coming_soon": bool(pro.get("coming_soon")),
            "price_monthly_cny": pro.get("price_monthly_cny"),
            "label": pro.get("label") or "Pro",
        },
    }
