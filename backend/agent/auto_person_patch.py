"""从对话自动提取成员字段并生成待确认写入。"""

from __future__ import annotations

from typing import Any

from agent.agent_runtime import AgentContext, AgentTurnResult
from agent.graph_store import GraphStore
from agent.person_intent import (
    extract_person_name_from_text,
    extract_person_patch_from_text,
    looks_like_person_update,
)
from agent.tool_executor import propose_write_tool


def _friendly_prefill_reply(tool_summary: str) -> str:
    return (
        "已从您的描述里提取成员信息，并自动填到右侧【成员】页，请核对字段。\n"
        "无误后请在对话卡片点「确认写入」保存到主谱；无需再手打一遍。\n\n"
        f"{tool_summary}"
    )


def try_auto_person_patch_turn(
    message: str,
    context: AgentContext,
    persons: list[dict],
    relations: list[dict],
    *,
    cursor,
    family_id: str,
) -> AgentTurnResult | None:
    """规则层：自然语言 → 字段提取 → 预填 UI + 待确认 patch。"""
    msg = (message or "").strip()
    if not cursor or not family_id or not looks_like_person_update(msg):
        return None

    patch = extract_person_patch_from_text(msg)
    if not patch:
        return None

    graph = GraphStore(persons, relations)
    params: dict[str, Any] = {"patch": dict(patch)}
    name = extract_person_name_from_text(msg)
    if name:
        params["person_name"] = name
    else:
        params["use_selected"] = True
        if not context.selected_person_id:
            params["use_anchor"] = True

    ctx = {
        "anchor_person_id": context.anchor_person_id,
        "selected_person_id": context.selected_person_id,
    }
    result = propose_write_tool(
        "propose_person_patch",
        params,
        cursor=cursor,
        family_id=family_id,
        graph=graph,
        persons=persons,
        context=ctx,
    )

    if not result.success and name and patch.get("name") == name:
        params = {"patch": {k: v for k, v in patch.items() if k != "name"}, "person_name": name}
        result = propose_write_tool(
            "propose_person_patch",
            params,
            cursor=cursor,
            family_id=family_id,
            graph=graph,
            persons=persons,
            context=ctx,
        )

    if not result.success:
        return AgentTurnResult(
            reply=result.summary,
            tool_calls=result.tool_calls,
            state_patch={"_used_llm": False},
        )

    if not result.confirmation:
        return AgentTurnResult(
            reply=result.summary,
            ui_actions=result.ui_actions,
            tool_calls=result.tool_calls,
            state_patch={**result.state_patch, "_used_llm": False},
        )

    turn = AgentTurnResult(
        reply=_friendly_prefill_reply(result.summary),
        ui_actions=result.ui_actions,
        tool_calls=result.tool_calls,
        state_patch=dict(result.state_patch),
    )
    turn.state_patch["_used_llm"] = False  # type: ignore
    turn.state_patch["_confirmation"] = result.confirmation  # type: ignore
    return turn
