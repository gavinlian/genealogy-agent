# -*- coding: utf-8 -*-
"""AI 对话整理主谱测试"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from agent.genealogy_organizer import (
    _rule_parse_instruction,
    merge_plan_into_genealogy,
    _normalize_plan,
    parse_organize_plan_from_text,
    compute_organize_diff,
    build_organize_prompt,
)
from agent.parser import extract_json_content


def test_rule_parse_parent_child():
    persons = [{"id": "1", "name": "\u5f20\u4e09"}, {"id": "2", "name": "\u674e\u56db"}]
    plan = _rule_parse_instruction("\u674e\u56db\u662f\u5f20\u4e09\u7684\u513f\u5b50", persons)
    assert len(plan["relations_add"]) == 1
    rel = plan["relations_add"][0]
    assert rel["from"] == "张三"
    assert rel["to"] == "李四"
    assert rel["type"] == "parent_child"


def test_rule_parse_spouse():
    persons = [{"id": "1", "name": "\u738b\u4e94"}, {"id": "2", "name": "\u8d75\u516d"}]
    plan = _rule_parse_instruction("\u738b\u4e94\u914d\u8d75\u516d", persons)
    assert len(plan["relations_add"]) == 1
    assert plan["relations_add"][0]["type"] == "spouse"


def test_merge_plan_adds_relation():
    persons = [
        {"id": "1", "name": "张三", "generation": 1},
        {"id": "2", "name": "李四", "generation": 2},
    ]
    relations = []
    plan = _normalize_plan({
        "explanation": "补父子",
        "relations_add": [{"from": "张三", "to": "李四", "type": "parent_child", "status": "confirmed"}],
    })
    built = merge_plan_into_genealogy(persons, relations, plan)
    assert built.get("success") is not False
    stats = built.get("stats") or {}
    assert stats.get("person_count", 0) >= 2
    assert stats.get("relation_count", 0) >= 1


def test_normalize_plan_defaults():
    plan = _normalize_plan({"explanation": "ok"})
    assert plan["relations_add"] == []
    assert plan["start_generation"] == 1


def test_extract_json_from_markdown_wrapper():
    raw = '说明如下\n```json\n{"explanation": "ok", "relations_add": []}\n```\n'
    parsed = extract_json_content(raw)
    assert parsed is not None
    assert parsed["explanation"] == "ok"


def test_extract_json_embedded_in_text():
    raw = '整理结果：{"explanation": "done", "relations_add": [], "relations_remove": []} 请确认'
    parsed = extract_json_content(raw)
    assert parsed is not None
    assert parsed["explanation"] == "done"


def test_extract_json_trailing_comma():
    raw = '{"explanation": "ok", "relations_add": [],}'
    parsed = extract_json_content(raw)
    assert parsed is not None
    assert parsed["explanation"] == "ok"


def test_parse_organize_from_persons_shape():
    raw = '{"explanation": "补全", "persons": [{"name": "张三"}], "relations": [{"from": "张三", "to": "李四", "type": "parent_child"}]}'
    plan = parse_organize_plan_from_text(raw)
    assert plan is not None
    assert len(plan["new_persons"]) == 1
    assert len(plan["relations_add"]) == 1


def test_parse_organize_plain_text_answer():
    plan = parse_organize_plan_from_text("当前族谱共三代，始祖为张三，无需修改。")
    assert plan is not None
    assert "张三" in plan["explanation"]


def test_normalize_plan_accepts_string_new_persons():
    plan = _normalize_plan({
        "explanation": "建谱",
        "new_persons": ["张三", "李四"],
        "relations_add": [{"from": "张三", "to": "李四", "type": "parent_child"}],
    })
    assert len(plan["new_persons"]) == 2
    assert plan["new_persons"][0]["name"] == "张三"
    built = merge_plan_into_genealogy([], [], plan)
    assert built.get("success") is not False
    assert built["stats"]["person_count"] >= 2


def test_build_organize_prompt_bootstrap_when_empty():
    prompt = build_organize_prompt([], [], "请从原文建谱", source_text="一世 张三\n二世 李四")
    assert "当前主谱尚无成员" in prompt
    assert "new_persons" in prompt


def test_compute_organize_diff_clean_slate_removes_old_relations():
    persons = [
        {"id": "1", "name": "张三", "generation": 1},
        {"id": "2", "name": "李四", "generation": 2},
        {"id": "3", "name": "王五", "generation": 2},
    ]
    relations = [
        {"from": "张三", "to": "李四", "type": "parent_child"},
        {"from": "张三", "to": "王五", "type": "parent_child"},
    ]
    plan = _normalize_plan({
        "clean_slate": True,
        "new_persons": [{"name": "张三"}, {"name": "李四"}],
        "relations_add": [{"from": "张三", "to": "李四", "type": "parent_child", "status": "confirmed"}],
    })
    built = merge_plan_into_genealogy(persons, relations, plan, clean_slate=True)
    diff = compute_organize_diff(persons, relations, plan, built)
    assert diff["clean_slate"] is True
    assert diff["has_replace_impact"] is True
    assert "王五" in diff["extra_persons"]
    assert any(r["to"] == "王五" for r in diff["extra_relations"])


def test_should_use_clean_slate_from_message():
    from agent.genealogy_organizer import should_use_clean_slate

    assert should_use_clean_slate("请按原文干净整理主谱") is True
    assert should_use_clean_slate("李四是谁的儿子") is False


def test_compute_organize_diff_merge_vs_replace():
    persons = [
        {"id": "1", "name": "张三", "generation": 1},
        {"id": "2", "name": "李四", "generation": 2},
        {"id": "3", "name": "王五", "generation": 2},
    ]
    relations = [
        {"from": "张三", "to": "李四", "type": "parent_child"},
    ]
    plan = _normalize_plan({
        "relations_add": [{"from": "张三", "to": "王五", "type": "parent_child", "status": "confirmed"}],
    })
    built = merge_plan_into_genealogy(persons, relations, plan)
    diff = compute_organize_diff(persons, relations, plan, built)
    assert diff["before"]["person_count"] == 3
    assert diff["before"]["relation_count"] == 1
    assert len(diff["relations_to_add"]) == 1
    assert diff["relations_to_add"][0]["to"] == "王五"
    assert diff["merge_change_count"] >= 1
    assert diff["has_replace_impact"] is False


def test_reconcile_plan_skips_existing_persons():
    from agent.genealogy_organizer import reconcile_plan_with_genealogy

    persons = [{"id": "1", "name": "张三"}, {"id": "2", "name": "李四"}]
    plan = _normalize_plan({
        "new_persons": [{"name": "张三"}, {"name": "李四"}, {"name": "王五"}],
        "relations_add": [{"from": "张三", "to": "王五", "type": "parent_child"}],
    })
    out = reconcile_plan_with_genealogy(plan, persons)
    assert len(out["new_persons"]) == 1
    assert out["new_persons"][0]["name"] == "王五"


def test_reconcile_plan_does_not_inflate_diff_after_count():
    from agent.genealogy_organizer import reconcile_plan_with_genealogy

    persons = [{"id": str(i), "name": f"成员{i}"} for i in range(44)]
    relations = []
    plan = reconcile_plan_with_genealogy(_normalize_plan({
        "new_persons": [{"name": f"成员{i}"} for i in range(44)],
        "relations_add": [{"from": "成员0", "to": "成员1", "type": "parent_child"}],
    }), persons)
    source = "\n".join(f"第{i}世 额外{i}" for i in range(50))
    built = merge_plan_into_genealogy(persons, relations, plan, source_text=source)
    diff = compute_organize_diff(persons, relations, plan, built)
    assert diff["before"]["person_count"] == 44
    assert diff["after"]["person_count"] <= 45
