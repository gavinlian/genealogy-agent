# -*- coding: utf-8 -*-
"""Agent 对话 API"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from agent.agent_runtime import AgentContext, run_agent_turn


def _family_data():
    persons = [
        {"id": "1", "name": "张三", "parent_id": None},
        {"id": "2", "name": "张四", "parent_id": "1"},
        {"id": "3", "name": "张五", "parent_id": "1"},
    ]
    relations = [
        {"from_person_id": "1", "to_person_id": "2", "relation_type": "parent_child"},
        {"from_person_id": "1", "to_person_id": "3", "relation_type": "parent_child"},
    ]
    return persons, relations


def test_agent_switch_tab():
    persons, relations = _family_data()
    turn = run_agent_turn("打开文字版", AgentContext(family_id="f1"), persons, relations)
    assert any(a.get("type") == "switch_tab" and a.get("tab") == "source" for a in turn.ui_actions)
    assert "原文" in turn.reply


def test_agent_search_person():
    persons, relations = _family_data()
    turn = run_agent_turn("搜索张四", AgentContext(family_id="f1"), persons, relations)
    assert "张四" in turn.reply


def test_agent_cousins_need_anchor():
    persons, relations = _family_data()
    turn = run_agent_turn("我的堂兄弟有谁", AgentContext(family_id="f1"), persons, relations)
    assert "我在谱中" in turn.reply


def test_agent_set_anchor():
    persons, relations = _family_data()
    turn = run_agent_turn("我在谱中是张三", AgentContext(family_id="f1"), persons, relations)
    assert any(a.get("type") == "set_anchor" for a in turn.ui_actions)
    assert turn.state_patch.get("anchor_person_id") == "1"


def test_agent_open_classic_panel():
    persons, relations = _family_data()
    turn = run_agent_turn("打开经典编辑整理", AgentContext(family_id="f1"), persons, relations)
    assert any(a.get("type") == "open_classic" and a.get("panel") == "organize" for a in turn.ui_actions)


def test_agent_open_settings():
    persons, relations = _family_data()
    turn = run_agent_turn("打开AI设置", AgentContext(family_id="f1"), persons, relations)
    assert any(a.get("type") == "open_settings" for a in turn.ui_actions)


def test_agent_chat_api(client):
    create = client.post("/api/families", json={"name": "Agent测试"})
    fid = create.json()["id"]
    client.post("/api/persons", json={"family_id": fid, "name": "太祖", "generation": 1})
    client.post("/api/persons", json={"family_id": fid, "name": "张三", "generation": 2})

    res = client.post(f"/api/families/{fid}/agent/chat", json={"message": "搜索张三"})
    body = res.json()
    assert body["success"] is True
    assert "张三" in body["reply"]
    assert body.get("state", {}).get("messages")

    state = client.get(f"/api/families/{fid}/agent/state").json()
    assert state["success"] is True

    client.put(f"/api/families/{fid}/agent/state", json={"active_tab": "tree", "anchor_person_id": None})
    res2 = client.post(f"/api/families/{fid}/agent/chat", json={"message": "去看树图"})
    assert res2.json()["ui_actions"][0]["tab"] == "tree"


def test_agent_auto_prefill_person_patch(client):
    create = client.post("/api/families", json={"name": "预填测试"})
    fid = create.json()["id"]
    pr = client.post("/api/persons", json={"family_id": fid, "name": "张三", "generation": 1})
    pid = pr.json()["id"]

    res = client.post(
        f"/api/families/{fid}/agent/chat",
        json={"message": "张三字子明，第三世", "use_llm": False},
    )
    body = res.json()
    assert body["success"] is True
    assert body.get("confirmation")
    assert any(a.get("type") == "prefill_person" for a in body.get("ui_actions") or [])
    prefill = next(a for a in body["ui_actions"] if a["type"] == "prefill_person")
    assert prefill["person_id"] == pid
    assert prefill["draft"].get("courtesy_name") == "子明"
    assert prefill["draft"].get("generation") == 3
    assert "自动填" in body["reply"] or "预填" in body["reply"] or "提取" in body["reply"]
