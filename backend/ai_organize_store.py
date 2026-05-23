"""族谱 AI 对话与待应用方案 — SQLite 持久化（按 family_id 一份）。"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from typing import Any


def ensure_ai_chat_table(cursor: sqlite3.Cursor) -> None:
    cursor.execute(
        """CREATE TABLE IF NOT EXISTS family_ai_chat (
            family_id TEXT PRIMARY KEY,
            messages TEXT NOT NULL DEFAULT '[]',
            session_id TEXT,
            session_meta TEXT,
            pending_plan TEXT,
            pending_diff TEXT,
            apply_mode TEXT DEFAULT 'merge',
            clean_slate INTEGER DEFAULT 0,
            updated_at TEXT
        )"""
    )


def _loads(raw: str | None, default: Any) -> Any:
    if not raw:
        return default
    try:
        return json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return default


def get_ai_chat_state(cursor: sqlite3.Cursor, family_id: str) -> dict[str, Any]:
    ensure_ai_chat_table(cursor)
    row = cursor.execute(
        "SELECT * FROM family_ai_chat WHERE family_id = ?",
        (family_id,),
    ).fetchone()
    if not row:
        return {
            "family_id": family_id,
            "messages": [],
            "session_id": None,
            "session_meta": {},
            "pending_plan": None,
            "pending_diff": None,
            "apply_mode": "merge",
            "clean_slate": False,
            "updated_at": None,
        }
    data = dict(row)
    return {
        "family_id": family_id,
        "messages": _loads(data.get("messages"), []),
        "session_id": data.get("session_id"),
        "session_meta": _loads(data.get("session_meta"), {}),
        "pending_plan": _loads(data.get("pending_plan"), None),
        "pending_diff": _loads(data.get("pending_diff"), None),
        "apply_mode": data.get("apply_mode") or "merge",
        "clean_slate": bool(data.get("clean_slate")),
        "updated_at": data.get("updated_at"),
    }


def save_ai_chat_state(cursor: sqlite3.Cursor, family_id: str, patch: dict[str, Any]) -> dict[str, Any]:
    ensure_ai_chat_table(cursor)
    current = get_ai_chat_state(cursor, family_id)
    merged = {**current, **patch, "family_id": family_id}
    now = datetime.now().isoformat()
    cursor.execute(
        """INSERT INTO family_ai_chat (
            family_id, messages, session_id, session_meta,
            pending_plan, pending_diff, apply_mode, clean_slate, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(family_id) DO UPDATE SET
            messages=excluded.messages,
            session_id=excluded.session_id,
            session_meta=excluded.session_meta,
            pending_plan=excluded.pending_plan,
            pending_diff=excluded.pending_diff,
            apply_mode=excluded.apply_mode,
            clean_slate=excluded.clean_slate,
            updated_at=excluded.updated_at
        """,
        (
            family_id,
            json.dumps(merged.get("messages") or [], ensure_ascii=False),
            merged.get("session_id"),
            json.dumps(merged.get("session_meta") or {}, ensure_ascii=False),
            json.dumps(merged["pending_plan"], ensure_ascii=False)
            if merged.get("pending_plan") is not None
            else None,
            json.dumps(merged["pending_diff"], ensure_ascii=False)
            if merged.get("pending_diff") is not None
            else None,
            merged.get("apply_mode") or "merge",
            1 if merged.get("clean_slate") else 0,
            now,
        ),
    )
    merged["updated_at"] = now
    return merged


def clear_ai_chat_messages(cursor: sqlite3.Cursor, family_id: str) -> None:
    save_ai_chat_state(
        cursor,
        family_id,
        {
            "messages": [],
            "session_id": None,
            "session_meta": {},
        },
    )
