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
    ui_organize_regenerate,
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
    cursor=None,
    family_id: str = "",
    relations: list[dict] | None = None,
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

    if tool_name == "fuse_source_versions":
        if not cursor or not family_id:
            return ToolResult(False, "融合需要族谱上下文。", tool_calls=tool_calls)
        from agent.source_fusion import build_source_fusion

        fusion = build_source_fusion(
            cursor,
            family_id,
            tree_persons=persons,
            tree_relations=relations or [],
            include_tree=bool(params.get("include_tree", True)),
        )
        stats = fusion.get("stats") or {}
        excerpt = (fusion.get("stepped_text") or "")[:3500]
        summary = (
            f"已融合 {stats.get('version_count', 0)} 个原文版本，"
            f"合并 {stats.get('merged_relation_count', 0)} 条关系、"
            f"{stats.get('merged_person_count', 0)} 位人物。\n\n"
            f"{excerpt}"
        )
        if len(fusion.get("stepped_text") or "") > 3500:
            summary += "\n\n（全文较长，可说「保存融合稿」写入原文版本。）"
        ui_actions.append(ui_switch_tab("fusion"))
        return ToolResult(
            True,
            summary,
            ui_actions=ui_actions,
            tool_calls=tool_calls,
            state_patch={"active_tab": "fusion", "_fusion_preview": fusion.get("stepped_text")},
            data=fusion,
        )

    return ToolResult(False, f"未知读工具：{tool_name}", tool_calls=tool_calls)


async def execute_regenerate_source_tool(
    params: dict[str, Any],
    *,
    cursor,
    family_id: str,
    ai_configured: bool,
) -> ToolResult:
    """AI 重新生成版本一 OCR 或版本二关系描述，并写入原文版本库。"""
    tool_calls = [{"tool": "regenerate_source_version", "params": params}]
    if not cursor or not family_id:
        return ToolResult(False, "重生原文需要族谱上下文。", tool_calls=tool_calls)
    if not ai_configured:
        return ToolResult(
            False,
            "AI 重生需要先在设置中配置 OCR / 关系解析模型。",
            tool_calls=tool_calls,
        )

    kind = (params.get("kind") or params.get("target") or "relation_desc").strip().lower()
    if kind in ("ocr", "v1", "version1", "ocr_raw", "ocr原文", "版本一"):
        kind = "ocr_raw"
    else:
        kind = "relation_desc"

    # 延迟导入，避免 main ↔ agent 循环依赖
    from main import UPLOAD_DIR, call_text_model, call_vision_model, load_model_selection
    from agent.source_regenerate import (
        preview_excerpt,
        regenerate_ocr_raw,
        regenerate_relation_desc,
    )

    sel = load_model_selection()
    ocr_cfg = sel.get("ocr") or {}
    parse_cfg = sel.get("parse") or {}
    ocr_provider = ocr_cfg.get("provider") or "minimax"
    ocr_model = ocr_cfg.get("model") or ""
    parse_provider = parse_cfg.get("provider") or "minimax"
    parse_model = parse_cfg.get("model") or ""

    async def vision_fn(provider, model, img, prompt):
        return await call_vision_model(provider, model, img, prompt)

    async def text_fn(provider, model, prompt, max_tokens=4096):
        return await call_text_model(provider, model, prompt, max_tokens=max_tokens)

    ui_actions: list[dict] = [ui_switch_tab("organize"), ui_organize_regenerate(kind, synced=True)]
    state_patch: dict[str, Any] = {"active_tab": "organize"}

    if kind == "ocr_raw":
        result = await regenerate_ocr_raw(
            cursor,
            family_id,
            UPLOAD_DIR,
            ocr_provider=ocr_provider,
            ocr_model=ocr_model,
            vision_fn=vision_fn,
        )
    else:
        from agent.regenerate_context import build_regenerate_context
        from source_versions import VERSION_KIND_CUSTOM, VERSION_KIND_RELATION_DESC

        persons_rows = cursor.execute(
            "SELECT name FROM persons WHERE family_id = ?", (family_id,),
        ).fetchall()
        persons = [{"name": r["name"]} for r in persons_rows]
        ctx = build_regenerate_context(cursor, family_id, persons=persons)
        target_kind = VERSION_KIND_CUSTOM if kind == "custom" else VERSION_KIND_RELATION_DESC

        result = await regenerate_relation_desc(
            cursor,
            family_id,
            parse_provider=parse_provider,
            parse_model=parse_model,
            text_fn=text_fn,
            ocr_text=(params.get("ocr_text") or "").strip() or None,
            target_kind=target_kind,
            context_notes=ctx.get("context_notes") or "",
            previous_draft=ctx.get("previous_draft") or "",
        )

    tool_calls[0]["result"] = result
    if not result.get("success"):
        return ToolResult(
            False,
            result.get("error") or "AI 重生失败",
            ui_actions=[ui_switch_tab("organize")],
            tool_calls=tool_calls,
            state_patch={"active_tab": "organize"},
        )

    text = (result.get("text") or "").strip()
    char_count = result.get("char_count") or len(text)
    label = "版本一 · OCR 原文" if kind == "ocr_raw" else (
        "版本三 · 修正稿" if kind == "custom" else "版本二 · 关系描述"
    )
    excerpt = preview_excerpt(text, 320)
    if result.get("used_ai"):
        summary = (
            f"已用 AI 重新生成【{label}】并写入原文库（共 {char_count} 字）。\n\n"
            f"节选：\n{excerpt}\n\n"
            "已打开整理页，请核对关系图后写入主谱。"
        )
    else:
        summary = (
            result.get("message")
            or f"已生成【{label}】草稿（共 {char_count} 字）。\n\n节选：\n{excerpt}"
        )
    return ToolResult(
        True,
        summary,
        ui_actions=ui_actions,
        tool_calls=tool_calls,
        state_patch=state_patch,
        data=result,
    )


