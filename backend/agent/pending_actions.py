"""Agent 写操作待确认队列 — confirmation_token 持久化。"""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timedelta
from typing import Any


def ensure_pending_actions_table(cursor: sqlite3.Cursor) -> None:
    cursor.execute(
        """CREATE TABLE IF NOT EXISTS agent_pending_actions (
            token TEXT PRIMARY KEY,
            family_id TEXT NOT NULL,
            tool_name TEXT NOT NULL,
            payload TEXT NOT NULL,
            summary TEXT,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL
        )"""
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_agent_pending_family ON agent_pending_actions(family_id)"
    )


def _now_iso() -> str:
    return datetime.now().isoformat()


def create_pending_action(
    cursor: sqlite3.Cursor,
    family_id: str,
    tool_name: str,
    payload: dict[str, Any],
    *,
    summary: str = "",
    ttl_minutes: int = 30,
) -> str:
    ensure_pending_actions_table(cursor)
    token = str(uuid.uuid4())[:12]
    now = datetime.now()
    expires = now + timedelta(minutes=ttl_minutes)
    cursor.execute(
        """INSERT INTO agent_pending_actions
           (token, family_id, tool_name, payload, summary, created_at, expires_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            token,
            family_id,
            tool_name,
            json.dumps(payload, ensure_ascii=False),
            summary,
            now.isoformat(),
            expires.isoformat(),
        ),
    )
    return token


def get_pending_action(cursor: sqlite3.Cursor, token: str, family_id: str) -> dict[str, Any] | None:
    ensure_pending_actions_table(cursor)
    row = cursor.execute(
        "SELECT * FROM agent_pending_actions WHERE token = ? AND family_id = ?",
        (token, family_id),
    ).fetchone()
    if not row:
        return None
    data = dict(row)
    if data.get("expires_at") and data["expires_at"] < _now_iso():
        delete_pending_action(cursor, token, family_id)
        return None
    try:
        data["payload"] = json.loads(data.get("payload") or "{}")
    except json.JSONDecodeError:
        data["payload"] = {}
    return data


def delete_pending_action(cursor: sqlite3.Cursor, token: str, family_id: str) -> None:
    ensure_pending_actions_table(cursor)
    cursor.execute(
        "DELETE FROM agent_pending_actions WHERE token = ? AND family_id = ?",
        (token, family_id),
    )


def clear_family_pending(cursor: sqlite3.Cursor, family_id: str) -> None:
    ensure_pending_actions_table(cursor)
    cursor.execute("DELETE FROM agent_pending_actions WHERE family_id = ?", (family_id,))
