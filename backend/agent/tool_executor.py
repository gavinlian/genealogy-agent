"""Agent 工具执行 — 读操作即时返回，写操作生成待确认 token。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from agent.agent_tools import (
    execute_find_relationship,
    execute_get_person_detail,
    execute_query_relatives,
    execute_search_persons,
    resolve_person_id,
    ui_focus_person,
    ui_open_classic,
    ui_open_scan,
    ui_open_settings,
    ui_prefill_person,
    ui_set_anchor,
    ui_switch_tab,
)
from agent.graph_store import GraphStore
from agent.pending_actions import create_pending_action
from agent.source_person_sync import apply_person_detail_patches, compute_person_detail_patches

AiFn = Callable[[str], Awaitable[tuple[str, str]]]

PATCHABLE_FIELDS = frozenset({
    "name", "gender", "birth_year", "death_year", "generation", "generation_name",
    "courtesy_name", "art_name", "county", "town", "village", "biography",
})

RELATIVE_KINDS = frozenset({
    "cousins", "siblings", "parents", "children", "ancestors", "descendants",
})


@dataclass
class ToolResult:
    success: bool
    summary: str
    ui_actions: list[dict[str, Any]] = field(default_factory=list)
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    state_patch: dict[str, Any] = field(default_factory=dict)
    confirmation: dict[str, Any] | None = None
    data: dict[str, Any] | None = None


def _resolve_subject_id(
    graph: GraphStore,
    params: dict,
    *,
    anchor_person_id: str | None,
    selected_person_id: str | None,
) -> str | None:
    pid = params.get("person_id")
    if pid and graph.get_person(str(pid)):
        return str(pid)
    name = (params.get("person_name") or params.get("name") or "").strip()
    if name:
        resolved = resolve_person_id(graph, name=name)
        if resolved:
            return resolved
    if params.get("use_selected") and selected_person_id:
        return selected_person_id
    if params.get("use_anchor") and anchor_person_id:
        return anchor_person_id
    if selected_person_id and graph.get_person(selected_person_id):
        return selected_person_id
    if anchor_person_id and graph.get_person(anchor_person_id):
        return anchor_person_id
    return None


def execute_read_tool(
    tool_name: str,
    params: dict[str, Any],
    *,
    graph: GraphStore,
    persons: list[dict],
    context: dict[str, Any],
    source_excerpt_fn=None,
    source_text: str = "",
) -> ToolResult:
    anchor = context.get("anchor_person_id")
    selected = context.get("selected_person_id")
    ui_actions: list[dict] = []
    state_patch: dict[str, Any] = {}
    tool_calls: list[dict] = [{"tool": tool_name, "params": params}]

    if tool_name == "search_persons":
        query = (params.get("query") or "").strip()
        if not query:
            return ToolResult(False, "请提供要搜索的姓名或关键字。")
        result = execute_search_persons(persons, query)
        tool_calls[0]["result"] = result
        people = result.get("people") or []
        if not people:
            return ToolResult(True, f"未找到与「{query}」匹配的成员。", tool_calls=tool_calls)
        lines = []
        for p in people[:15]:
            extra = []
            if p.get("courtesy_name"):
                extra.append(f"字{p['courtesy_name']}")
            if p.get("generation"):
                extra.append(f"第{p['generation']}代")
            suffix = f"（{'，'.join(extra)}）" if extra else ""
            lines.append(f"- {p.get('name')}{suffix}")
        summary = f"找到 {len(people)} 位相关成员：\n" + "\n".join(lines)
        if len(people) == 1:
            pid = people[0]["id"]
            ui_actions.extend([ui_focus_person(pid, people[0].get("name", "")), ui_switch_tab("person")])
            state_patch.update({"selected_person_id": pid, "active_tab": "person"})
        return ToolResult(True, summary, ui_actions=ui_actions, tool_calls=tool_calls, state_patch=state_patch)

    if tool_name == "query_relatives":
        kind = (params.get("kind") or "siblings").strip().lower()
        if kind not in RELATIVE_KINDS:
            kind = "siblings"
        subject_id = _resolve_subject_id(graph, params, anchor_person_id=anchor, selected_person_id=selected)
        if not subject_id:
            return ToolResult(
                False,
                "请先在顶栏设置「我在谱中是谁」，或在树图选中成员后再问亲属关系。",
                tool_calls=tool_calls,
            )
        result = execute_query_relatives(graph, subject_id, kind)
        tool_calls[0]["result"] = result
        person = result.get("person") or {}
        kind_labels = {
            "cousins": "堂/表兄弟姐妹",
            "siblings": "兄弟姐妹",
            "parents": "父母",
            "children": "子女",
            "ancestors": "祖先",
            "descendants": "后代",
        }
        label = kind_labels.get(kind, kind)
        rel_people = result.get("people") or []
        if not rel_people:
            summary = f"【{person.get('name', '该成员')}】暂无记录的{label}。"
        else:
            lines = [f"- {p.get('name')}" for p in rel_people[:15]]
            summary = f"【{person.get('name', '该成员')}】的{label}：\n" + "\n".join(lines)
        ui_actions.extend([ui_switch_tab("tree"), ui_focus_person(subject_id, person.get("name", ""))])
        state_patch.update({"selected_person_id": subject_id, "active_tab": "tree"})
        return ToolResult(True, summary, ui_actions=ui_actions, tool_calls=tool_calls, state_patch=state_patch)

    if tool_name == "find_relationship":
        name_a = (params.get("person_a") or params.get("name_a") or "").strip()
        name_b = (params.get("person_b") or params.get("name_b") or "").strip()
        if not name_a or not name_b:
            return ToolResult(False, "请提供两位成员的姓名。", tool_calls=tool_calls)
        id_a = resolve_person_id(graph, name=name_a)
        id_b = resolve_person_id(graph, name=name_b)
        if not id_a:
            return ToolResult(False, f"未找到成员「{name_a}」。", tool_calls=tool_calls)
        if not id_b:
            return ToolResult(False, f"未找到成员「{name_b}」。", tool_calls=tool_calls)
        result = execute_find_relationship(graph, id_a, id_b)
        tool_calls[0]["result"] = result
        ui_actions.extend([ui_switch_tab("tree"), ui_focus_person(id_a, name_a)])
        state_patch.update({"selected_person_id": id_a, "active_tab": "tree"})
        return ToolResult(True, result.get("summary", "未能判断关系"), ui_actions=ui_actions, tool_calls=tool_calls, state_patch=state_patch)

    if tool_name == "get_person_detail":
        subject_id = _resolve_subject_id(graph, params, anchor_person_id=anchor, selected_person_id=selected)
        if not subject_id:
            return ToolResult(False, "请指定成员姓名或在页面选中一人。", tool_calls=tool_calls)
        excerpt = source_excerpt_fn(subject_id) if source_excerpt_fn else ""
        result = execute_get_person_detail(graph, subject_id, source_excerpt=excerpt)
        tool_calls[0]["result"] = result
        p = result.get("person") or {}
        parts = [f"【{p.get('name', '未知')}】"]
        if p.get("generation"):
            parts.append(f"第{p['generation']}代")
        if p.get("courtesy_name") or p.get("art_name"):
            parts.append(f"字{p.get('courtesy_name') or '—'}，号{p.get('art_name') or '—'}")
        if p.get("biography"):
            parts.append(f"\n{p['biography'][:300]}")
        ui_actions.extend([ui_switch_tab("person"), ui_focus_person(subject_id, p.get("name", ""))])
        state_patch.update({"selected_person_id": subject_id, "active_tab": "person"})
        return ToolResult(True, " ".join(parts[:3]) + (parts[3] if len(parts) > 3 else ""), ui_actions=ui_actions, tool_calls=tool_calls, state_patch=state_patch)

    if tool_name == "get_source_text":
        text = (source_text or "").strip()
        if not text:
            return ToolResult(True, "当前暂无原文/文字版。", tool_calls=tool_calls)
        preview = text[:500] + ("…" if len(text) > 500 else "")
        ui_actions.append(ui_switch_tab("source"))
        state_patch["active_tab"] = "source"
        return ToolResult(True, f"原文共 {len(text)} 字，节选：\n{preview}", ui_actions=ui_actions, tool_calls=tool_calls, state_patch=state_patch)

    if tool_name == "ui_switch_tab":
        tab = (params.get("tab") or "tree").strip().lower()
        ui_actions.append(ui_switch_tab(tab))
        state_patch["active_tab"] = tab
        labels = {"tree": "树图", "source": "原文", "person": "成员", "diff": "对比", "organize": "整理"}
        return ToolResult(True, f"已切换到【{labels.get(tab, tab)}】页面。", ui_actions=ui_actions, tool_calls=tool_calls, state_patch=state_patch)

    if tool_name == "ui_focus_person":
        subject_id = _resolve_subject_id(graph, params, anchor_person_id=anchor, selected_person_id=selected)
        if not subject_id:
            return ToolResult(False, "未找到要定位的成员。", tool_calls=tool_calls)
        person = graph.get_person(subject_id) or {}
        ui_actions.extend([ui_focus_person(subject_id, person.get("name", "")), ui_switch_tab("person")])
        state_patch.update({"selected_person_id": subject_id, "active_tab": "person"})
        return ToolResult(True, f"已定位到【{person.get('name', '成员')}】。", ui_actions=ui_actions, tool_calls=tool_calls, state_patch=state_patch)

    if tool_name == "ui_set_anchor":
        subject_id = _resolve_subject_id(graph, params, anchor_person_id=anchor, selected_person_id=selected)
        if not subject_id:
            return ToolResult(False, "未找到要设为「我在谱中」的成员。", tool_calls=tool_calls)
        person = graph.get_person(subject_id) or {}
        ui_actions.append(ui_set_anchor(subject_id, person.get("name", "")))
        state_patch["anchor_person_id"] = subject_id
        return ToolResult(
            True,
            f"已设置「我在谱中是谁」为【{person.get('name', '成员')}】。",
            ui_actions=ui_actions,
            tool_calls=tool_calls,
            state_patch=state_patch,
        )

    if tool_name == "ui_open_classic":
        panel = (params.get("panel") or params.get("tab") or "").strip().lower()
        ui_actions.append(ui_open_classic(panel))
        return ToolResult(
            True,
            f"已打开经典编辑{' · ' + panel if panel else ''}（完整 CRUD/OCR/整理/对比）。",
            ui_actions=ui_actions,
            tool_calls=tool_calls,
        )

    if tool_name == "ui_open_settings":
        ui_actions.append(ui_open_settings())
        return ToolResult(True, "已打开设置。", ui_actions=ui_actions, tool_calls=tool_calls)

    if tool_name == "ui_open_scan":
        ui_actions.append(ui_open_scan())
        return ToolResult(True, "已打开扫描建谱。", ui_actions=ui_actions, tool_calls=tool_calls)

    return ToolResult(False, f"未知读工具：{tool_name}", tool_calls=tool_calls)


def propose_write_tool(
    tool_name: str,
    params: dict[str, Any],
    *,
    cursor,
    family_id: str,
    graph: GraphStore,
    persons: list[dict],
    context: dict[str, Any],
) -> ToolResult:
    anchor = context.get("anchor_person_id")
    selected = context.get("selected_person_id")
    tool_calls = [{"tool": tool_name, "params": params}]

    if tool_name == "propose_person_patch":
        subject_id = _resolve_subject_id(graph, params, anchor_person_id=anchor, selected_person_id=selected)
        if not subject_id:
            return ToolResult(False, "请指定要修改的成员（姓名或在成员页选中）。", tool_calls=tool_calls)
        person = graph.get_person(subject_id) or {}
        raw_patch = params.get("patch") or params.get("fields") or params
        patch = {k: v for k, v in raw_patch.items() if k in PATCHABLE_FIELDS and v is not None and v != ""}
        if not patch:
            return ToolResult(False, "未提供有效字段更新。", tool_calls=tool_calls)
        changes = []
        for k, v in patch.items():
            old = person.get(k)
            if str(old) != str(v):
                changes.append({"field": k, "from": old, "to": v})
        if not changes:
            return ToolResult(True, "字段与当前主谱一致，无需修改。", tool_calls=tool_calls)
        payload = {"person_id": subject_id, "patch": patch, "person_name": person.get("name")}
        summary = f"更新【{person.get('name')}】：" + "；".join(
            f"{c['field']} {c['from'] or '空'} → {c['to']}" for c in changes
        )
        token = create_pending_action(cursor, family_id, tool_name, payload, summary=summary)
        confirmation = {
            "token": token,
            "tool": tool_name,
            "title": "确认更新成员",
            "summary": summary,
            "details": {
                "changes": changes,
                "person_name": person.get("name"),
                "person_id": subject_id,
                "draft": patch,
            },
        }
        ui_actions = [
            ui_switch_tab("person"),
            ui_focus_person(subject_id, person.get("name", "")),
            ui_prefill_person(subject_id, patch, person_name=person.get("name", "")),
        ]
        return ToolResult(
            True,
            summary + "\n\n字段已预填到成员页，请在下方卡片确认后才会写入主谱。",
            ui_actions=ui_actions,
            tool_calls=tool_calls,
            state_patch={
                "selected_person_id": subject_id,
                "active_tab": "person",
                "person_draft": {"person_id": subject_id, "patch": patch},
            },
            confirmation=confirmation,
        )

    if tool_name == "propose_sync_person_details":
        source_text = (params.get("source_text") or context.get("source_text") or "").strip()
        if not source_text:
            return ToolResult(False, "暂无原文，无法同步字段。", tool_calls=tool_calls)
        patches = compute_person_detail_patches(persons, source_text)
        if not patches:
            return ToolResult(True, "原文与主谱字段已一致，无需回填。", tool_calls=tool_calls)
        preview = [
            {"name": p.get("name"), "fields": [k for k in p if k not in ("name", "person_id")]}
            for p in patches[:20]
        ]
        summary = f"将从原文向 {len(patches)} 位成员回填空字段（仅补空，不覆盖已有值）。"
        payload = {"patches": patches}
        token = create_pending_action(cursor, family_id, tool_name, payload, summary=summary)
        confirmation = {
            "token": token,
            "tool": tool_name,
            "title": "确认字段同步",
            "summary": summary,
            "details": {"patches_preview": preview, "count": len(patches)},
        }
        ui_actions = [ui_switch_tab("person")]
        return ToolResult(
            True,
            summary + "\n\n请在下方卡片确认后才会写入主谱。",
            ui_actions=ui_actions,
            tool_calls=tool_calls,
            state_patch={"active_tab": "person"},
            confirmation=confirmation,
        )

    return ToolResult(False, f"未知写工具：{tool_name}", tool_calls=tool_calls)


async def propose_organize_tool(
    params: dict[str, Any],
    *,
    cursor,
    family_id: str,
    persons: list[dict],
    relations: list[dict],
    source_text: str,
    ai_fn: AiFn,
    ai_configured: bool,
    history: list[dict] | None = None,
) -> ToolResult:
    from agent.genealogy_organizer import organize_genealogy_with_chat

    message = (params.get("message") or params.get("instruction") or "").strip()
    if not message:
        return ToolResult(False, "请说明要如何整理族谱。")

    result = await organize_genealogy_with_chat(
        persons,
        relations,
        message,
        ai_fn,
        source_text=source_text,
        history=history or [],
        ai_configured=ai_configured,
    )
    if not result.get("success"):
        return ToolResult(False, result.get("error") or result.get("message") or "整理方案生成失败")

    plan = result.get("plan")
    if not plan:
        return ToolResult(True, result.get("explanation") or "未生成可应用的整理方案。")

    diff = result.get("diff") or {}
    stats = (result.get("preview") or {}).get("stats") or {}
    summary = result.get("explanation") or "已生成整理方案，请确认后应用。"
    detail_lines = []
    if stats:
        detail_lines.append(
            f"预计：+{stats.get('persons_added', 0)} 人，"
            f"更新 {stats.get('persons_updated', 0)} 人，"
            f"关系 +{stats.get('relations_added', 0)}"
        )
    payload = {
        "plan": plan,
        "apply_mode": params.get("apply_mode") or "merge",
        "message": message,
    }
    token = create_pending_action(cursor, family_id, "propose_organize_plan", payload, summary=summary[:500])
    confirmation = {
        "token": token,
        "tool": "propose_organize_plan",
        "title": "确认应用整理方案",
        "summary": summary,
        "details": {
            "stats": stats,
            "diff_summary": {
                "persons_added": len(diff.get("persons_added") or []),
                "persons_updated": len(diff.get("persons_updated") or []),
                "relations_added": len(diff.get("relations_added") or []),
            },
            "explanation": summary,
        },
    }
    return ToolResult(
        True,
        summary + "\n\n请在下方卡片确认后才会写入主谱。",
        ui_actions=[ui_switch_tab("organize")],
        tool_calls=[{"tool": "propose_organize_plan", "params": params, "used_ai": result.get("used_ai")}],
        state_patch={"active_tab": "organize"},
        confirmation=confirmation,
        data={"plan": plan, "diff": diff},
    )


def apply_pending_action(
    cursor,
    family_id: str,
    pending: dict[str, Any],
    *,
    persons: list[dict],
    now: str,
) -> dict[str, Any]:
    tool_name = pending.get("tool_name")
    payload = pending.get("payload") or {}

    if tool_name == "propose_person_patch":
        person_id = payload.get("person_id")
        patch = payload.get("patch") or {}
        row = cursor.execute("SELECT * FROM persons WHERE id = ? AND family_id = ?", (person_id, family_id)).fetchone()
        if not row:
            return {"success": False, "error": "成员不存在"}
        person = dict(row)
        merged = {**person, **patch, "id": person_id}
        cursor.execute(
            """UPDATE persons SET name=?, gender=?, birth_year=?, death_year=?, generation=?,
               generation_name=?, courtesy_name=?, art_name=?, county=?, town=?, village=?, biography=?
               WHERE id=? AND family_id=?""",
            (
                merged.get("name"), merged.get("gender"), merged.get("birth_year"), merged.get("death_year"),
                merged.get("generation"), merged.get("generation_name"),
                merged.get("courtesy_name"), merged.get("art_name"),
                merged.get("county"), merged.get("town"), merged.get("village"), merged.get("biography"),
                person_id, family_id,
            ),
        )
        return {"success": True, "message": f"已更新【{person.get('name')}】的字段。", "person_id": person_id}

    if tool_name == "propose_sync_person_details":
        patches = payload.get("patches") or []
        stats = apply_person_detail_patches(cursor, family_id, persons, patches, now)
        return {
            "success": True,
            "message": f"已从原文回填 {stats.get('persons_updated', 0)} 位成员的空字段。",
            **stats,
        }

    if tool_name == "propose_organize_plan":
        return {"success": False, "error": "整理方案请在 main.apply 路径执行", "needs_main_apply": True, "payload": payload}

    return {"success": False, "error": f"不支持的应用操作：{tool_name}"}
