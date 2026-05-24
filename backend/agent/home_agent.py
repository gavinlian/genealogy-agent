"""首页（未选族谱）Agent — 全局 LLM 对话。"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from agent.home_intent import (
    build_create_family_action,
    extract_family_create_from_text,
    finalize_create_fields,
    looks_like_create_family,
)
from agent.parser import extract_json_content

ChatFn = Callable[[list[dict[str, str]]], Awaitable[tuple[str, str]]]


@dataclass
class HomeAgentTurn:
    reply: str
    home_actions: list[dict[str, Any]] = field(default_factory=list)
    used_llm: bool = False
    llm_error: str | None = None


def _build_home_system(families: list[dict]) -> str:
    lines = []
    for f in families[:30]:
        name = f.get("name") or "未命名"
        cnt = f.get("person_count") or 0
        lines.append(f"- id={f.get('id')} name={name} members={cnt}")
    fam_block = "\n".join(lines) if lines else "（尚无族谱）"
    return f"""你是「族见」身具智能的家族智能体（ReSee），使命是「见家族，见自己」。

## 产品原则
用户通过对话操作族谱与家族相关功能（打开/创建族谱、扫描建谱等），不要只让用户去点界面按钮。

## 可用族谱
{fam_block}

## 首页动作（action=home_action 时）
- open_family: 打开族谱，params {{ "family_id": "..." }} 或 {{ "family_name": "..." }}
- scan: 打开扫描/OCR 建谱
- create_family: 新建族谱。若用户已给出名称等信息，必须在 params 里带上：
  {{ "name": "族谱名称", "surname": "姓氏可选", "description": "简介可选" }}
  系统会自动创建并打开，不要只让用户手填表单。

## 规则
1. 一般问答、介绍功能、闲聊 → action=reply_only，在 reply 里完整回答。
2. 用户明确要打开某本谱 → home_action + open_family。
3. 扫描/拍照/建谱 → home_action scan。
4. 用户要**创建/新建族谱**且提供了名称 → home_action create_family + 完整 params，reply 说明将自动创建。
5. 只输出一个 JSON 对象。

