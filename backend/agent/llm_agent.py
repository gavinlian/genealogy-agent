"""LLM Agent — 多轮对话 + 工具执行 + 写操作确认。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from agent.agent_runtime import AgentContext, AgentTurnResult, run_agent_turn
from agent.auto_person_patch import try_auto_person_patch_turn
from agent.graph_store import GraphStore
from agent.parser import extract_json_content, _strip_llm_wrappers
from agent.tool_executor import (
    AiFn,
    execute_read_tool,
    propose_organize_tool,
    propose_write_tool,
)

ChatFn = Callable[[list[dict[str, str]]], Awaitable[tuple[str, str]]]

READ_TOOLS = frozenset({
    "search_persons", "query_relatives", "find_relationship", "get_person_detail",
    "get_source_text", "ui_switch_tab", "ui_focus_person",
    "ui_set_anchor", "ui_open_classic", "ui_open_settings", "ui_open_scan",
})
WRITE_TOOLS = frozenset({
    "propose_person_patch", "propose_sync_person_details", "propose_organize_plan",
})


@dataclass
class LlmAgentDeps:
    chat_fn: ChatFn
    ai_fn: AiFn | None
    ai_configured: bool
    cursor: Any = None
    family_id: str = ""
    source_text: str = ""
    source_excerpt_fn: Callable[[str], str] | None = None
    message_history: list[dict] | None = None


def _compact_person_names(persons: list[dict], limit: int = 40) -> str:
    names = [p.get("name") for p in persons if p.get("name")][:limit]
    if not names:
        return "（尚无成员）"
    suffix = f" …共{len(persons)}人" if len(persons) > limit else ""
    return "、".join(names) + suffix


def build_agent_system_prompt(
    context: AgentContext,
    persons: list[dict],
    *,
    anchor_name: str = "",
    selected_name: str = "",
) -> str:
    tool_doc = """
可用工具（仅在需要查库/改库/切页时 call_tool，一次一个）：

读操作：
- search_persons: { "query": "..." }
- query_relatives: { "kind": "cousins|siblings|parents|children|ancestors|descendants", "person_name"?, "use_anchor"?, "use_selected"? }
- find_relationship: { "person_a": "...", "person_b": "..." }
- get_person_detail: { "person_name"?, "use_selected"? }
- get_source_text: {}
- ui_switch_tab: { "tab": "tree|source|person|diff|organize" }
- ui_focus_person: { "person_name": "..." }
- ui_set_anchor: { "person_name": "...", "use_selected"? }
- ui_open_classic: { "panel"?: "organize|source|export|search" }
- ui_open_settings: {}
- ui_open_scan: {}

写操作（须用户确认后才入库）：
- propose_person_patch: { "person_name"?, "use_selected"?, "patch": { ... } }
  可写字段: name, gender, birth_year, death_year, generation, generation_name,
  courtesy_name, art_name, county, town, village, biography
- propose_sync_person_details: {}
- propose_organize_plan: { "message": "整理意图" }
"""
    return f"""你是「族见」身具智能的家族智能体（ReSee），使命是「见家族，见自己」。

## 产品原则（Agent-first）
- 用户通过**对话**完成族谱与家族相关操作；不要只告诉用户去点按钮或手填表单。
- 界面上每个能力都应对应工具或 home_action；能执行就执行，不能执行就说明缺什么。
- 成员资料：从自然语言提取字段 → propose_person_patch → 界面自动预填 → 用户确认写入。

## 当前上下文
- 族谱: {context.family_id}
- Tab: {context.active_tab}
- 我在谱中: {anchor_name or "未设置"}
- 选中成员: {selected_name or "无"}
- 成员（节选）: {_compact_person_names(persons)}

## 行为
1. **大部分问题**（解释、建议、闲聊、问法不清）：action=reply_only，在 reply 里完整回答。
2. **需要查主谱数据**（搜人、亲属、关系、成员详情、原文）：action=call_tool。
3. **改字段/同步/整理**：call_tool 对应 propose_*，禁止假装已写入。
4. **用户用自然语言描述成员资料**（如「张三字子明第三世」「把字号改成醉翁」）：
   必须 call_tool propose_person_patch，从描述里提取字段填入 patch，禁止只文字回复让用户手填表单。
5. **切页面/定位/设身份/经典编辑/设置/扫描**：用 ui_switch_tab、ui_focus_person、ui_set_anchor、ui_open_classic、ui_open_settings、ui_open_scan，让用户看见结果。
6. 「他/她/当前成员」→ params 里 use_selected 或 use_anchor。

{tool_doc}

