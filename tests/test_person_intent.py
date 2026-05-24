# -*- coding: utf-8 -*-
"""自然语言成员字段提取"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from agent.person_intent import (
    extract_person_name_from_text,
    extract_person_patch_from_text,
    looks_like_person_update,
)


def test_extract_courtesy_and_generation():
    patch = extract_person_patch_from_text("张三字子明，第三世")
    assert patch.get("courtesy_name") == "子明"
    assert patch.get("generation") == 3
    assert extract_person_name_from_text("张三字子明，第三世") == "张三"


def test_extract_art_name():
    patch = extract_person_patch_from_text("李四号醉翁")
    assert patch.get("art_name") == "醉翁"


def test_looks_like_update_not_query():
    assert looks_like_person_update("张三字子明第三世") is True
    assert looks_like_person_update("张三的字是什么") is False
    assert looks_like_person_update("帮我把张三的字改成子明") is True


def test_extract_birth_year():
    patch = extract_person_patch_from_text("王五生于1850年")
    assert patch.get("birth_year") == 1850
