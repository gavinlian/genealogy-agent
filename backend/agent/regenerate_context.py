"""为版本重生收集对话、主谱、旧稿等上下文。"""

from __future__ import annotations

from typing import Any

from agent_store import get_agent_state
from source_versions import VERSION_KIND_CUSTOM, VERSION_KIND_RELATION_DESC, find_version_by_kind


def _trim(text: str, limit: int) -> str:
    t = (text or "").strip()
    if len(t) <= limit:
        return t
    return t[:limit] + "…"


def _extract_chat_notes(messages: list[dict], *, limit: int = 12) -> str:
    """从 Agent 对话提取与用户整理族谱相关的片段。"""
    if not messages:
        return ""
    lines: list[str] = []
    keywords = (
        "整理", "关系", "OCR", "识别", "版本", "配偶", "父子", "补全",
        "修正", "谱", "人名", "写入", "重生", "生成",
    )
    for item in messages[-limit:]:
        role = item.get("role")
        content = (item.get("content") or "").strip()
        if not content or role not in ("user", "assistant"):
            continue
        if role == "user" or any(k in content for k in keywords):
            if role == "user" and len(content) <= 4 and not any(k in content for k in keywords):
                continue
            prefix = "用户" if role == "user" else "助手"
            lines.append(f"- {prefix}：{_trim(content, 400)}")
    return "\n".join(lines[-8:])


def build_regenerate_context(
    cursor,
    family_id: str,
    *,
    persons: list[dict] | None = None,
    previous_relation_text: str = "",
) -> dict[str, Any]:
    """汇总重生关系描述时可注入 prompt 的上下文。"""
    agent = get_agent_state(cursor, family_id)
    chat_notes = _extract_chat_notes(agent.get("messages") or [])

    v2 = find_version_by_kind(cursor, family_id, VERSION_KIND_RELATION_DESC)
    v3 = find_version_by_kind(cursor, family_id, VERSION_KIND_CUSTOM)
    prev_v2 = (v2.get("source_text") if v2 else "") or ""
    prev_v3 = (v3.get("source_text") if v3 else "") or ""
    previous_draft = (previous_relation_text or prev_v3 or prev_v2).strip()

    names: list[str] = []
    for p in persons or []:
        n = (p.get("name") or "").strip()
        if n and n not in names:
            names.append(n)
    genealogy_summary = ""
    if names:
        sample = "、".join(names[:25])
        extra = f" 等共 {len(names)} 人" if len(names) > 25 else f" 共 {len(names)} 人"
        genealogy_summary = f"主谱已有成员：{sample}{extra}"

    try:
        from ai_organize_store import get_ai_chat_state

        org = get_ai_chat_state(cursor, family_id)
        last_explanation = (org.get("session_meta") or {}).get("last_explanation") or ""
        if not last_explanation:
            last_explanation = (org.get("pending_plan") or {}).get("explanation") or ""
    except Exception:
        last_explanation = ""

    notes_parts: list[str] = []
    if chat_notes:
        notes_parts.append("【近期对话要点】\n" + chat_notes)
    if last_explanation:
        notes_parts.append("【上次 AI 整理说明】\n" + _trim(last_explanation, 600))
    if genealogy_summary:
        notes_parts.append("【主谱现状】\n" + genealogy_summary)

    return {
        "context_notes": "\n\n".join(notes_parts).strip(),
        "previous_draft": previous_draft,
        "genealogy_summary": genealogy_summary,
        "chat_turns": len(agent.get("messages") or []),
    }
