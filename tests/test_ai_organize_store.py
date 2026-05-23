# -*- coding: utf-8 -*-
"""AI 对话持久化存储测试"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from ai_organize_store import (
    clear_ai_chat_messages,
    ensure_ai_chat_table,
    get_ai_chat_state,
    save_ai_chat_state,
)


class FakeCursor:
    def __init__(self):
        self.tables: dict[str, list[dict]] = {}
        self.last_sql = ""

    def execute(self, sql, params=()):
        self.last_sql = sql
        sql_norm = " ".join(sql.split())
        if sql_norm.startswith("CREATE TABLE"):
            return self
        if "SELECT * FROM family_ai_chat WHERE family_id" in sql_norm:
            rows = self.tables.get("family_ai_chat", [])
            self._row = next((r for r in rows if r["family_id"] == params[0]), None)
            return self
        if "INSERT INTO family_ai_chat" in sql_norm:
            row = {
                "family_id": params[0],
                "messages": params[1],
                "session_id": params[2],
                "session_meta": params[3],
                "pending_plan": params[4],
                "pending_diff": params[5],
                "apply_mode": params[6],
                "clean_slate": params[7],
                "updated_at": params[8],
            }
            rows = self.tables.setdefault("family_ai_chat", [])
            for i, existing in enumerate(rows):
                if existing["family_id"] == params[0]:
                    rows[i] = row
                    return self
            rows.append(row)
            return self
        return self

    def fetchone(self):
        return getattr(self, "_row", None)


def test_save_and_load_messages():
    c = FakeCursor()
    ensure_ai_chat_table(c)
    save_ai_chat_state(
        c,
        "f1",
        {
            "messages": [{"role": "user", "content": "hello"}],
            "session_id": "s1",
            "pending_plan": {"relations_add": []},
        },
    )
    state = get_ai_chat_state(c, "f1")
    assert len(state["messages"]) == 1
    assert state["session_id"] == "s1"
    assert state["pending_plan"] == {"relations_add": []}


def test_clear_messages_keeps_pending_when_patched():
    c = FakeCursor()
    ensure_ai_chat_table(c)
    save_ai_chat_state(
        c,
        "f1",
        {
            "messages": [{"role": "user", "content": "x"}],
            "pending_plan": {"new_persons": ["张三"]},
        },
    )
    clear_ai_chat_messages(c, "f1")
    save_ai_chat_state(c, "f1", {"pending_plan": None, "pending_diff": None})
    state = get_ai_chat_state(c, "f1")
    assert state["messages"] == []
    assert state["pending_plan"] is None


def test_per_family_isolation():
    c = FakeCursor()
    save_ai_chat_state(c, "f1", {"messages": [{"role": "user", "content": "a"}]})
    save_ai_chat_state(c, "f2", {"messages": [{"role": "user", "content": "b"}]})
    assert get_ai_chat_state(c, "f1")["messages"][0]["content"] == "a"
    assert get_ai_chat_state(c, "f2")["messages"][0]["content"] == "b"
