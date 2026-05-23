"""人名识别与清洗测试"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from agent.name_extractor import (
    extract_names_from_line,
    extract_names_from_full_text,
    find_name_occurrences,
    is_valid_person_name,
    normalize_person_name,
    post_process_person,
    refine_persons_list,
)
from agent.genealogy_builder import parse_genealogy_text_enhanced


def test_rejects_generation_as_name():
    assert not is_valid_person_name("一世")
    assert not is_valid_person_name("谱序")
    assert not is_valid_person_name("长子")


def test_accepts_genealogy_names():
    assert is_valid_person_name("张公")
    assert is_valid_person_name("张三")
    assert is_valid_person_name("欧阳修")
    assert is_valid_person_name("王伟")
    assert is_valid_person_name("李华")


def test_accepts_single_char_given_name():
    assert is_valid_person_name("五")
    assert is_valid_person_name("华")


def test_rejects_invalid_standalone_char():
    assert not is_valid_person_name("子")
    assert not is_valid_person_name("谱")


def test_extract_single_char_after_role():
    found = extract_names_from_line("长子：五", 2)
    names = {p["name"] for p in found}
    assert "五" in names


def test_extract_line_skips_generation_prefix():
    entries = extract_names_from_line("二世 张子 生1950", 2)
    names = [e["name"] for e in entries]
    assert "二世" not in names
    assert "张子" in names


def test_extract_spouse_and_child():
    line = "张三 配李四 子张五"
    entries = extract_names_from_line(line, 1)
    names = {e["name"] for e in entries}
    assert "张三" in names
    assert "李四" in names
    assert "张五" in names


def test_refine_filters_ai_hallucination():
    raw = "一世 张公\n二世 张子"
    ai_persons = [
        {"name": "一世", "generation": 1},
        {"name": "张公", "generation": 1, "gender": "male"},
        {"name": "张子", "generation": 2},
    ]
    refined = refine_persons_list(ai_persons, raw)
    names = [p["name"] for p in refined]
    assert "一世" not in names
    assert "张公" in names
    assert "张子" in names


def test_post_process_strips_invalid():
    assert post_process_person({"name": "碑记", "generation": 1}) is None
    assert post_process_person({"name": "王五", "generation": 1})["name"] == "王五"


def test_full_text_supplements_missing():
    text = """张氏族谱
一世 张公
二世 张子 生1950
配李氏"""
    refined = refine_persons_list([], text)
    names = {p["name"] for p in refined}
    assert "张公" in names
    assert "张子" in names


def test_parse_enhanced_no_generation_names():
    text = """谱序
一世 张公
二世 张子"""
    result = parse_genealogy_text_enhanced(text)
    names = [p["name"] for p in result["persons"]]
    assert "谱序" not in names
    assert "一世" not in names
    assert "张公" in names


def test_normalize_person_name():
    assert normalize_person_name(" 张 三 ") == "张三"


def test_find_name_occurrences():
    text = "一世 张公\n二世 张子配李氏"
    occs = find_name_occurrences(text)
    names = {o["name"] for o in occs}
    assert "张公" in names
    assert "张子" in names
    assert all("start" in o and "end" in o for o in occs)
    assert normalize_person_name("张公，") == "张公"