## 输出格式
{{
  "action": "reply_only" | "home_action",
  "reply": "给用户的中文回复",
  "home_action": "open_family|scan|create_family",
  "params": {{ }}
}}
"""


def _parse_home_decision(content: str) -> dict[str, Any] | None:
    data = extract_json_content(content)
    if isinstance(data, dict):
        action = (data.get("action") or "").strip().lower()
        if action == "home_action":
            return {
                "action": "home_action",
                "reply": data.get("reply") or "",
                "home_action": (data.get("home_action") or "").strip(),
                "params": data.get("params") or {},
            }
        if action == "reply_only" or data.get("reply"):
            return {"action": "reply_only", "reply": data.get("reply") or ""}
    stripped = (content or "").strip()
    if stripped and not stripped.startswith("{"):
        return {"action": "reply_only", "reply": stripped}
    return None


def _resolve_family_id(families: list[dict], params: dict) -> str | None:
    fid = (params.get("family_id") or "").strip()
    if fid:
        return fid
    name = (params.get("family_name") or params.get("name") or "").strip()
    if not name:
        return None
    for f in families:
        if (f.get("name") or "") == name or name in (f.get("name") or ""):
            return f.get("id")
    return None


async def run_home_agent_turn(
    message: str,
    families: list[dict],
    *,
    chat_fn: ChatFn,
    history: list[dict] | None = None,
) -> HomeAgentTurn:
    msg = (message or "").strip()
    create_action = build_create_family_action(msg)
    if create_action:
        name = create_action.get("name", "")
        parts = [f"名称「{name}」"]
        if create_action.get("surname"):
            parts.append(f"姓氏「{create_action['surname']}」")
        if create_action.get("description"):
            parts.append("已带上简介")
        return HomeAgentTurn(
            reply=f"好的，正在为您创建族谱（{'，'.join(parts)}），创建完成后会自动打开。",
            home_actions=[create_action],
            used_llm=False,
        )

    system = _build_home_system(families)
    messages: list[dict[str, str]] = [{"role": "system", "content": system}]
    for item in (history or [])[-12:]:
        role = item.get("role")
        content = (item.get("content") or "").strip()
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": content[:2000]})
    messages.append({"role": "user", "content": message})

    content, err = await chat_fn(messages)
    if err or not content:
        create_action = build_create_family_action(msg)
        if create_action:
            return HomeAgentTurn(
                reply=f"正在创建「{create_action['name']}」…（模型暂不可用，使用规则创建）",
                home_actions=[create_action],
                used_llm=False,
                llm_error=err or "empty",
            )
        return HomeAgentTurn(
            reply=_rule_home_fallback(message, families),
            used_llm=False,
            llm_error=err or "empty",
        )

    decision = _parse_home_decision(content)
    if not decision:
        return HomeAgentTurn(reply=content.strip(), used_llm=True)

    if decision.get("action") == "reply_only":
        # LLM 只文字回复时，若规则能提取建谱信息则仍自动创建
        create_action = build_create_family_action(msg)
        if create_action:
            name = create_action.get("name", "")
            return HomeAgentTurn(
                reply=f"好的，正在为您创建「{name}」并打开…",
                home_actions=[create_action],
                used_llm=True,
            )
        return HomeAgentTurn(reply=(decision.get("reply") or content).strip(), used_llm=True)

    action_type = decision.get("home_action") or ""
    params = decision.get("params") or {}
    reply = (decision.get("reply") or "").strip()
    home_actions: list[dict] = []

    if action_type == "open_family":
        fid = _resolve_family_id(families, params)
        if fid:
            home_actions.append({"type": "select_family", "family_id": fid})
            if not reply:
                fname = next((f.get("name") for f in families if f.get("id") == fid), "")
                reply = f"正在打开「{fname}」…"
        elif not reply:
            reply = "未找到匹配的族谱，请在上方面板点选，或告诉我完整族谱名。"
    elif action_type == "scan":
        home_actions.append({"type": "scan"})
        if not reply:
            reply = "好的，正在打开扫描建谱…"
    elif action_type == "create_family":
        extracted = finalize_create_fields({**extract_family_create_from_text(msg), **(params or {})})
        name = (extracted.get("name") or "").strip()
        payload: dict[str, Any] = {"type": "create_family"}
        if name:
            payload["name"] = name
            if extracted.get("surname"):
                payload["surname"] = extracted["surname"]
            if extracted.get("description"):
                payload["description"] = extracted["description"]
            payload["auto_create"] = True
            if not reply:
                reply = f"好的，正在创建「{name}」并为您打开…"
        else:
            # 信息不全：预填已有字段，交给前端弹窗
            for key in ("name", "surname", "description"):
                if extracted.get(key):
                    payload[key] = extracted[key]
            if not reply:
                reply = "请补充族谱名称，或告诉我姓氏（如「姓张」），我可以帮您建好。"
        home_actions.append(payload)

    if not reply:
        reply = content.strip()
    return HomeAgentTurn(reply=reply, home_actions=home_actions, used_llm=True)


def _rule_home_fallback(message: str, families: list[dict]) -> str:
    text = message or ""
    if looks_like_create_family(text):
        fields = extract_family_create_from_text(text)
        if fields.get("name"):
            return f"正在创建「{fields['name']}」（规则模式，未连接模型）。"
    if re.search(r"扫描|ocr|拍照|图片建谱", text, re.I):
        return "好的，正在打开扫描建谱…（未连接模型，使用离线提示）"
    for f in families:
        name = f.get("name") or ""
        if name and name in text:
            return f"请点选上方「{name}」打开（未连接模型）。"
    return (
        "我是族见家族智能体（身具智能，ReSee）。请在设置中配置解析模型 API Key 以获得完整对话能力；"
        "或在上方面板选择族谱、说「扫描建谱」。"
    )
