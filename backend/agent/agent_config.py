"""族谱智能体调度与扫描配置。"""

from __future__ import annotations

import json
import os
from typing import Any

_DEFAULT: dict[str, Any] = {
    "enabled": True,
    "daily_run_times": ["08:00", "20:00"],
    "on_open_max_hours": 48,
    "check_interval_minutes": 5,
    "compare_owned_families": True,
    "compare_followed_families": True,
    "compare_snapshots": True,
    "min_match_confidence": 0.62,
    "max_discoveries_per_scan": 50,
}

_CACHE: dict[str, Any] | None = None


def _config_path() -> str:
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(root, "config", "agent_scheduler.json")


def load_agent_scheduler_defaults() -> dict[str, Any]:
    global _CACHE
    if _CACHE is not None:
        return dict(_CACHE)
    path = _config_path()
    merged = dict(_DEFAULT)
    if os.path.isfile(path):
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                merged.update({k: v for k, v in data.items() if not k.startswith("$")})
        except (OSError, json.JSONDecodeError):
            pass
    _CACHE = merged
    return dict(merged)


def merge_schedule_settings(stored: dict[str, Any] | None) -> dict[str, Any]:
    base = load_agent_scheduler_defaults()
    if not stored:
        return base
    out = dict(base)
    for key in (
        "enabled",
        "daily_run_times",
        "on_open_max_hours",
        "check_interval_minutes",
        "compare_owned_families",
        "compare_followed_families",
        "compare_snapshots",
        "min_match_confidence",
        "max_discoveries_per_scan",
    ):
        if key in stored and stored[key] is not None:
            out[key] = stored[key]
    return out
