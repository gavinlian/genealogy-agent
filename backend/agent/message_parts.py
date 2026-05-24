"""对话 message_parts — 结构化 UI 片段（Generative UI / 模式 A 的 Vue 落地）。"""

from __future__ import annotations

from typing import Any

FIELD_LABELS: dict[str, str] = {
    "name": "姓名",
    "gender": "性别",
    "birth_year": "生年",
    "death_year": "卒年",
    "generation": "世代",
    "generation_name": "字辈",
    "courtesy_name": "字",
    "art_name": "号",
    "county": "县",
    "town": "镇",
    "village": "村",
    "biography": "简介",
}


def text_part(content: str) -> dict[str, Any]:
    return {"type": "text", "content": (content or "").strip()}


def _person_summary(person: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": person.get("id"),
        "name": person.get("name") or "未知",
        "courtesy_name": person.get("courtesy_name") or "",
        "generation": person.get("generation"),
    }


def _person_card_data(person: dict[str, Any], *, source_excerpt: str = "") -> dict[str, Any]:
    return {
        "id": person.get("id"),
        "name": person.get("name") or "未知",
        "courtesy_name": person.get("courtesy_name") or "",
        "art_name": person.get("art_name") or "",
        "generation": person.get("generation"),
        "birth_year": person.get("birth_year"),
        "death_year": person.get("death_year"),
        "biography": (person.get("biography") or "")[:200],
        "source_excerpt": (source_excerpt or "")[:320],
    }


def person_card_part(person: dict[str, Any], *, source_excerpt: str = "") -> dict[str, Any]:
    return {"type": "person_card", "data": _person_card_data(person, source_excerpt=source_excerpt)}


def field_diff_part(changes: list[dict[str, Any]], *, title: str = "从对话提取的字段") -> dict[str, Any]:
    return {"type": "field_diff", "data": {"title": title, "changes": changes}}


def create_family_preview_part(
    *,
    name: str,
    surname: str = "",
    description: str = "",
    status: str = "pending",
    family_id: str = "",
) -> dict[str, Any]:
    return {
        "type": "create_family_preview",
        "data": {
            "name": name,
            "surname": surname or "",
            "description": description or "",
            "status": status,
            "family_id": family_id or "",
        },
    }


def _draft_to_changes(draft: dict[str, Any]) -> list[dict[str, Any]]:
    changes: list[dict[str, Any]] = []
    for key, val in draft.items():
        if val in (None, ""):
            continue
        changes.append({
            "field": FIELD_LABELS.get(key, key),
            "from": None,
            "to": val,
        })
    return changes


def build_family_message_parts(
    *,
    reply: str,
    ui_actions: list[dict[str, Any]] | None = None,
    tool_calls: list[dict[str, Any]] | None = None,
    confirmation: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """族谱工作区 Agent 回合 → 可渲染 parts。"""
    parts: list[dict[str, Any]] = []
    if reply:
        parts.append(text_part(reply))

    seen: set[str] = set()

    for action in ui_actions or []:
        if action.get("type") == "prefill_person" and not confirmation:
            draft = action.get("draft") or {}
            changes = _draft_to_changes(draft)
            if changes:
                key = "prefill:" + str(action.get("person_id"))
                if key not in seen:
                    seen.add(key)
                    parts.append(field_diff_part(changes, title="已从对话提取 · 待确认写入"))

    if confirmation:
        details = confirmation.get("details") or {}
        changes = details.get("changes") or []
        if changes and "confirm" not in seen:
            seen.add("confirm")
            parts.append(field_diff_part(changes, title=confirmation.get("title") or "待确认修改"))

    for tc in tool_calls or []:
        tool = tc.get("tool") or ""
        result = tc.get("result") or {}
        if tool == "search_persons":
            people = result.get("people") or []
            if len(people) == 1:
                pid = people[0].get("id")
                if pid and f"person:{pid}" not in seen:
                    seen.add(f"person:{pid}")
                    parts.append(person_card_part(people[0]))
            elif len(people) > 1:
                parts.append({
                    "type": "search_results",
                    "data": {
                        "title": f"找到 {len(people)} 位成员",
                        "people": [_person_summary(p) for p in people[:10]],
                        "total": len(people),
                    },
                })
        elif tool == "get_person_detail":
            person = result.get("person") or {}
            pid = person.get("id")
            if pid and f"person:{pid}" not in seen:
                seen.add(f"person:{pid}")
                parts.append(person_card_part(person, source_excerpt=result.get("source_excerpt") or ""))
        elif tool == "query_relatives":
            subject = result.get("person") or {}
            pid = subject.get("id")
            if pid and f"person:{pid}" not in seen:
                seen.add(f"person:{pid}")
                parts.append(person_card_part(subject))
            rel_people = result.get("people") or []
            if rel_people:
                parts.append({
                    "type": "search_results",
                    "data": {
                        "title": "亲属列表",
                        "people": [_person_summary(p) for p in rel_people[:10]],
                        "total": len(rel_people),
                    },
                })

    return parts


def build_home_message_parts(
    *,
    reply: str,
    raw_actions: list[dict[str, Any]] | None = None,
    materialized_actions: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """首页 Agent 回合 → 可渲染 parts。"""
    parts: list[dict[str, Any]] = []
    if reply:
        parts.append(text_part(reply))

    created_id = ""
    created_name = ""
    for ma in materialized_actions or []:
        if ma.get("type") == "select_family":
            created_id = ma.get("family_id") or ""
            created_name = ma.get("family_name") or ""

    preview_added = False
    for action in raw_actions or []:
        if action.get("type") != "create_family":
            continue
        name = (action.get("name") or "").strip()
        if not name:
            continue
        status = "created" if created_id else "pending"
        parts.append(create_family_preview_part(
            name=name,
            surname=str(action.get("surname") or ""),
            description=str(action.get("description") or ""),
            status=status,
            family_id=created_id,
        ))
        preview_added = True
        break

    if not preview_added and created_id and created_name:
        parts.append(create_family_preview_part(
            name=created_name,
            status="created",
            family_id=created_id,
        ))

    return parts
