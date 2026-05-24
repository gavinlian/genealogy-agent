# -*- coding: utf-8 -*-
"""首页族谱创建意图提取"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from agent.home_intent import extract_family_create_from_text, looks_like_create_family


def test_extract_family_fields():
    fields = extract_family_create_from_text("帮我创建族谱，名称：张氏族谱，姓氏：张，描述：祖籍江西")
    assert fields.get("name") == "张氏族谱"
    assert fields.get("surname") == "张"
    assert "江西" in fields.get("description", "")


def test_extract_clan_shorthand():
    fields = extract_family_create_from_text("帮我建一本陈氏族谱，简介：广东迁入")
    assert fields.get("name") == "陈氏族谱"
    assert fields.get("surname") == "陈"
    assert "广东" in fields.get("description", "")


def test_extract_natural_name():
    fields = extract_family_create_from_text("帮我创建张氏族谱，名字叫张家谱，姓氏张，描述祖籍江西")
    assert fields.get("name") in ("张家谱", "张氏族谱")
    assert fields.get("surname") == "张"
    assert looks_like_create_family("创建李氏族谱，名称李氏宗谱") is True
    assert looks_like_create_family("怎么创建族谱") is False


def test_extract_surname_only_generates_name():
    from agent.home_intent import finalize_create_fields

    fields = finalize_create_fields(extract_family_create_from_text("帮我建族谱，我们姓王，简介：山东临沂"))
    assert fields.get("name") == "王氏族谱"
    assert fields.get("surname") == "王"
    assert "临沂" in fields.get("description", "")


def test_extract_jian_zupu_phrase():
    fields = extract_family_create_from_text("我想建一个族谱，谱名叫李氏宗谱，姓李")
    assert fields.get("name") == "李氏宗谱"
    assert fields.get("surname") == "李"


def test_build_action_from_surname_only():
    from agent.home_intent import build_create_family_action

    action = build_create_family_action("帮我新建族谱，姓氏陈，描述广东迁入")
    assert action is not None
    assert action["name"] == "陈氏族谱"
    assert action.get("auto_create") is True


def test_home_chat_auto_create_family(client):
    res = client.post("/api/agent/home/chat", json={
        "message": "新建族谱，名称：测试自动创建谱，姓氏：测，描述：自动创建测试",
        "families": [],
        "history": [],
    })
    body = res.json()
    assert body["success"] is True
    actions = body.get("home_actions") or []
    assert any(a.get("type") == "select_family" for a in actions)
    fid = next(a["family_id"] for a in actions if a.get("type") == "select_family")
    families = client.get("/api/families").json()
    assert any(f["id"] == fid and f["name"] == "测试自动创建谱" for f in families)
