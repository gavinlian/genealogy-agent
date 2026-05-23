"""MiniMax chatcompletion_v2 客户端（与族见小程序 ai_service 一致）"""

from __future__ import annotations

import httpx

DEFAULT_CHAT_ENDPOINT = "https://api.minimax.chat/v1/text/chatcompletion_v2"
VLM_ENDPOINT = "https://api.minimaxi.com/v1/coding_plan/vlm"


def minimax_headers(api_key: str, group_id: str) -> dict[str, str]:
    """GroupId 走请求头（与已验证的 cloudfunctions 一致）"""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    if group_id:
        headers["GroupId"] = group_id
    return headers


def build_text_messages(prompt: str, system: str | None = None) -> list:
    messages = []
    if system:
        messages.append({"role": "system", "name": "system", "content": system})
    messages.append({"role": "user", "name": "user", "content": prompt})
    return messages


def build_vision_messages(prompt: str, image_base64: str) -> list:
    return [{
        "role": "user",
        "name": "user",
        "content": [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"}},
        ],
    }]


def extract_minimax_content(result: dict) -> str:
    """解析 chatcompletion_v2 / VLM 响应"""
    base = result.get("base_resp") or {}
    code = base.get("status_code")
    if code is not None and code != 0:
        return ""

    choices = result.get("choices") or []
    if choices:
        choice = choices[0]
        msg = choice.get("message") or {}
        content = (msg.get("content") or "").strip()
        reasoning = (msg.get("reasoning_content") or "").strip()
        combined = "\n".join(part for part in (content, reasoning) if part)
        if combined:
            return combined
        nested = choice.get("messages") or []
        if nested and nested[0].get("content"):
            return str(nested[0]["content"]).strip()

    for key in ("reply", "output_text", "content"):
        val = result.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
        if isinstance(val, list) and val and isinstance(val[0], dict):
            return str(val[0].get("text", "")).strip()

    return ""


def extract_minimax_error(result: dict) -> str:
    base = result.get("base_resp") or {}
    code = base.get("status_code")
    if code is not None and code != 0:
        return base.get("status_msg") or f"MiniMax 错误码 {code}"
    err = result.get("error")
    if isinstance(err, dict) and err.get("message"):
        return err["message"]
    return ""


async def call_minimax_chat(
    api_key: str,
    group_id: str,
    model: str,
    messages: list,
    *,
    endpoint: str = DEFAULT_CHAT_ENDPOINT,
    max_tokens: int = 1024,
    temperature: float = 0.3,
) -> tuple[str, str]:
    if not api_key:
        return "", "未配置 MiniMax API Key"
    if not group_id:
        return "", "未配置 MiniMax Group ID（控制台基础信息 → Group ID，填在设置里）"

    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }

    try:
        async with httpx.AsyncClient(timeout=90.0) as client:
            resp = await client.post(
                endpoint,
                headers=minimax_headers(api_key, group_id),
                json=payload,
            )
            raw = resp.text[:500] if resp.text else ""
            if resp.status_code != 200:
                return "", f"MiniMax HTTP {resp.status_code}: {raw}"

            data = resp.json()
            err = extract_minimax_error(data)
            if err:
                return "", f"MiniMax API: {err}"

            text = extract_minimax_content(data)
            if text:
                return text, ""
            return "", f"MiniMax 返回为空，原始响应: {raw}"
    except httpx.TimeoutException:
        return "", "MiniMax 请求超时"
    except Exception as e:
        return "", f"MiniMax 异常: {e}"


async def call_minimax_vlm(
    api_key: str,
    group_id: str,
    prompt: str,
    image_base64: str,
    *,
    max_tokens: int = 256,
) -> tuple[str, str]:
    """族谱 OCR：优先 VLM 接口（与 scanocr 云函数一致）"""
    if not api_key:
        return "", "未配置 MiniMax API Key"
    if not group_id:
        return "", "未配置 MiniMax Group ID"

    payload = {
        "prompt": prompt,
        "image_url": f"data:image/jpeg;base64,{image_base64}",
        "max_tokens": max_tokens,
    }

    try:
        async with httpx.AsyncClient(timeout=90.0) as client:
            resp = await client.post(
                VLM_ENDPOINT,
                headers=minimax_headers(api_key, group_id),
                json=payload,
            )
            raw = resp.text[:500] if resp.text else ""
            if resp.status_code != 200:
                return "", f"MiniMax VLM HTTP {resp.status_code}: {raw}"

            data = resp.json()
            err = extract_minimax_error(data)
            if err:
                return "", f"MiniMax VLM: {err}"

            text = extract_minimax_content(data)
            if text:
                return text, ""
            return "", f"MiniMax VLM 返回为空: {raw}"
    except httpx.TimeoutException:
        return "", "MiniMax VLM 请求超时"
    except Exception as e:
        return "", f"MiniMax VLM 异常: {e}"
