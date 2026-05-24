# -*- coding: utf-8 -*-
"""LLM Agent 单元测试（mock chat_fn）"""

import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from agent.agent_runtime import AgentContext
from agent.home_agent import run_home_agent_turn
from agent.llm_agent import LlmAgentDeps, parse_llm_agent_decision, run_agent_turn_llm


def _family_data():
    persons = [
        {"id": "1", "name": "张三", "parent_id": None, "generation": 1},
        {"id": "2", "name": "张四", "parent_id": "1", "generation": 2},
    ]
    relations = [
        {"from_person_id": "1", "to_person_id": "2", "relation_type": "parent_child"},
    ]
    return persons, relations


def test_parse_llm_agent_decision_tool():
    raw = json.dumps({
        "action": "call_tool",
        "tool": "search_persons",
        "params": {"query": "张四"},
    })
    d = parse_llm_agent_decision(raw)
    assert d and d["tool"] == "search_persons"


def test_parse_llm_natural_text_reply():
    d = parse_llm_agent_decision("你好，我是族谱助手，有什么可以帮你？")
    assert d and d["action"] == "reply_only"


def test_llm_agent_search_via_mock():
    persons, relations = _family_data()

    async def chat_fn(_msgs):
        return json.dumps({
            "action": "call_tool",
            "tool": "search_persons",
            "params": {"query": "张四"},
        }), ""

    async def ai_fn(_prompt):
        return "找到张四了。", ""

    deps = LlmAgentDeps(
        chat_fn=chat_fn, ai_fn=ai_fn, ai_configured=True, family_id="f1",
    )
    turn = asyncio.run(
        run_agent_turn_llm(
            "帮我找张四",
            AgentContext(family_id="f1"),
            persons,
            relations,
            deps,
        )
    )
    assert "张四" in turn.reply
    assert turn.state_patch.get("_used_llm") is True


def test_llm_agent_natural_reply_no_rule_fallback():
    persons, relations = _family_data()

    async def chat_fn(_msgs):
        return "族谱是用来记录家族世系的，你可以问我成员关系或让我帮你整理。", ""

    deps = LlmAgentDeps(
        chat_fn=chat_fn, ai_fn=None, ai_configured=True, family_id="f1",
    )
    turn = asyncio.run(
        run_agent_turn_llm(
            "族谱是干嘛的",
            AgentContext(family_id="f1"),
            persons,
            relations,
            deps,
        )
    )
    assert turn.state_patch.get("_used_llm") is True
    assert "族谱" in turn.reply
    assert "规则引擎" not in turn.reply


def test_home_agent_llm():
    families = [{"id": "f1", "name": "张氏族谱", "person_count": 3}]

    async def chat_fn(_msgs):
        return json.dumps({
            "action": "home_action",
            "home_action": "open_family",
            "params": {"family_name": "张氏族谱"},
            "reply": "好的，打开张氏族谱",
        }), ""

    turn = asyncio.run(run_home_agent_turn("打开张氏族谱", families, chat_fn=chat_fn))
    assert turn.used_llm
    assert turn.home_actions[0]["family_id"] == "f1"