## 输出（仅 JSON，无 markdown）
{{ "action": "reply_only"|"call_tool", "tool": "...", "params": {{}}, "reply": "..." }}
"""


def _build_chat_messages(system: str, history: list[dict] | None, user_message: str) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = [{"role": "system", "content": system}]
    for item in (history or [])[-14:]:
        role = item.get("role")
        content = (item.get("content") or "").strip()
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": content[:2000]})
    messages.append({"role": "user", "content": user_message})
    return messages


def parse_llm_agent_decision(content: str) -> dict[str, Any] | None:
    data = extract_json_content(content)
    if isinstance(data, dict):
        action = (data.get("action") or "").strip().lower()
        if action == "reply_only" or (not data.get("tool") and data.get("reply")):
            return {"action": "reply_only", "reply": data.get("reply") or ""}
        tool = (data.get("tool") or "").strip()
        if tool:
            return {
                "action": "call_tool",
                "tool": tool,
                "params": data.get("params") or {},
                "reply": data.get("reply") or "",
            }
    stripped = _strip_llm_wrappers((content or "").strip())
    if stripped and not stripped.lstrip().startswith("{"):
        return {"action": "reply_only", "reply": stripped}
    return None


def _tool_result_to_turn(result, *, llm_reply: str = "", used_llm: bool = True) -> AgentTurnResult:
    reply = (llm_reply or result.summary or "").strip()
    meta_patch = dict(result.state_patch or {})
    turn = AgentTurnResult(
        reply=reply,
        ui_actions=result.ui_actions,
        tool_calls=result.tool_calls,
        state_patch=meta_patch,
    )
    turn.state_patch["_used_llm"] = used_llm  # type: ignore
    if result.confirmation:
        turn.state_patch["_confirmation"] = result.confirmation  # type: ignore
    return turn


async def _summarize_with_llm(
    deps: LlmAgentDeps,
    user_message: str,
    tool_name: str,
    tool_summary: str,
) -> str:
    if not deps.ai_fn:
        return tool_summary
    prompt = (
        f"用户问题：{user_message}\n\n"
        f"系统已执行工具「{tool_name}」，结果如下：\n{tool_summary}\n\n"
        "请用简洁自然的中文直接回答用户，不要重复 JSON，不要提「工具」二字。"
    )
    text, err = await deps.ai_fn(prompt)
    if text and not err:
        return text.strip()
    return tool_summary


async def run_agent_turn_llm(
    message: str,
    context: AgentContext,
    persons: list[dict],
    relations: list[dict],
    deps: LlmAgentDeps,
) -> AgentTurnResult:
    graph = GraphStore(persons, relations)
    anchor_name = selected_name = ""
    if context.anchor_person_id:
        anchor_name = (graph.get_person(context.anchor_person_id) or {}).get("name") or ""
    if context.selected_person_id:
        selected_name = (graph.get_person(context.selected_person_id) or {}).get("name") or ""

    system = build_agent_system_prompt(
        context, persons, anchor_name=anchor_name, selected_name=selected_name,
    )
    chat_messages = _build_chat_messages(system, deps.message_history, message)

    content, err = await deps.chat_fn(chat_messages)
    if err or not content:
        fallback = run_agent_turn(
            message, context, persons, relations,
            source_excerpt_fn=deps.source_excerpt_fn,
        )
        fallback.state_patch["_used_llm"] = False  # type: ignore
        fallback.state_patch["_llm_error"] = err or "empty"  # type: ignore
        return fallback

    decision = parse_llm_agent_decision(content)
    if not decision:
        return AgentTurnResult(
            reply=content.strip(),
            state_patch={"_used_llm": True},
        )

    if decision.get("action") == "reply_only":
        reply = (decision.get("reply") or content).strip()
        return AgentTurnResult(reply=reply, state_patch={"_used_llm": True})

    tool_name = decision.get("tool") or ""
    params = decision.get("params") or {}
    llm_reply = decision.get("reply") or ""
    ctx = {
        "anchor_person_id": context.anchor_person_id,
        "selected_person_id": context.selected_person_id,
        "source_text": deps.source_text,
    }

    if tool_name in READ_TOOLS:
        result = execute_read_tool(
            tool_name, params, graph=graph, persons=persons, context=ctx,
            source_excerpt_fn=deps.source_excerpt_fn, source_text=deps.source_text,
        )
        if result.success and not llm_reply:
            llm_reply = await _summarize_with_llm(deps, message, tool_name, result.summary)
        return _tool_result_to_turn(result, llm_reply=llm_reply)

    if tool_name in WRITE_TOOLS:
        if tool_name == "propose_organize_plan":
            if not deps.ai_fn:
                return AgentTurnResult(reply="整理需要配置 AI 模型。", state_patch={"_used_llm": True})
            result = await propose_organize_tool(
                params, cursor=deps.cursor, family_id=deps.family_id,
                persons=persons, relations=relations, source_text=deps.source_text,
                ai_fn=deps.ai_fn, ai_configured=deps.ai_configured,
                history=deps.message_history,
            )
        else:
            if not deps.cursor or not deps.family_id:
                return AgentTurnResult(reply="写操作需要数据库上下文。", state_patch={"_used_llm": True})
            result = propose_write_tool(
                tool_name, params, cursor=deps.cursor, family_id=deps.family_id,
                graph=graph, persons=persons, context=ctx,
            )
        if not result.success:
            return AgentTurnResult(
                reply=result.summary, tool_calls=result.tool_calls, state_patch={"_used_llm": True},
            )
        return _tool_result_to_turn(result, llm_reply=llm_reply)

    # 未知工具：把模型原文当回复，仍算 LLM 回合
    return AgentTurnResult(
        reply=llm_reply or content.strip(),
        state_patch={"_used_llm": True},
    )


async def run_agent_turn_hybrid(
    message: str,
    context: AgentContext,
    persons: list[dict],
    relations: list[dict],
    *,
    use_llm: bool,
    deps: LlmAgentDeps | None = None,
    source_excerpt_fn=None,
) -> AgentTurnResult:
    if deps and deps.cursor and deps.family_id:
        auto = try_auto_person_patch_turn(
            message,
            context,
            persons,
            relations,
            cursor=deps.cursor,
            family_id=deps.family_id,
        )
        if auto:
            return auto

    if use_llm and deps and deps.ai_configured:
        return await run_agent_turn_llm(message, context, persons, relations, deps)
    turn = run_agent_turn(
        message, context, persons, relations,
        source_excerpt_fn=source_excerpt_fn or (deps.source_excerpt_fn if deps else None),
    )
    turn.state_patch["_used_llm"] = False  # type: ignore
    return turn
