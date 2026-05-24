"""族谱 Agent 会话状态 — SQLite 持久化（按 family_id）。"""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime
from typing import Any

VALID_TABS = frozenset({"tree", "source", "person", "diff", "organize", "chat"})


def ensure_agent_state_table(cursor: sqlite3.Cursor) -> None:
    cursor.execute(
        """CREATE TABLE IF NOT EXISTS family_agent_state (
            family_id TEXT PRIMARY KEY,
            messages TEXT NOT NULL DEFAULT '[]',
            anchor_person_id TEXT,
            active_tab TEXT DEFAULT 'tree',
            selected_person_id TEXT,
            session_id TEXT,
            updated_at TEXT
        )"""
    )
    try:
        cursor.execute("ALTER TABLE family_agent_state ADD COLUMN session_id TEXT")
    except sqlite3.OperationalError:
        pass


def _loads(raw: str | None, default: Any) -> Any:
    if not raw:
        return default
    try:
        return json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return default


def get_agent_state(cursor: sqlite3.Cursor, family_id: str) -> dict[str, Any]:
    ensure_agent_state_table(cursor)
    row = cursor.execute(
        "SELECT * FROM family_agent_state WHERE family_id = ?",
        (family_id,),
    ).fetchone()
    if not row:
        return _default_state(family_id)
    data = dict(row)
    tab = data.get("active_tab") or "tree"
    if tab not in VALID_TABS:
        tab = "tree"
    return {
        "family_id": family_id,
        "messages": _loads(data.get("messages"), []),
        "anchor_person_id": data.get("anchor_person_id"),
        "active_tab": tab,
        "selected_person_id": data.get("selected_person_id"),
        "session_id": data.get("session_id"),
        "updated_at": data.get("updated_at"),
    }


def _default_state(family_id: str) -> dict[str, Any]:
    return {
        "family_id": family_id,
        "messages": [],
        "anchor_person_id": None,
        "active_tab": "tree",
        "selected_person_id": None,
        "session_id": None,
        "updated_at": None,
    }


def save_agent_state(cursor: sqlite3.Cursor, family_id: str, patch: dict[str, Any]) -> dict[str, Any]:
    ensure_agent_state_table(cursor)
    current = get_agent_state(cursor, family_id)
    merged = {**current, **patch, "family_id": family_id}
    if merged.get("active_tab") not in VALID_TABS:
        merged["active_tab"] = current.get("active_tab") or "tree"
    now = datetime.now().isoformat()
    cursor.execute(
        """INSERT INTO family_agent_state (
            family_id, messages, anchor_person_id, active_tab, selected_person_id, session_id, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(family_id) DO UPDATE SET
            messages=excluded.messages,
            anchor_person_id=excluded.anchor_person_id,
            active_tab=excluded.active_tab,
            selected_person_id=excluded.selected_person_id,
            session_id=COALESCE(excluded.session_id, family_agent_state.session_id),
            updated_at=excluded.updated_at
        """,
        (
            family_id,
            json.dumps(merged.get("messages") or [], ensure_ascii=False),
            merged.get("anchor_person_id"),
            merged.get("active_tab") or "tree",
            merged.get("selected_person_id"),
            merged.get("session_id"),
            now,
        ),
    )
    merged["updated_at"] = now
    return merged


def append_agent_messages(
    cursor: sqlite3.Cursor,
    family_id: str,
    user_message: str,
    assistant_message: str,
    *,
    extra_meta: dict | None = None,
) -> dict[str, Any]:
    state = get_agent_state(cursor, family_id)
    messages = list(state.get("messages") or [])
    if user_message:
        messages.append({"role": "user", "content": user_message})
    assistant_entry: dict[str, Any] = {"role": "assistant", "content": assistant_message}
    if extra_meta:
        assistant_entry["meta"] = extra_meta
    messages.append(assistant_entry)
    # keep last 40 turns
    if len(messages) > 80:
        messages = messages[-80:]
    return save_agent_state(cursor, family_id, {"messages": messages})


def build_family_welcome_message(family_name: str = "") -> str:
    title = f"「{family_name}」" if family_name else "本族谱"
    return (
        f"已开启新对话（{title}）。你可以直接说：\n"
        "· 「搜索张三」\n"
        "· 「打开文字版」\n"
        "· 「我的堂兄弟有谁」（需先设「我在谱中是谁」）"
    )


def build_home_welcome_message() -> str:
    return (
        "你好，我是族谱智能体。\n"
        "· 在上方点选族谱即可开始\n"
        "· 或说「扫描建谱」创建新族谱\n"
        "· 说「打开某某族谱」也可切换"
    )


def clear_agent_messages(cursor: sqlite3.Cursor, family_id: str) -> dict[str, Any]:
    return save_agent_state(cursor, family_id, {"messages": []})


def reset_agent_session(
    cursor: sqlite3.Cursor,
    family_id: str,
    *,
    family_name: str = "",
    with_welcome: bool = True,
) -> dict[str, Any]:
    session_id = str(uuid.uuid4())[:10]
    messages: list[dict] = []
    if with_welcome:
        messages = [{"role": "assistant", "content": build_family_welcome_message(family_name)}]
    return save_agent_state(cursor, family_id, {
        "messages": messages,
        "session_id": session_id,
    })
