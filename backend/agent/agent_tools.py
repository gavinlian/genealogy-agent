"""Agent 工具执行 — Phase 1 读谱 / 搜索 / UI 指令。"""

from __future__ import annotations

import re
from typing import Any

from agent.graph_store import GraphStore
from agent.search import search_persons


def _person_brief(p: dict) -> dict:
    return {
        "id": p.get("id"),
        "name": p.get("name"),
        "generation": p.get("generation"),
        "courtesy_name": p.get("courtesy_name"),
        "art_name": p.get("art_name"),
        "birth_year": p.get("birth_year"),
        "death_year": p.get("death_year"),
        "biography": (p.get("biography") or "")[:200] or None,
    }


def execute_search_persons(persons: list[dict], query: str, *, limit: int = 20) -> dict[str, Any]:
    hits = search_persons(persons, query, limit=limit)
    return {"success": True, "query": query, "count": len(hits), "people": hits}


def execute_get_person_detail(
    graph: GraphStore,
    person_id: str,
    *,
    source_excerpt: str = "",
) -> dict[str, Any]:
    person = graph.get_person(person_id)
    if not person:
        return {"success": False, "error": "成员不存在"}
    detail = _person_brief(person)
    if source_excerpt:
        detail["source_excerpt"] = source_excerpt[:400]
    detail["parents"] = [_person_brief(p) for p in graph.get_parents(person_id)]
    detail["children"] = [_person_brief(p) for p in graph.get_children(person_id)]
    return {"success": True, "person": detail}


def execute_query_relatives(
    graph: GraphStore,
    person_id: str,
    kind: str,
    *,
    depth: int = 3,
) -> dict[str, Any]:
    return graph.summarize_relatives(person_id, kind, depth=depth)


def execute_find_relationship(graph: GraphStore, person_a_id: str, person_b_id: str) -> dict[str, Any]:
    result = graph.find_relationship(person_a_id, person_b_id)
    return {"success": result.get("found", False), **result}


def ui_switch_tab(tab: str) -> dict[str, Any]:
    valid = {"tree", "source", "person", "diff", "organize"}
    tab = (tab or "tree").lower()
    if tab not in valid:
        tab = "tree"
    return {"type": "switch_tab", "tab": tab}


def ui_focus_person(person_id: str, name: str = "") -> dict[str, Any]:
    return {"type": "focus_person", "person_id": person_id, "name": name}


def ui_prefill_person(person_id: str, draft: dict[str, Any], *, person_name: str = "") -> dict[str, Any]:
    return {
        "type": "prefill_person",
        "person_id": person_id,
        "draft": draft,
        "name": person_name,
    }


def ui_set_anchor(person_id: str, name: str = "") -> dict[str, Any]:
    return {"type": "set_anchor", "person_id": person_id, "name": name}


def ui_open_classic(panel: str = "") -> dict[str, Any]:
    return {"type": "open_classic", "panel": (panel or "").strip().lower()}


def ui_open_settings() -> dict[str, Any]:
    return {"type": "open_settings"}


def ui_open_scan() -> dict[str, Any]:
    return {"type": "open_scan"}


def resolve_person_id(
    graph: GraphStore,
    *,
    name: str | None = None,
    person_id: str | None = None,
    anchor_person_id: str | None = None,
    selected_person_id: str | None = None,
) -> str | None:
    if person_id and graph.get_person(person_id):
        return person_id
    if name:
        hits = graph.find_by_name(name.strip())
        if len(hits) == 1:
            return hits[0]["id"]
        if len(hits) > 1:
            return hits[0]["id"]
    if selected_person_id and graph.get_person(selected_person_id):
        return selected_person_id
    if anchor_person_id and graph.get_person(anchor_person_id):
        return anchor_person_id
    return None


def extract_two_names(text: str) -> tuple[str | None, str | None]:
    """从「A和B什么关系」类问句提取两个姓名。"""
    m = re.search(
        r"([\u4e00-\u9fff]{2,4})\s*[和与跟]\s*([\u4e00-\u9fff]{2,4})",
        text,
    )
    if m:
        return m.group(1), m.group(2)
    return None, None
