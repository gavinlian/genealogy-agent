# -*- coding: utf-8 -*-
"""message_parts 构建"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from agent.message_parts import build_family_message_parts, build_home_message_parts


def test_home_create_family_preview():
    parts = build_home_message_parts(
        reply="好的，正在创建…",
        raw_actions=[{"type": "create_family", "name": "张氏族谱", "surname": "张", "description": "祖籍江西"}],
        materialized_actions=[{"type": "select_family", "family_id": "abc", "family_name": "张氏族谱"}],
    )
    preview = next(p for p in parts if p["type"] == "create_family_preview")
    assert preview["data"]["name"] == "张氏族谱"
    assert preview["data"]["status"] == "created"
    assert preview["data"]["family_id"] == "abc"


def test_family_person_card_from_search():
    parts = build_family_message_parts(
        reply="找到成员",
        tool_calls=[{
            "tool": "search_persons",
            "result": {"people": [{"id": "1", "name": "张三", "generation": 2}]},
        }],
    )
    card = next(p for p in parts if p["type"] == "person_card")
    assert card["data"]["name"] == "张三"


def test_family_field_diff_from_prefill():
    parts = build_family_message_parts(
        reply="已提取",
        ui_actions=[{"type": "prefill_person", "person_id": "1", "draft": {"courtesy_name": "子明", "generation": 3}}],
    )
    diff = next(p for p in parts if p["type"] == "field_diff")
    assert any(c["field"] == "字" for c in diff["data"]["changes"])
