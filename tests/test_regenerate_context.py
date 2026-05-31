# -*- coding: utf-8 -*-
"""重生上下文与规则降级"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from agent.regenerate_context import build_regenerate_context, _extract_chat_notes


def test_extract_chat_notes_filters_keywords():
    messages = [
        {"role": "user", "content": "整理好的文字填到版本2里面吗"},
        {"role": "assistant", "content": "好的，关系文字应保存到版本二"},
        {"role": "user", "content": "你好"},
    ]
    notes = _extract_chat_notes(messages)
    assert "版本2" in notes or "版本二" in notes
    assert "你好" not in notes


def test_build_regenerate_context_empty():
    import sqlite3
    from agent_store import ensure_agent_state_table
    from source_versions import ensure_versions_table

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS families (id TEXT PRIMARY KEY, source_text TEXT, source_annotations TEXT)")
    c.execute("INSERT INTO families (id, source_text, source_annotations) VALUES ('fam1', '', '[]')")
    ensure_agent_state_table(c)
    ensure_versions_table(c)
    ctx = build_regenerate_context(c, "fam1", persons=[{"name": "张三"}])
    assert "张三" in ctx.get("genealogy_summary", "")
    conn.close()
