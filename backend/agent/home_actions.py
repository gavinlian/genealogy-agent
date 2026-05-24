"""首页 Agent 动作物化（写库等）。"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any


def create_family_in_db(cursor, *, name: str, surname: str = "", description: str = "") -> str:
    fid = str(uuid.uuid4())[:8]
    now = datetime.now().isoformat()
    cursor.execute(
        """INSERT INTO families (id, name, surname, description, start_generation, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (fid, name.strip(), (surname or "").strip(), (description or "").strip(), 1, now, now),
    )
    return fid


def materialize_home_actions(cursor, actions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """将 create_family(auto_create) 转为真实建库 + select_family。"""
    out: list[dict[str, Any]] = []
    for action in actions or []:
        if action.get("type") != "create_family":
            out.append(action)
            continue

        name = (action.get("name") or "").strip()
        auto = action.get("auto_create", bool(name))

        if auto and name:
            fid = create_family_in_db(
                cursor,
                name=name,
                surname=str(action.get("surname") or ""),
                description=str(action.get("description") or ""),
            )
            out.append({"type": "select_family", "family_id": fid, "family_name": name})
            continue

        payload: dict[str, Any] = {"type": "create_family"}
        if name:
            payload["name"] = name
        if action.get("surname"):
            payload["surname"] = action["surname"]
        if action.get("description"):
            payload["description"] = action["description"]
        out.append(payload)

    return out
