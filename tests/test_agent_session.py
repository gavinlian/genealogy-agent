# -*- coding: utf-8 -*-
"""Agent 会话重置 API"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))


def test_agent_session_reset_new(client):
    create = client.post("/api/families", json={"name": "会话测试"})
    fid = create.json()["id"]
    client.post(f"/api/families/{fid}/agent/chat", json={"message": "搜索测试", "use_llm": False})

    state = client.get(f"/api/families/{fid}/agent/state").json()
    assert len(state.get("messages") or []) >= 2

    reset = client.post(f"/api/families/{fid}/agent/session/reset", json={"mode": "new"})
    body = reset.json()
    assert body["success"] is True
    assert body.get("session_id")
    assert len(body.get("messages") or []) >= 1
    assert "新对话" in body["messages"][0]["content"]


def test_agent_session_reset_clear(client):
    create = client.post("/api/families", json={"name": "清空测试"})
    fid = create.json()["id"]
    client.post(f"/api/families/{fid}/agent/chat", json={"message": "你好", "use_llm": False})

    reset = client.post(f"/api/families/{fid}/agent/session/reset", json={"mode": "clear"})
    body = reset.json()
    assert body["success"] is True
    assert body.get("messages") == []
