"""加载 config/ai_plans.json — 套餐额度与 Auto 路由链。"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "ai_plans.json"


@lru_cache(maxsize=1)
def load_ai_plans() -> dict[str, Any]:
    if not _CONFIG_PATH.is_file():
        return {}
    with _CONFIG_PATH.open(encoding="utf-8") as fh:
        return json.load(fh)


def get_plan(plan_id: str | None = None) -> dict[str, Any]:
    cfg = load_ai_plans()
    pid = plan_id or cfg.get("default_plan") or "free"
    plans = cfg.get("plans") or {}
    return plans.get(pid) or plans.get("free") or {}


def get_plan_limits(plan_id: str | None = None) -> dict[str, dict[str, int]]:
    plan = get_plan(plan_id)
    return dict(plan.get("limits") or {})


def get_routes(task: str) -> dict[str, list[dict[str, Any]]]:
    cfg = load_ai_plans()
    return dict((cfg.get("routes") or {}).get(task) or {})


def get_platform_defaults() -> dict[str, str]:
    cfg = load_ai_plans()
    platform = dict(cfg.get("platform") or {})
    return {
        "provider": platform.get("provider") or "siliconflow",
        "ocr_provider": platform.get("ocr_provider") or platform.get("provider") or "siliconflow",
        "parse_provider": platform.get("parse_provider") or platform.get("provider") or "siliconflow",
        "ocr_model": platform.get("ocr_model") or "Qwen/Qwen2-VL-72B-Instruct",
        "parse_model": platform.get("parse_model") or "Qwen/Qwen2.5-72B-Instruct",
    }


def source_label(source: str) -> str:
    cfg = load_ai_plans()
    labels = cfg.get("source_labels") or {}
    return labels.get(source) or source
