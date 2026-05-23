"""主谱与原文差异对比测试"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from agent.source_diff import compare_genealogy_with_source, compare_parsed_with_genealogy

MULTIGEN_TEXT = """张氏族谱
一世 张公
二世 张子 生1950
三世 孙一 男 生1980
孙二 男 生1985"""


def test_compare_no_source():
    persons = [{"name": "张公"}, {"name": "张子"}]
    relations = [{"from": "张公", "to": "张子", "type": "parent_child"}]
    result = compare_genealogy_with_source(persons, relations, "")
    assert result["has_source"] is False
    assert result["aligned"] is True
    assert result["current"]["person_count"] == 2


def test_compare_detects_missing_person_and_relation():
    persons = [{"name": "张公", "generation": 1}]
    relations: list[dict] = []
    result = compare_genealogy_with_source(persons, relations, MULTIGEN_TEXT)
    assert result["has_source"] is True
    assert "张子" in result["missing_persons"]
    assert result["issues_count"] > 0
    assert result["aligned"] is False
    assert result["source_length"] == len(MULTIGEN_TEXT.strip())


def test_compare_aligned_when_matches_source():
    persons = [
        {"name": "张公", "generation": 1},
        {"name": "张子", "generation": 2},
        {"name": "孙一", "generation": 3},
        {"name": "孙二", "generation": 3},
    ]
    relations = [
        {"from": "张公", "to": "张子", "type": "parent_child"},
        {"from": "张子", "to": "孙一", "type": "parent_child"},
        {"from": "张子", "to": "孙二", "type": "parent_child"},
    ]
    result = compare_genealogy_with_source(persons, relations, MULTIGEN_TEXT)
    assert result["has_source"] is True
    assert result["missing_persons"] == []
    assert result["proposed_relations"] == []


def test_compare_includes_version_info():
    persons = [{"name": "张公"}]
    version = {"id": "v1", "label": "第2版", "version_no": 2, "status": "confirmed"}
    result = compare_genealogy_with_source(
        persons, [], MULTIGEN_TEXT, source_version=version
    )
    assert result["source_version"]["label"] == "第2版"
    assert result["source_version"]["status"] == "confirmed"


def test_compare_parsed_skips_existing_and_lists_additions():
    persons = [
        {"name": "张三", "generation": 1},
        {"name": "李四", "generation": 2},
    ]
    relations = [{"from": "张三", "to": "李四", "type": "parent_child"}]
    parsed_persons = [
        {"name": "张三", "generation": 1},
        {"name": "李四", "generation": 2},
        {"name": "王五", "generation": 3},
    ]
    parsed_relations = [
        {"from": "张三", "to": "李四", "type": "parent_child"},
        {"from": "李四", "to": "王五", "type": "parent_child"},
    ]
    result = compare_parsed_with_genealogy(persons, relations, parsed_persons, parsed_relations)
    assert result["compare_mode"] == "parse_import"
    assert result["persons_to_add"] == ["王五"]
    assert "张三" in result["persons_skipped"]
    assert len(result["relations_to_add"]) == 1
    assert result["relations_to_add"][0]["to"] == "王五"
    assert len(result["relations_skipped"]) == 1
    assert result["aligned"] is False


def test_compare_parsed_aligned_when_no_new_items():
    persons = [{"name": "张三"}]
    relations = []
    parsed_persons = [{"name": "张三"}]
    parsed_relations = []
    result = compare_parsed_with_genealogy(persons, relations, parsed_persons, parsed_relations)
    assert result["aligned"] is True
    assert result["persons_to_add"] == []
    assert result["relations_to_add"] == []
