"""加载 config/genealogy_pipeline.json — Agent / 提示词 / 规则引擎共用。"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "genealogy_pipeline.json"


@lru_cache(maxsize=1)
def load_pipeline_config() -> dict[str, Any]:
    if not _CONFIG_PATH.is_file():
        return {}
    with _CONFIG_PATH.open(encoding="utf-8") as fh:
        return json.load(fh)


def get_relation_format() -> dict[str, Any]:
    return load_pipeline_config().get("relation_text_format") or {}


def get_forbidden_names() -> list[str]:
    fmt = get_relation_format()
    return list(fmt.get("forbidden_as_names") or [])


def get_format_rules() -> list[str]:
    fmt = get_relation_format()
    return list(fmt.get("rules") or [])


def format_forbidden_for_prompt() -> str:
    names = get_forbidden_names()
    if not names:
        return "「一世」「谱序」「长子」等"
    shown = names[:20]
    suffix = "等" if len(names) > 20 else ""
    return "、".join(f"「{n}」" for n in shown) + suffix


def format_rules_for_prompt() -> str:
    rules = get_format_rules()
    if not rules:
        return ""
    return "\n".join(f"- {r}" for r in rules)


def get_pipeline_stages() -> list[dict[str, Any]]:
    return list(load_pipeline_config().get("pipeline_stages") or [])


def get_agent_guidance() -> dict[str, Any]:
    return load_pipeline_config().get("agent_guidance") or {}


def get_validation_checks() -> list[dict[str, Any]]:
    val = load_pipeline_config().get("validation") or {}
    return list(val.get("preview_before_apply") or [])


def public_config_payload() -> dict[str, Any]:
    """供 API / 前端读取的公开子集（不含冗长 architecture）。"""
    cfg = load_pipeline_config()
    fmt = get_relation_format()
    return {
        "version": cfg.get("version"),
        "pipeline_stages": get_pipeline_stages(),
        "relation_text_format": {
            "hint": fmt.get("hint"),
            "recommended_line_example": fmt.get("recommended_line_example"),
            "relation_syntax": fmt.get("relation_syntax"),
            "rules": get_format_rules(),
            "forbidden_as_names": get_forbidden_names(),
        },
        "validation": cfg.get("validation"),
        "agent_guidance": get_agent_guidance(),
    }
