# -*- coding: utf-8 -*-
"""流水线配置加载"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from agent.pipeline_config import get_forbidden_names, get_format_rules, load_pipeline_config, public_config_payload


def test_pipeline_config_loads():
    cfg = load_pipeline_config()
    assert cfg.get("version") == "1.0"
    assert len(cfg.get("pipeline_stages") or []) >= 4


def test_forbidden_names_from_config():
    names = get_forbidden_names()
    assert "谱序" in names
    assert "长子" in names


def test_format_rules_from_config():
    rules = get_format_rules()
    assert any("配偶" in r for r in rules)


def test_public_payload():
    pub = public_config_payload()
    assert pub.get("relation_text_format", {}).get("hint")
    assert pub.get("agent_guidance", {}).get("workflow_summary")
