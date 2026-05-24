"""AI 对话整理智能体会话 — 避免每轮重复发送完整主谱上下文。"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Any

SESSION_TTL = timedelta(hours=24)

# family_id -> session_id（每族谱同时仅保留一个活跃会话）
_family_active: dict[str, str] = {}
_sessions: dict[str, dict[str, Any]] = {}


def build_genealogy_summary(persons: list[dict], relations: list[dict]) -> str:
    names = [p.get("name") for p in persons if p.get("name")]
    gens = sorted({int(p.get("generation") or 0) for p in persons if p.get("generation")})
    gen_range = f"{gens[0]}–{gens[-1]} 世" if len(gens) >= 2 else (f"{gens[0]} 世" if gens else "未知")
    sample = "、".join(names[:12])
    if len(names) > 12:
        sample += f"…等 {len(names)} 人"
    pc = sum(1 for r in relations if (r.get("type") or r.get("relation_type")) == "parent_child")
    sc = sum(1 for r in relations if (r.get("type") or r.get("relation_type")) == "spouse")
    return (
        f"主谱共 {len(names)} 人、{len(relations)} 条关系（父子约 {pc}、配偶约 {sc}），世代 {gen_range}。"
        f" 姓名示例：{sample or '（空）'}"
    )


def create_organize_session(family_id: str) -> str:
    """新建整理智能体会话。"""
    old_id = _family_active.get(family_id)
    if old_id:
        _sessions.pop(old_id, None)
    session_id = str(uuid.uuid4())[:12]
    now = datetime.now()
    _sessions[session_id] = {
        "id": session_id,
        "family_id": family_id,
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
        "turn_count": 0,
        "summary": "",
        "last_explanation": "",
        "source_included_once": False,
    }
    _family_active[family_id] = session_id
    return session_id


def restore_organize_session(session_id: str, family_id: str, meta: dict[str, Any] | None = None) -> dict[str, Any]:
    """后端重启后，用持久化的 session_id + meta 恢复内存会话。"""
    meta = meta or {}
    now = datetime.now()
    session = {
        "id": session_id,
        "family_id": family_id,
        "created_at": meta.get("created_at") or now.isoformat(),
        "updated_at": now.isoformat(),
        "turn_count": int(meta.get("turn_count") or 0),
        "summary": meta.get("summary") or "",
        "last_explanation": meta.get("last_explanation") or "",
        "source_included_once": bool(meta.get("source_included_once")),
        "restored": True,
    }
    _sessions[session_id] = session
    _family_active[family_id] = session_id
    return session


def get_organize_session(session_id: str | None, family_id: str) -> dict[str, Any] | None:
    if not session_id:
        return None
    _purge_expired()
    session = _sessions.get(session_id)
    if not session or session.get("family_id") != family_id:
        return None
    return session


def touch_organize_session(
    session_id: str,
    *,
    persons: list[dict],
    relations: list[dict],
    explanation: str = "",
    source_included: bool = False,
) -> dict[str, Any] | None:
    session = _sessions.get(session_id)
    if not session:
        return None
    session["turn_count"] = int(session.get("turn_count") or 0) + 1
    session["updated_at"] = datetime.now().isoformat()
    session["summary"] = build_genealogy_summary(persons, relations)
    if explanation:
        session["last_explanation"] = explanation[:800]
    if source_included:
        session["source_included_once"] = True
    return session


def clear_organize_session(session_id: str | None, family_id: str) -> bool:
    if not session_id:
        return False
    session = _sessions.pop(session_id, None)
    if session and _family_active.get(family_id) == session_id:
        _family_active.pop(family_id, None)
    return session is not None


def clear_family_organize_sessions(family_id: str) -> None:
    sid = _family_active.pop(family_id, None)
    if sid:
        _sessions.pop(sid, None)


def _purge_expired() -> None:
    now = datetime.now()
    expired = []
    for sid, session in _sessions.items():
        updated = session.get("updated_at") or session.get("created_at")
        try:
            ts = datetime.fromisoformat(updated)
        except (TypeError, ValueError):
            expired.append(sid)
            continue
        if now - ts > SESSION_TTL:
            expired.append(sid)
    for sid in expired:
        session = _sessions.pop(sid, None)
        if session:
            fid = session.get("family_id")
            if fid and _family_active.get(fid) == sid:
                _family_active.pop(fid, None)


def resolve_context_mode(
    session: dict[str, Any] | None,
    *,
    refresh_context: bool,
) -> str:
    """full=完整主谱 JSON；summary=会话摘要（后续轮次）。"""
    if refresh_context or not session or int(session.get("turn_count") or 0) <= 0:
        return "full"
    return "summary"
