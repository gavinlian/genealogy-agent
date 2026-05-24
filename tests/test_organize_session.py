"""整理智能体会话测试"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from agent.organize_session import (
    build_genealogy_summary,
    clear_organize_session,
    create_organize_session,
    get_organize_session,
    restore_organize_session,
    resolve_context_mode,
    touch_organize_session,
)


def test_create_and_touch_session():
    family_id = "fam-test-1"
    session_id = create_organize_session(family_id)
    session = get_organize_session(session_id, family_id)
    assert session is not None
    assert session["turn_count"] == 0

    persons = [{"name": "张三", "generation": 1}, {"name": "李四", "generation": 2}]
    relations = [{"from": "张三", "to": "李四", "type": "parent_child"}]
    touch_organize_session(session_id, persons=persons, relations=relations, explanation="已整理")
    session = get_organize_session(session_id, family_id)
    assert session["turn_count"] == 1
    assert "张三" in session["summary"]
    assert session["last_explanation"] == "已整理"


def test_resolve_context_mode_summary_after_first_turn():
    session = {"turn_count": 1, "summary": "主谱共 2 人"}
    assert resolve_context_mode(session, refresh_context=False) == "summary"
    assert resolve_context_mode(session, refresh_context=True) == "full"
    assert resolve_context_mode(None, refresh_context=False) == "full"


def test_build_genealogy_summary():
    summary = build_genealogy_summary(
        [{"name": "张三", "generation": 1}],
        [{"from": "张三", "to": "李四", "type": "parent_child"}],
    )
    assert "1 人" in summary
    assert "张三" in summary


def test_restore_session_after_memory_loss():
    family_id = "fam-restore"
    session_id = "sess-restore01"
    session = restore_organize_session(session_id, family_id, {"turn_count": 2, "summary": "主谱共 5 人"})
    assert session["restored"] is True
    assert session["turn_count"] == 2
    assert get_organize_session(session_id, family_id) is not None
    assert resolve_context_mode(session, refresh_context=False) == "summary"


def test_clear_session():
    family_id = "fam-test-2"
    session_id = create_organize_session(family_id)
    assert get_organize_session(session_id, family_id) is not None
    assert clear_organize_session(session_id, family_id) is True
    assert get_organize_session(session_id, family_id) is None