def propose_write_tool(
    tool_name: str,
    params: dict[str, Any],
    *,
    cursor,
    family_id: str,
    graph: GraphStore,
    persons: list[dict],
    relations: list[dict] | None = None,
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

    if tool_name == "propose_save_fusion":
        from agent.source_fusion import build_source_fusion

        stepped = (params.get("stepped_text") or params.get("fusion_text") or "").strip()
        if not stepped:
            fusion = build_source_fusion(
                cursor,
                family_id,
                tree_persons=persons,
                tree_relations=relations or [],
                include_tree=True,
            )
            stepped = fusion.get("stepped_text") or ""
        if not stepped:
            return ToolResult(False, "暂无内容可保存为融合稿，请先执行多版本融合。", tool_calls=tool_calls)
        preview = stepped[:800] + ("…" if len(stepped) > 800 else "")
        summary = f"将保存「融合稿 · 多版合并」原文版本（约 {len(stepped)} 字）。"
        token = create_pending_action(
            cursor,
            family_id,
            tool_name,
            {"stepped_text": stepped},
            summary=summary,
        )
        confirmation = {
            "token": token,
            "tool": tool_name,
            "title": "确认保存融合稿",
            "summary": summary,
            "details": {"preview": preview, "char_count": len(stepped)},
        }
        return ToolResult(
            True,
            summary + "\n\n请在下方卡片确认后写入原文版本库。",
            ui_actions=[ui_switch_tab("source")],
            tool_calls=tool_calls,
            state_patch={"active_tab": "source"},
            confirmation=confirmation,
        )

    if tool_name == "propose_merge_family":
        from agent.family_merge import build_family_merge_preview, resolve_source_family_id

        user_id = (context.get("user_id") or "local-default").strip()
        source_id = resolve_source_family_id(
            cursor,
            user_id,
            source_family_id=params.get("source_family_id"),
            source_family_name=params.get("source_family_name"),
            exclude_family_id=family_id,
        )
        if not source_id:
            hint = "请说明要合并哪一份族谱（名称或 id）。"
            if context.get("other_families"):
                names = "、".join(
                    f.get("name", "") for f in context["other_families"][:8] if f.get("name")
                )
                if names:
                    hint += f" 可选：{names}"
            return ToolResult(False, hint, tool_calls=tool_calls)
        try:
            preview = build_family_merge_preview(cursor, family_id, source_id, user_id)
        except ValueError as exc:
            return ToolResult(False, str(exc), tool_calls=tool_calls)
        summary = preview.get("summary") or "族谱合并预览"
        stats = preview.get("stats") or {}
        token = create_pending_action(
            cursor,
            family_id,
            tool_name,
            {
                "source_family_id": source_id,
                "source_family_name": preview.get("source_family_name"),
                "user_id": user_id,
            },
            summary=summary,
        )
        confirmation = {
            "token": token,
            "tool": tool_name,
            "title": "确认合并族谱",
            "summary": summary,
            "details": {
                "stats": stats,
                "preview": preview.get("preview") or {},
                "source_family_name": preview.get("source_family_name"),
                "target_family_name": preview.get("target_family_name"),
            },
        }
        return ToolResult(
            True,
            summary + "\n\n请在下方卡片确认后才会写入当前族谱。",
            ui_actions=[ui_switch_tab("fusion")],
            tool_calls=tool_calls,
            state_patch={"active_tab": "fusion"},
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
    summary = result.get("explanation") or "已生成整理方案。"
    apply_mode = params.get("apply_mode") or "merge"
    from ai_organize_store import save_ai_chat_state

    save_ai_chat_state(
        cursor,
        family_id,
        {
            "pending_plan": plan,
            "pending_diff": diff,
            "apply_mode": apply_mode,
        },
    )
    if stats:
        summary += (
            f"\n预计：+{stats.get('persons_added', 0)} 人，"
            f"更新 {stats.get('persons_updated', 0)} 人，"
            f"关系 +{stats.get('relations_added', 0)}"
        )
    return ToolResult(
        True,
        summary + "\n\n已切到「整理」页，请核对关系卡片后点「写入主谱」。",
        ui_actions=[ui_switch_tab("organize")],
        tool_calls=[{"tool": "propose_organize_plan", "params": params, "used_ai": result.get("used_ai")}],
        state_patch={"active_tab": "organize"},
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

    if tool_name == "propose_save_fusion":
        from agent.source_fusion import save_fusion_as_version

        text = (payload.get("stepped_text") or "").strip()
        if not text:
            return {"success": False, "error": "融合稿为空"}
        version = save_fusion_as_version(cursor, family_id, text)
        return {
            "success": True,
            "message": "已保存为多版本融合原文（融合稿版本）。",
            "version_id": version.get("id"),
        }

    if tool_name == "propose_merge_family":
        from agent.family_merge import apply_family_merge

        source_id = (payload.get("source_family_id") or "").strip()
        user_id = (payload.get("user_id") or "local-default").strip()
        if not source_id:
            return {"success": False, "error": "缺少源族谱 id"}
        try:
            result = apply_family_merge(
                cursor, family_id, source_id, user_id, now, merge_ocr_text=True,
            )
        except ValueError as exc:
            return {"success": False, "error": str(exc)}
        return {
            "success": True,
            "message": result.get("message") or "族谱合并完成。",
            **{k: v for k, v in result.items() if k not in ("success", "message")},
        }

    return {"success": False, "error": f"不支持的应用操作：{tool_name}"}
