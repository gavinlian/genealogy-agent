"""族谱智能体单元测试"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from agent.parser import parse_genealogy_text, extract_json_content
from agent.validators import validate_genealogy_persons, validate_relations
from agent.engine import get_agent_status


def test_parse_genealogy_text_basic():
    text = """第一代
张三 生于1980 卒于2020
配李四
张五 男"""
    result = parse_genealogy_text(text)
    names = [p["name"] for p in result["persons"]]
    assert "张三" in names
    assert any(p["birth_year"] == 1980 for p in result["persons"] if p["name"] == "张三")


def test_extract_json_content_codeblock():
    raw = '说明\n```json\n{"persons": [], "relations": []}\n```'
    parsed = extract_json_content(raw)
    assert parsed == {"persons": [], "relations": []}


def test_validate_birth_after_death():
    persons = [{"name": "王五", "birth_year": 2000, "death_year": 1990}]
    result = validate_genealogy_persons(persons)
    assert result["valid"] is False
    assert result["error_count"] >= 1


def test_validate_duplicate_name_warning():
    persons = [
        {"name": "赵六", "birth_year": 1900},
        {"name": "赵六", "birth_year": 1920},
    ]
    result = validate_genealogy_persons(persons)
    assert result["warning_count"] >= 1


def test_validate_relations_missing_parent():
    persons = [{"name": "子一"}]
    relations = [{"from": "不存在", "to": "子一", "type": "parent_child"}]
    result = validate_relations(persons, relations)
    assert result["valid"] is False


def test_agent_status_structure():
    status = get_agent_status(
        ocr_configured=True,
        parse_configured=False,
        ocr_selection={"provider": "minimax", "model": "MiniMax-M2.7"},
        parse_selection={"provider": "minimax", "model": "MiniMax-M2.7"},
    )
    assert status["name"] == "族见 · 身具智能的家族智能体"
    assert "scan" in status["tasks"]
    assert "generate" in status["tasks"]
    assert status["ai"]["ready"] is False
