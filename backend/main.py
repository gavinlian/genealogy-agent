from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
import sqlite3
import uuid
import os
import json
import base64
import httpx

from agent.engine import get_agent_status
from agent.minimax_client import (
    DEFAULT_CHAT_ENDPOINT,
    build_text_messages,
    build_vision_messages,
    call_minimax_chat,
    call_minimax_vlm,
)
from agent.pipeline import run_scan_pipeline, PARSE_PROMPT_TEMPLATE
from agent.genealogy_prompts import OCR_PROMPT, build_legacy_parse_prompt
from agent.two_stage_parse import run_two_stage_genealogy_parse
from agent.genealogy_builder import auto_build_genealogy
from agent.genealogy_organizer import (
    organize_genealogy_with_chat,
    _normalize_plan,
    compute_organize_diff,
    merge_plan_into_genealogy,
    should_use_clean_slate,
    reconcile_plan_with_genealogy,
    build_genealogy_name_index,
    resolve_genealogy_name,
)
from ai_organize_store import (
    clear_ai_chat_messages,
    ensure_ai_chat_table,
    get_ai_chat_state,
    save_ai_chat_state,
)
from agent.organize_session import (
    clear_family_organize_sessions,
    clear_organize_session,
    create_organize_session,
    get_organize_session,
    resolve_context_mode,
    touch_organize_session,
)
from agent.source_diff import compare_genealogy_with_source, compare_parsed_with_genealogy
from genealogy_clear import clear_family_genealogy
from agent.parser import parse_genealogy_text, extract_json_content
from agent.validators import validate_genealogy_persons, validate_relations, validate_genealogy_with_generations
from agent.tree import build_family_tree
from agent.generation_engine import recalculate_generations, add_person_with_kinship, kinship_generation_delta
from agent.search import search_persons
from agent.nl_search import nl_search_with_ai, rule_based_nl_search
from agent.pdf_export import generate_genealogy_html
from agent.review import annotate_persons_for_review
from agent.person_editor import (
    apply_person_relations,
    create_relation_record,
    get_spouse_id,
)
from db_schema import migrate_schema, row_to_person
from source_versions import (
    confirm_source_version,
    create_source_version,
    ensure_versions_table,
    get_source_version,
    list_source_versions,
    migrate_legacy_family_source,
    get_active_source_for_family,
    set_active_source_version,
    delete_source_version,
    update_source_version,
    upsert_text_edition_from_source,
)
from agent.relation_text import build_local_relation_description
from agent.name_extractor import normalize_person_name

app = FastAPI(title="族见 - 数字族谱API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DB_PATH = os.path.join(os.path.dirname(__file__), "genealogy.db")
UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

# AI Provider 预设
AI_PROVIDERS = {
    "minimax": {
        "name": "MiniMax",
        "label": "MiniMax",
        "api_base": "https://api.minimax.chat",
        "chat_endpoint": "https://api.minimax.chat/v1/text/chatcompletion_v2",
        "vision_model": "MiniMax-M2.7",
        "text_model": "MiniMax-M2.7",
        "vision_models": ["MiniMax-M2.7", "MiniMax-Text-01", "MiniMax-Image-01"],
        "text_models": ["MiniMax-M2.7", "abab6.5s-chat", "MiniMax-Text-01"],
        "is_free": False,
        "supports_vision": True,
        "requires_group_id": True,
    },
    "siliconflow": {
        "name": "SiliconFlow",
        "label": "硅基流动",
        "api_base": "https://api.siliconflow.cn/v1",
        "vision_model": "Qwen/Qwen2-VL-72B-Instruct",
        "text_model": "Qwen/Qwen2.5-72B-Instruct",
        "vision_models": ["Qwen/Qwen2-VL-72B-Instruct", "deepseek-ai/DeepSeek-V3"],
        "text_models": ["Qwen/Qwen2.5-72B-Instruct", "deepseek-ai/DeepSeek-V3", "Qwen/Qwen2-VL-72B-Instruct"],
        "is_free": True,
        "supports_vision": True,
    },
    "qwen": {
        "name": "Qwen",
        "label": "通义千问",
        "api_base": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "vision_model": "qwen-vl-plus",
        "text_model": "qwen-plus",
        "vision_models": ["qwen-vl-plus", "qwen-vl-max"],
        "text_models": ["qwen-plus", "qwen-turbo", "qwen-max"],
        "is_free": False,
        "supports_vision": True,
    },
    "openai": {
        "name": "OpenAI",
        "label": "OpenAI",
        "api_base": "https://api.openai.com/v1",
        "vision_model": "gpt-4o",
        "text_model": "gpt-4o",
        "vision_models": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo"],
        "text_models": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo"],
        "is_free": False,
        "supports_vision": True,
    },
    "deepseek": {
        "name": "DeepSeek",
        "label": "DeepSeek",
        "api_base": "https://api.deepseek.com/v1",
        "vision_model": "",
        "text_model": "deepseek-chat",
        "vision_models": [],
        "text_models": ["deepseek-chat", "deepseek-coder"],
        "is_free": True,
        "supports_vision": False,
    },
    "zhipu": {
        "name": "GLM",
        "label": "智谱 GLM",
        "api_base": "https://open.bigmodel.cn/api/paas/v4",
        "vision_model": "glm-4v-9b",
        "text_model": "glm-4-plus",
        "vision_models": ["glm-4v-9b", "glm-4v-plus"],
        "text_models": ["glm-4-plus", "glm-4-flash"],
        "is_free": False,
        "supports_vision": True,
    },
    "custom": {
        "name": "Custom",
        "label": "自定义",
        "api_base": "",
        "vision_model": "",
        "text_model": "",
        "vision_models": [],
        "text_models": [],
        "is_free": False,
        "supports_vision": True,
    },
}

DEFAULT_OCR = {"provider": "minimax", "model": "MiniMax-M2.7"}
DEFAULT_PARSE = {"provider": "minimax", "model": "MiniMax-M2.7"}


def get_provider_config(provider_name: str) -> dict:
    return AI_PROVIDERS.get(provider_name, AI_PROVIDERS["minimax"])


def _minimax_group_id_from_env() -> str:
    return (os.environ.get("MINIMAX_GROUP_ID") or "").strip()


def _minimax_endpoint(api_base: str | None) -> str:
    preset = get_provider_config("minimax")
    if api_base and "chatcompletion" in api_base:
        return api_base.strip()
    if api_base:
        return f"{api_base.rstrip('/')}/v1/text/chatcompletion_v2"
    return preset.get("chat_endpoint", DEFAULT_CHAT_ENDPOINT)


def resolve_credentials(
    provider_id: str,
    *,
    api_key_override: str | None = None,
    api_base_override: str | None = None,
    group_id_override: str | None = None,
) -> tuple[str, str, str]:
    """返回 (api_key, api_base, group_id)，测试时可传入覆盖值"""
    preset = get_provider_config(provider_id)
    api_key, api_base, group_id = get_provider_credentials(provider_id)

    if api_key_override and api_key_override.strip():
        api_key = api_key_override.strip()
    if api_base_override and api_base_override.strip():
        api_base = api_base_override.strip()
    if group_id_override is not None and str(group_id_override).strip():
        group_id = str(group_id_override).strip()

    if provider_id == "minimax" and not group_id:
        group_id = _minimax_group_id_from_env()
    if provider_id == "custom" and api_base_override:
        api_base = api_base_override.strip()
    elif not api_base:
        api_base = preset.get("api_base", "")
    return api_key, api_base, group_id


def get_provider_credentials(provider_id: str) -> tuple[str, str, str]:
    conn = get_db()
    c = conn.cursor()
    row = c.execute(
        "SELECT api_key, api_base, group_id FROM ai_provider_keys WHERE provider = ?",
        (provider_id,),
    ).fetchone()
    if not row or not row["api_key"]:
        old = c.execute(
            "SELECT api_key, api_base FROM ai_config WHERE id = 'default' AND provider = ?",
            (provider_id,),
        ).fetchone()
        if old and old["api_key"]:
            row = {"api_key": old["api_key"], "api_base": old["api_base"], "group_id": ""}
    conn.close()

    preset = get_provider_config(provider_id)
    api_key = row["api_key"] if row and row["api_key"] else ""
    api_base = row["api_base"] if row and row["api_base"] else preset.get("api_base", "")
    group_id = ""
    if row:
        try:
            group_id = (row["group_id"] or "").strip()
        except (KeyError, IndexError):
            group_id = ""
    if provider_id == "minimax" and not group_id:
        group_id = _minimax_group_id_from_env()
    if provider_id == "custom" and row and row["api_base"]:
        api_base = row["api_base"]
    return api_key, api_base, group_id


def load_model_selection() -> dict:
    conn = get_db()
    c = conn.cursor()
    row = c.execute("SELECT ocr_provider, ocr_model, parse_provider, parse_model FROM ai_settings WHERE id = 'default'").fetchone()
    conn.close()
    if row:
        return {
            "ocr": {"provider": row["ocr_provider"], "model": row["ocr_model"]},
            "parse": {"provider": row["parse_provider"], "model": row["parse_model"]},
        }
    return {"ocr": dict(DEFAULT_OCR), "parse": dict(DEFAULT_PARSE)}


def resolve_task_model(data: dict, task: str) -> tuple[str, str]:
    """优先使用请求里传的模型，否则读数据库配置"""
    saved = load_model_selection()[task]
    incoming = data.get(task) or {}
    provider = incoming.get("provider") or saved["provider"]
    model = incoming.get("model") or saved["model"]
    return provider, model

def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS families (
        id TEXT PRIMARY KEY, name TEXT NOT NULL, surname TEXT, description TEXT,
        root_person_id TEXT, created_at TEXT, updated_at TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS persons (
        id TEXT PRIMARY KEY, family_id TEXT NOT NULL, name TEXT NOT NULL,
        gender TEXT DEFAULT 'unknown', birth_year INTEGER, death_year INTEGER,
        generation INTEGER, generation_name TEXT, generation_prefix TEXT,
        parent_id TEXT, spouse_ids TEXT, status TEXT DEFAULT 'confirmed', created_at TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS relations (
        id TEXT PRIMARY KEY, family_id TEXT NOT NULL, from_person_id TEXT NOT NULL,
        to_person_id TEXT NOT NULL, relation_type TEXT NOT NULL,
        status TEXT DEFAULT 'confirmed', created_at TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS ocr_records (
        id TEXT PRIMARY KEY, family_id TEXT, image_path TEXT, raw_text TEXT,
        parsed_text TEXT, status TEXT DEFAULT 'pending', created_at TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS ai_provider_keys (
        provider TEXT PRIMARY KEY, api_key TEXT, api_base TEXT, group_id TEXT, updated_at TEXT)""")
    migrate_schema(c)
    ensure_versions_table(c)
    ensure_ai_chat_table(c)
    c.execute("""CREATE TABLE IF NOT EXISTS ai_settings (
        id TEXT PRIMARY KEY, ocr_provider TEXT, ocr_model TEXT,
        parse_provider TEXT, parse_model TEXT, updated_at TEXT)""")
    # 兼容旧表
    c.execute("""CREATE TABLE IF NOT EXISTS ai_config (
        id TEXT PRIMARY KEY, provider TEXT, api_key TEXT, model TEXT,
        api_base TEXT, vision_model TEXT, updated_at TEXT)""")

    # 迁移旧配置
    old = c.execute("SELECT * FROM ai_config WHERE id = 'default'").fetchone()
    settings = c.execute("SELECT id FROM ai_settings WHERE id = 'default'").fetchone()
    if old and not settings:
        now = datetime.now().isoformat()
        provider = old["provider"] or "minimax"
        c.execute(
            """INSERT OR IGNORE INTO ai_provider_keys (provider, api_key, api_base, updated_at)
               VALUES (?, ?, ?, ?)""",
            (provider, old["api_key"], old["api_base"], now),
        )
        c.execute(
            """INSERT INTO ai_settings (id, ocr_provider, ocr_model, parse_provider, parse_model, updated_at)
               VALUES ('default', ?, ?, ?, ?, ?)""",
            (
                provider,
                old["vision_model"] or DEFAULT_OCR["model"],
                provider,
                old["model"] or DEFAULT_PARSE["model"],
                now,
            ),
        )
    elif not settings:
        now = datetime.now().isoformat()
        c.execute(
            """INSERT INTO ai_settings (id, ocr_provider, ocr_model, parse_provider, parse_model, updated_at)
               VALUES ('default', ?, ?, ?, ?, ?)""",
            (
                DEFAULT_OCR["provider"],
                DEFAULT_OCR["model"],
                DEFAULT_PARSE["provider"],
                DEFAULT_PARSE["model"],
                now,
            ),
        )
    conn.commit()
    conn.close()

init_db()

def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=10000")
    return conn

# ==================== AI 配置 API ====================

@app.get("/api/ai/providers")
async def get_ai_providers():
    """获取所有 AI Provider 列表（MiniMax 优先）"""
    order = ["minimax", "siliconflow", "qwen", "openai", "deepseek", "zhipu", "custom"]
    providers = []
    for key in order:
        if key not in AI_PROVIDERS:
            continue
        val = AI_PROVIDERS[key]
        providers.append({
            "id": key,
            "name": val["name"],
            "label": val.get("label", val["name"]),
            "vision_model": val["vision_model"],
            "text_model": val["text_model"],
            "vision_models": val.get("vision_models", [val["vision_model"]] if val.get("vision_model") else []),
            "text_models": val.get("text_models", [val["text_model"]] if val.get("text_model") else []),
            "is_free": val["is_free"],
            "supports_vision": val["supports_vision"],
        })
    return providers


@app.get("/api/ai/config")
async def get_ai_config():
    conn = get_db()
    c = conn.cursor()
    key_rows = c.execute("SELECT provider, api_key, api_base, group_id FROM ai_provider_keys").fetchall()
    conn.close()

    keys = {}
    for pid in AI_PROVIDERS:
        preset = get_provider_config(pid)
        row = next((r for r in key_rows if r["provider"] == pid), None)
        base = preset.get("api_base", "")
        if pid == "custom" and row and row["api_base"]:
            base = row["api_base"]
        gid = ""
        if row:
            try:
                gid = row["group_id"] or ""
            except (KeyError, IndexError):
                gid = ""
        if pid == "minimax" and not gid:
            gid = _minimax_group_id_from_env()
        configured = bool(row and row["api_key"])
        if pid == "minimax":
            configured = configured and bool(gid)
        keys[pid] = {
            "configured": configured,
            "api_base": base,
            "group_id": gid,
            "has_group_id": bool(gid),
        }

    selection = load_model_selection()
    return {"keys": keys, **selection}


@app.post("/api/ai/config")
async def save_ai_config(data: dict):
    conn = get_db()
    c = conn.cursor()
    now = datetime.now().isoformat()

    keys = data.get("keys") or {}
    for provider_id, key_data in keys.items():
        if provider_id not in AI_PROVIDERS:
            continue
        api_key = (key_data or {}).get("api_key", "")
        api_base = (key_data or {}).get("api_base")
        group_id = (key_data or {}).get("group_id")
        existing = c.execute(
            "SELECT api_key, api_base, group_id FROM ai_provider_keys WHERE provider = ?",
            (provider_id,),
        ).fetchone()
        preset = get_provider_config(provider_id)
        final_key = api_key or (existing["api_key"] if existing else "")
        final_base = api_base if api_base is not None else (
            existing["api_base"] if existing and existing["api_base"] else preset.get("api_base", "")
        )
        final_group = group_id if group_id is not None else (
            existing["group_id"] if existing else ""
        )
        if final_key or final_group or api_base is not None:
            c.execute(
                """INSERT OR REPLACE INTO ai_provider_keys
                   (provider, api_key, api_base, group_id, updated_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (provider_id, final_key, final_base, final_group or "", now),
            )

    ocr = data.get("ocr") or DEFAULT_OCR
    parse_cfg = data.get("parse") or DEFAULT_PARSE
    c.execute(
        """INSERT OR REPLACE INTO ai_settings
           (id, ocr_provider, ocr_model, parse_provider, parse_model, updated_at)
           VALUES ('default', ?, ?, ?, ?, ?)""",
        (
            ocr.get("provider", DEFAULT_OCR["provider"]),
            ocr.get("model", DEFAULT_OCR["model"]),
            parse_cfg.get("provider", DEFAULT_PARSE["provider"]),
            parse_cfg.get("model", DEFAULT_PARSE["model"]),
            now,
        ),
    )
    conn.commit()
    conn.close()
    return {"success": True}


# 1x1 测试图（JPEG），用于 OCR 连通性检测
TEST_OCR_IMAGE_B64 = (
    "/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAP//////////////////////////////////////////////////////////////////////////////////////"
    "2wBDAf//////////////////////////////////////////////////////////////////////////////////////wAARCAABAAEDASIAAhEBAxEB/8QAFQABAQAAAAAAAAAAAAAAAAAAAAb/xAAUEAEAAAAAAAAAAAAAAAAAAAAA/8QAFQEBAQAAAAAAAAAAAAAAAAAAAAX/xAAUEQEAAAAAAAAAAAAAAAAAAAAA/9oADAMBAAIRAxEAPwCwAA8A/9k="
)


@app.post("/api/ai/test")
async def test_ai_connection(data: dict):
    """
    测试模型 / API Key 是否可用。
    task: key（当前 Provider Key）| ocr | parse
    可在保存前传入 api_key 做即时测试。
    """
    import time

    task = data.get("task", "key")
    provider_id = data.get("provider", "minimax")
    model = data.get("model", "")
    api_key_override = (data.get("api_key") or "").strip() or None
    api_base_override = (data.get("api_base") or "").strip() or None
    group_id_override = data.get("group_id")
    if group_id_override is not None:
        group_id_override = str(group_id_override).strip() or None

    preset = get_provider_config(provider_id)
    if not model:
        if task == "ocr":
            model = preset.get("vision_model") or DEFAULT_OCR["model"]
        else:
            model = preset.get("text_model") or DEFAULT_PARSE["model"]

    started = time.perf_counter()

    if task == "key":
        prompt = "请只回复：OK"
        max_tokens = 64 if provider_id == "minimax" else 256
        if provider_id == "minimax":
            api_key, _, group_id = resolve_credentials(
                provider_id,
                api_key_override=api_key_override,
                group_id_override=group_id_override,
            )
            if not api_key:
                return {"success": False, "task": task, "provider": provider_id, "model": model,
                        "message": "未配置 API Key", "latency_ms": 0}
            if not group_id:
                return {"success": False, "task": task, "provider": provider_id, "model": model,
                        "message": "未配置 Group ID", "latency_ms": 0}
            content, err = await call_minimax_chat(
                api_key, group_id, model or "MiniMax-M2.7",
                build_text_messages(prompt),
                max_tokens=max_tokens,
            )
        else:
            content, err = await call_text_model(
                provider_id,
                model,
                prompt,
                api_key_override=api_key_override,
                api_base_override=api_base_override,
                group_id_override=group_id_override,
            )
    elif task == "ocr":
        if not preset.get("supports_vision") and provider_id != "custom":
            return {
                "success": False,
                "task": task,
                "provider": provider_id,
                "model": model,
                "message": f"{preset.get('label', provider_id)} 不支持图片识别，请换其他 Provider",
                "latency_ms": 0,
            }
        prompt = "这是一张连通性测试图。请只回复：测试成功"
        content, err = await call_vision_model(
            provider_id,
            model,
            TEST_OCR_IMAGE_B64,
            prompt,
            api_key_override=api_key_override,
            api_base_override=api_base_override,
            group_id_override=group_id_override,
        )
    elif task == "parse":
        prompt = (
            '从以下文字提取 JSON：{"persons":[{"name":"测试","gender":"male","birth_year":null,"death_year":null,"generation":1,"generation_name":""}],"relations":[]}\n'
            "文字：测试氏，第一代，测试。"
        )
        content, err = await call_text_model(
            provider_id,
            model,
            prompt,
            api_key_override=api_key_override,
            api_base_override=api_base_override,
            group_id_override=group_id_override,
        )
    else:
        raise HTTPException(status_code=400, detail=f"未知测试类型: {task}")

    latency_ms = int((time.perf_counter() - started) * 1000)
    preview = (content or "")[:120]

    if err:
        return {
            "success": False,
            "task": task,
            "provider": provider_id,
            "model": model,
            "message": err,
            "latency_ms": latency_ms,
        }

    return {
        "success": True,
        "task": task,
        "provider": provider_id,
        "model": model,
        "message": "连接成功，模型有回应",
        "reply_preview": preview,
        "latency_ms": latency_ms,
    }


async def call_minimax_vision(
    api_key: str,
    group_id: str,
    model: str,
    image_base64: str,
    prompt: str,
    *,
    endpoint: str | None = None,
) -> tuple[str, str]:
    """MiniMax OCR：先 VLM，再 chatcompletion_v2 多模态"""
    text, err = await call_minimax_vlm(api_key, group_id, prompt, image_base64)
    if text:
        return text, ""

    messages = build_vision_messages(prompt, image_base64)
    text2, err2 = await call_minimax_chat(
        api_key,
        group_id,
        model,
        messages,
        endpoint=endpoint or _minimax_endpoint(None),
    )
    if text2:
        return text2, ""
    return "", err2 or err or "MiniMax OCR 失败"


async def call_vision_model(
    provider_id: str,
    model: str,
    image_base64: str,
    prompt: str,
    *,
    api_key_override: str | None = None,
    api_base_override: str | None = None,
    group_id_override: str | None = None,
) -> tuple[str, str]:
    """返回 (识别文本, 错误信息)"""
    api_key, api_base, group_id = resolve_credentials(
        provider_id,
        api_key_override=api_key_override,
        api_base_override=api_base_override,
        group_id_override=group_id_override,
    )
    if not api_key:
        return "", "未配置 API Key，请在设置中填写并保存"

    if provider_id == "minimax":
        return await call_minimax_vision(
            api_key,
            group_id,
            model,
            image_base64,
            prompt,
            endpoint=_minimax_endpoint(api_base),
        )

    if not api_base:
        return "", f"{provider_id} 不支持图片识别"

    payload = {
        "model": model,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"}},
                {"type": "text", "text": prompt},
            ],
        }],
    }
    try:
        async with httpx.AsyncClient(timeout=90.0) as client:
            resp = await client.post(
                f"{api_base.rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json=payload,
            )
            if resp.status_code == 200:
                result = resp.json()
                text = result.get("choices", [{}])[0].get("message", {}).get("content", "")
                if text:
                    return text.strip(), ""
                return "", "模型返回为空"
            err = resp.text[:200] if resp.text else f"HTTP {resp.status_code}"
            return "", f"OCR 调用失败: {err}"
    except httpx.TimeoutException:
        return "", "OCR 请求超时，请换更小图片或检查网络"
    except Exception as e:
        return "", f"OCR 异常: {str(e)}"


async def call_text_model(
    provider_id: str,
    model: str,
    prompt: str,
    *,
    api_key_override: str | None = None,
    api_base_override: str | None = None,
    group_id_override: str | None = None,
    max_tokens: int = 2048,
) -> tuple[str, str]:
    """返回 (内容, 错误信息)"""
    api_key, api_base, group_id = resolve_credentials(
        provider_id,
        api_key_override=api_key_override,
        api_base_override=api_base_override,
        group_id_override=group_id_override,
    )
    if not api_key:
        return "", "未配置 API Key"

    if provider_id == "minimax":
        messages = build_text_messages(prompt)
        return await call_minimax_chat(
            api_key,
            group_id,
            model,
            messages,
            endpoint=_minimax_endpoint(api_base),
            max_tokens=max_tokens,
        )

    if not api_base:
        return "", "未配置 API 地址"

    try:
        async with httpx.AsyncClient(timeout=45.0) as client:
            resp = await client.post(
                f"{api_base.rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": max_tokens,
                },
            )
            if resp.status_code == 200:
                result = resp.json()
                text = result.get("choices", [{}])[0].get("message", {}).get("content", "")
                if text:
                    return text, ""
                return "", "模型返回为空"
            return "", f"解析失败 HTTP {resp.status_code}"
    except httpx.TimeoutException:
        return "", "解析请求超时"
    except Exception as e:
        return "", str(e)

# ==================== 族谱 API ====================

def _insert_person_row(cursor, pid: str, family_id: str, person: dict, now: str) -> None:
    is_placeholder = 1 if person.get("is_placeholder") else 0
    cursor.execute(
        """INSERT INTO persons (
            id, family_id, name, gender, birth_year, death_year, generation,
            generation_name, generation_prefix, parent_id,
            courtesy_name, art_name, county, town, village, biography,
            ai_confidence, review_status, status, is_placeholder, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            pid, family_id, person.get("name"), person.get("gender", "unknown"),
            person.get("birth_year"), person.get("death_year"), person.get("generation"),
            person.get("generation_name"), person.get("generation_prefix"), person.get("parent_id"),
            person.get("courtesy_name"), person.get("art_name"),
            person.get("county"), person.get("town"), person.get("village"),
            person.get("biography"), person.get("ai_confidence"),
            person.get("review_status", "confirmed"), person.get("status", "confirmed"),
            is_placeholder, now,
        ),
    )


def _load_family_generation_context(cursor, family_id: str) -> tuple[dict, list[dict], list[dict]]:
    family = dict(cursor.execute("SELECT * FROM families WHERE id = ?", (family_id,)).fetchone())
    persons = [dict(r) for r in cursor.execute(
        "SELECT * FROM persons WHERE family_id = ?", (family_id,)
    ).fetchall()]
    relations = [dict(r) for r in cursor.execute(
        "SELECT * FROM relations WHERE family_id = ?", (family_id,)
    ).fetchall()]
    return family, persons, relations


def _persist_family_generations(cursor, family_id: str) -> dict:
    """按族谱始祖与起始代数重算并写回 generation 字段。"""
    family, persons, relations = _load_family_generation_context(cursor, family_id)
    if not persons:
        return {"persons": [], "root_person_id": family.get("root_person_id"), "unresolved_ids": []}

    start_gen = int(family.get("start_generation") or 1)
    result = recalculate_generations(
        persons,
        relations,
        root_person_id=family.get("root_person_id"),
        start_generation=start_gen,
    )
    now = datetime.now().isoformat()
    for p in result["persons"]:
        cursor.execute("UPDATE persons SET generation = ? WHERE id = ?", (p.get("generation"), p["id"]))
    root_id = result.get("root_person_id")
    if root_id and root_id != family.get("root_person_id"):
        cursor.execute(
            "UPDATE families SET root_person_id = ?, updated_at = ? WHERE id = ?",
            (root_id, now, family_id),
        )
    return result


def _insert_relation_row(
    cursor,
    family_id: str,
    from_id: str,
    to_id: str,
    rtype: str,
    *,
    status: str = "confirmed",
    confidence: float = 1.0,
    relation_subtype: str = "birth",
    now: str,
) -> str:
    rid = str(uuid.uuid4())[:8]
    cursor.execute(
        """INSERT INTO relations (
            id, family_id, from_person_id, to_person_id, relation_type,
            status, confidence, relation_subtype, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (rid, family_id, from_id, to_id, rtype, status, confidence, relation_subtype, now),
    )
    if rtype == "parent_child":
        cursor.execute("UPDATE persons SET parent_id = ? WHERE id = ?", (from_id, to_id))
    return rid


class FamilyCreate(BaseModel):
    name: str
    surname: Optional[str] = None
    description: Optional[str] = None
    start_generation: Optional[int] = 1

@app.get("/api/health")
async def health_check():
    """轻量健康检查，供前端判断后端是否可用。"""
    conn = get_db()
    c = conn.cursor()
    family_count = c.execute("SELECT COUNT(*) FROM families").fetchone()[0]
    conn.close()
    return {"success": True, "families": family_count}


@app.get("/api/families")
async def get_families():
    conn = get_db()
    c = conn.cursor()
    families = c.execute("""SELECT f.*, COUNT(p.id) as person_count FROM families f
        LEFT JOIN persons p ON p.family_id = f.id GROUP BY f.id ORDER BY f.created_at DESC""").fetchall()
    conn.close()
    return [dict(f) for f in families]

@app.post("/api/families")
async def create_family(family: FamilyCreate):
    conn = get_db()
    c = conn.cursor()
    fid = str(uuid.uuid4())[:8]
    now = datetime.now().isoformat()
    start_gen = max(1, int(family.start_generation or 1))
    c.execute(
        """INSERT INTO families (id, name, surname, description, start_generation, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (fid, family.name, family.surname, family.description, start_gen, now, now),
    )
    conn.commit()
    conn.close()
    return {"id": fid, "name": family.name, "success": True}

@app.put("/api/families/{family_id}")
async def update_family(family_id: str, data: dict):
    """编辑族谱名称、姓氏、简介"""
    conn = get_db()
    c = conn.cursor()
    family = c.execute("SELECT id FROM families WHERE id = ?", (family_id,)).fetchone()
    if not family:
        conn.close()
        raise HTTPException(status_code=404, detail="Family not found")
    now = datetime.now().isoformat()
    recalc = False
    name = data.get("name")
    surname = data.get("surname")
    description = data.get("description")
    start_generation = data.get("start_generation")
    root_person_id = data.get("root_person_id")

    if start_generation is not None:
        start_generation = max(1, int(start_generation))
        recalc = True
    if root_person_id is not None:
        recalc = True

    source_text = data.get("source_text")
    source_annotations = data.get("source_annotations")
    if isinstance(source_annotations, (list, dict)):
        source_annotations = json.dumps(source_annotations, ensure_ascii=False)

    c.execute(
        """UPDATE families SET name=?, surname=?, description=?, start_generation=COALESCE(?, start_generation),
           root_person_id=COALESCE(?, root_person_id),
           source_text=COALESCE(?, source_text),
           source_annotations=COALESCE(?, source_annotations),
           updated_at=? WHERE id=?""",
        (
            name,
            surname,
            description,
            start_generation,
            root_person_id,
            source_text,
            source_annotations,
            now,
            family_id,
        ),
    )
    if recalc:
        _persist_family_generations(c, family_id)
    conn.commit()
    row = c.execute("SELECT * FROM families WHERE id = ?", (family_id,)).fetchone()
    conn.close()
    return {"success": True, "family": dict(row)}


@app.put("/api/families/{family_id}/source-text")
async def update_family_source_text(family_id: str, data: dict):
    """保存族谱 OCR/粘贴原文与姓名标注（写入当前活跃版本或新建第 1 版）。"""
    conn = get_db()
    c = conn.cursor()
    family = c.execute("SELECT id FROM families WHERE id = ?", (family_id,)).fetchone()
    if not family:
        conn.close()
        raise HTTPException(status_code=404, detail="Family not found")

    migrate_legacy_family_source(c, family_id)
    text = data.get("source_text") or ""
    annotations = data.get("source_annotations")
    origin = data.get("origin") or "manual"

    active = c.execute(
        "SELECT active_source_version_id FROM families WHERE id = ?",
        (family_id,),
    ).fetchone()
    active_id = active["active_source_version_id"] if active else None

    if not active_id:
        label = "第1版 · OCR 原始" if origin == "ocr" else "第1版"
        vid = create_source_version(
            c, family_id,
            source_text=text,
            source_annotations=annotations,
            label=label,
            status="confirmed" if origin == "ocr" else "draft",
            set_active=True,
        )
    else:
        vid = active_id
        update_source_version(
            c, family_id, vid,
            source_text=text,
            source_annotations=annotations,
        )

    conn.commit()
    row = c.execute("SELECT * FROM families WHERE id = ?", (family_id,)).fetchone()
    version = get_source_version(c, family_id, vid)
    conn.close()
    return {"success": True, "family": dict(row), "version": version}


@app.get("/api/families/{family_id}/source-versions")
async def get_family_source_versions(family_id: str):
    conn = get_db()
    c = conn.cursor()
    family = c.execute("SELECT id FROM families WHERE id = ?", (family_id,)).fetchone()
    if not family:
        conn.close()
        raise HTTPException(status_code=404, detail="Family not found")
    payload = list_source_versions(c, family_id)
    conn.close()
    return {"success": True, **payload}


@app.post("/api/families/{family_id}/source-versions")
async def post_family_source_version(family_id: str, data: dict):
    """另存为新版本（迭代稿）。"""
    conn = get_db()
    c = conn.cursor()
    family = c.execute("SELECT id FROM families WHERE id = ?", (family_id,)).fetchone()
    if not family:
        conn.close()
        raise HTTPException(status_code=404, detail="Family not found")

    migrate_legacy_family_source(c, family_id)
    version_no = data.get("version_no")
    label = data.get("label")
    if not label and version_no:
        label = f"第{version_no}版"
    vid = create_source_version(
        c, family_id,
        source_text=data.get("source_text") or "",
        source_annotations=data.get("source_annotations"),
        label=label,
        status=data.get("status") or "draft",
        note=data.get("note"),
        set_active=bool(data.get("set_active")),
    )
    conn.commit()
    version = get_source_version(c, family_id, vid)
    row = c.execute("SELECT * FROM families WHERE id = ?", (family_id,)).fetchone()
    conn.close()
    return {"success": True, "version": version, "family": dict(row)}


@app.put("/api/families/{family_id}/source-versions/{version_id}")
async def put_family_source_version(family_id: str, version_id: str, data: dict):
    conn = get_db()
    c = conn.cursor()
    version = update_source_version(
        c, family_id, version_id,
        source_text=data.get("source_text"),
        source_annotations=data.get("source_annotations"),
        label=data.get("label"),
        note=data.get("note"),
    )
    if not version:
        conn.close()
        raise HTTPException(status_code=404, detail="Version not found")
    conn.commit()
    row = c.execute("SELECT * FROM families WHERE id = ?", (family_id,)).fetchone()
    conn.close()
    return {"success": True, "version": version, "family": dict(row)}


@app.post("/api/families/{family_id}/source-versions/{version_id}/confirm")
async def confirm_family_source_version(family_id: str, version_id: str):
    """确认此版为可用定稿，并设为 AI/整理使用的活跃版本。"""
    conn = get_db()
    c = conn.cursor()
    version = confirm_source_version(c, family_id, version_id)
    if not version:
        conn.close()
        raise HTTPException(status_code=404, detail="Version not found")
    conn.commit()
    row = c.execute("SELECT * FROM families WHERE id = ?", (family_id,)).fetchone()
    conn.close()
    return {"success": True, "version": version, "family": dict(row)}


@app.post("/api/families/{family_id}/source-versions/{version_id}/activate")
async def activate_family_source_version(family_id: str, version_id: str):
    conn = get_db()
    c = conn.cursor()
    version = set_active_source_version(c, family_id, version_id)
    if not version:
        conn.close()
        raise HTTPException(status_code=404, detail="Version not found")
    conn.commit()
    row = c.execute("SELECT * FROM families WHERE id = ?", (family_id,)).fetchone()
    conn.close()
    return {"success": True, "version": version, "family": dict(row)}


@app.post("/api/families/{family_id}/source-versions/text-preview")
async def preview_text_edition(family_id: str, data: dict | None = None):
    """预览当前原文的关系描述稿，不创建版本、不切换选中版本。"""
    data = data or {}
    conn = get_db()
    c = conn.cursor()
    family = c.execute("SELECT id FROM families WHERE id = ?", (family_id,)).fetchone()
    if not family:
        conn.close()
        raise HTTPException(status_code=404, detail="Family not found")

    source_version_id = (data.get("source_version_id") or "").strip() or None
    if source_version_id:
        src = get_source_version(c, family_id, source_version_id)
    else:
        _, src = get_active_source_for_family(c, family_id)

    conn.close()
    if not src:
        raise HTTPException(status_code=400, detail="请先选择原文版本")
    raw = (src.get("source_text") or "").strip()
    if not raw:
        raise HTTPException(status_code=400, detail="当前原文版本无内容")

    relation_text = build_local_relation_description(raw)
    return {
        "success": True,
        "relation_text": relation_text,
        "source_version_id": src.get("id"),
        "source_version_label": src.get("label"),
    }


@app.post("/api/families/{family_id}/source-versions/sync-text-edition")
async def sync_text_edition(family_id: str, data: dict | None = None):
    """手动保存文字版草稿（可选）；默认不切换当前选中版本。"""
    data = data or {}
    conn = get_db()
    c = conn.cursor()
    family = c.execute("SELECT id FROM families WHERE id = ?", (family_id,)).fetchone()
    if not family:
        conn.close()
        raise HTTPException(status_code=404, detail="Family not found")

    source_version_id = (data.get("source_version_id") or "").strip() or None
    if not source_version_id:
        _, active = get_active_source_for_family(c, family_id)
        source_version_id = active.get("id") if active else None
    if not source_version_id:
        conn.close()
        raise HTTPException(status_code=400, detail="请先选择或保存一个原文版本")

    src = get_source_version(c, family_id, source_version_id)
    if not src:
        conn.close()
        raise HTTPException(status_code=404, detail="原文版本不存在")

    raw = (src.get("source_text") or "").strip()
    if not raw:
        conn.close()
        raise HTTPException(status_code=400, detail="当前原文版本无内容")

    relation_text = build_local_relation_description(raw)
    set_active = bool(data.get("set_active"))
    try:
        version = upsert_text_edition_from_source(
            c, family_id, source_version_id, relation_text, set_active=set_active,
        )
    except ValueError as exc:
        conn.close()
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    conn.commit()
    payload = list_source_versions(c, family_id)
    row = c.execute("SELECT * FROM families WHERE id = ?", (family_id,)).fetchone()
    conn.close()
    return {
        "success": True,
        "version": version,
        "relation_text": relation_text,
        "source_version_id": source_version_id,
        **payload,
        "family": dict(row),
    }


@app.delete("/api/families/{family_id}/source-versions/{version_id}")
async def delete_family_source_version(family_id: str, version_id: str):
    """删除无用原文版本（至少保留一版）。"""
    conn = get_db()
    c = conn.cursor()
    family = c.execute("SELECT id FROM families WHERE id = ?", (family_id,)).fetchone()
    if not family:
        conn.close()
        raise HTTPException(status_code=404, detail="Family not found")
    try:
        result = delete_source_version(c, family_id, version_id)
    except ValueError as e:
        conn.close()
        raise HTTPException(status_code=400, detail=str(e)) from e
    if not result:
        conn.close()
        raise HTTPException(status_code=404, detail="Version not found")
    conn.commit()
    payload = list_source_versions(c, family_id)
    row = c.execute("SELECT * FROM families WHERE id = ?", (family_id,)).fetchone()
    conn.close()
    return {"success": True, **result, **payload, "family": dict(row)}


@app.delete("/api/families/{family_id}")
async def delete_family(family_id: str):
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM relations WHERE family_id = ?", (family_id,))
    c.execute("DELETE FROM ocr_records WHERE family_id = ?", (family_id,))
    c.execute("DELETE FROM family_source_versions WHERE family_id = ?", (family_id,))
    c.execute("DELETE FROM persons WHERE family_id = ?", (family_id,))
    c.execute("DELETE FROM families WHERE id = ?", (family_id,))
    conn.commit()
    conn.close()
    return {"success": True}

@app.get("/api/families/{family_id}")
async def get_family(family_id: str):
    conn = get_db()
    c = conn.cursor()
    family = c.execute("SELECT * FROM families WHERE id = ?", (family_id,)).fetchone()
    conn.close()
    if not family:
        raise HTTPException(status_code=404, detail="Family not found")
    return dict(family)

@app.get("/api/families/{family_id}/persons")
async def get_persons(family_id: str):
    conn = get_db()
    c = conn.cursor()
    rows = c.execute(
        "SELECT * FROM persons WHERE family_id = ? ORDER BY generation, name", (family_id,)
    ).fetchall()
    result = []
    for row in rows:
        person = row_to_person(row)
        person["spouse_id"] = get_spouse_id(c, person["id"])
        result.append(person)
    conn.close()
    return result


@app.get("/api/persons/{person_id}")
async def get_person_detail(person_id: str):
    conn = get_db()
    c = conn.cursor()
    row = c.execute("SELECT * FROM persons WHERE id = ?", (person_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Person not found")
    person = row_to_person(row)
    fid = person["family_id"]

    parents = []
    if person.get("parent_id"):
        pr = c.execute("SELECT * FROM persons WHERE id = ?", (person["parent_id"],)).fetchone()
        if pr:
            parents.append(row_to_person(pr))

    children = [row_to_person(r) for r in c.execute(
        "SELECT * FROM persons WHERE parent_id = ?", (person_id,)
    ).fetchall()]

    rel_rows = c.execute(
        """SELECT r.*, p1.name as from_name, p2.name as to_name
           FROM relations r
           LEFT JOIN persons p1 ON p1.id = r.from_person_id
           LEFT JOIN persons p2 ON p2.id = r.to_person_id
           WHERE r.family_id = ? AND (r.from_person_id = ? OR r.to_person_id = ?)""",
        (fid, person_id, person_id),
    ).fetchall()
    relations = [dict(r) for r in rel_rows]
    person["spouse_id"] = get_spouse_id(c, person_id)
    spouse = None
    if person.get("spouse_id"):
        sr = c.execute("SELECT * FROM persons WHERE id = ?", (person["spouse_id"],)).fetchone()
        if sr:
            spouse = row_to_person(sr)
    conn.close()
    return {
        "success": True,
        "person": person,
        "parents": parents,
        "children": children,
        "spouse": spouse,
        "relations": relations,
    }


@app.post("/api/persons")
async def create_person(person: dict):
    conn = get_db()
    c = conn.cursor()
    pid = str(uuid.uuid4())[:8]
    now = datetime.now().isoformat()
    family_id = person.get("family_id")
    _insert_person_row(c, pid, family_id, person, now)
    apply_person_relations(c, family_id, pid, person, is_new=True, now=now)
    _persist_family_generations(c, family_id)

    conn.commit()
    conn.close()
    return {"id": pid, "success": True}

@app.post("/api/persons/batch")
async def create_persons_batch(persons_data: dict):
    family_id = persons_data.get("family_id")
    persons_list = persons_data.get("persons", [])
    parent_map = persons_data.get("parent_map", {})
    relations_list = persons_data.get("relations", [])
    merge = bool(persons_data.get("merge"))

    conn = get_db()
    c = conn.cursor()
    now = datetime.now().isoformat()
    created_ids: dict[str, str] = {}
    relations_to_create: list[dict] = []

    if merge:
        for row in c.execute(
            "SELECT id, name FROM persons WHERE family_id = ?", (family_id,)
        ).fetchall():
            created_ids[row["name"]] = row["id"]

    for p in persons_list:
        name = (p.get("name") or "").strip()
        if not name:
            continue

        if merge and name in created_ids:
            pid = created_ids[name]
            c.execute(
                """UPDATE persons SET gender=?, birth_year=?, death_year=?, generation=?,
                   generation_name=?, generation_prefix=?, courtesy_name=?, art_name=?,
                   county=?, town=?, village=?, biography=?, ai_confidence=?, review_status=?
                   WHERE id=?""",
                (
                    p.get("gender", "unknown"),
                    p.get("birth_year"),
                    p.get("death_year"),
                    p.get("generation"),
                    p.get("generation_name"),
                    p.get("generation_prefix"),
                    p.get("courtesy_name"),
                    p.get("art_name"),
                    p.get("county"),
                    p.get("town"),
                    p.get("village"),
                    p.get("biography"),
                    p.get("ai_confidence"),
                    p.get("review_status", "pending_review"),
                    pid,
                ),
            )
            continue

        pid = str(uuid.uuid4())[:8]
        created_ids[name] = pid
        _insert_person_row(c, pid, family_id, p, now)

    # AI 解析的 relations（优先）
    for rel in relations_list:
        from_name = rel.get("from")
        to_name = rel.get("to")
        if not from_name or not to_name:
            continue
        if from_name not in created_ids or to_name not in created_ids:
            continue
        from_id = created_ids[from_name]
        to_id = created_ids[to_name]
        rtype = rel.get("type") or "parent_child"
        if merge:
            exists = c.execute(
                """SELECT id FROM relations
                   WHERE family_id=? AND from_person_id=? AND to_person_id=? AND relation_type=?""",
                (family_id, from_id, to_id, rtype),
            ).fetchone()
            if exists:
                if rtype == "parent_child":
                    c.execute("UPDATE persons SET parent_id = ? WHERE id = ?", (from_id, to_id))
                continue
        relations_to_create.append({
            "id": str(uuid.uuid4())[:8],
            "from": from_id,
            "to": to_id,
            "type": rtype,
            "status": rel.get("status") or "inferred",
            "confidence": rel.get("confidence") or 0.85,
            "relation_subtype": rel.get("relation_subtype") or "birth",
        })
        if rtype == "parent_child":
            c.execute("UPDATE persons SET parent_id = ? WHERE id = ?", (from_id, to_id))

    # 兼容旧 parent_map
    for child_name, parent_name in parent_map.items():
        if child_name not in created_ids or parent_name not in created_ids:
            continue
        from_id = created_ids[parent_name]
        to_id = created_ids[child_name]
        if any(r["from"] == from_id and r["to"] == to_id for r in relations_to_create):
            continue
        relations_to_create.append({
            "id": str(uuid.uuid4())[:8],
            "from": from_id,
            "to": to_id,
            "type": "parent_child",
            "status": "confirmed",
            "confidence": 1.0,
        })
        c.execute("UPDATE persons SET parent_id = ? WHERE id = ?", (from_id, to_id))

    for rel in relations_to_create:
        c.execute(
            """INSERT INTO relations (
                id, family_id, from_person_id, to_person_id, relation_type,
                status, confidence, relation_subtype, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                rel["id"], family_id, rel["from"], rel["to"], rel["type"],
                rel["status"], rel["confidence"], rel.get("relation_subtype", "birth"), now,
            ),
        )

    _persist_family_generations(c, family_id)
    conn.commit()
    conn.close()
    return {"success": True, "count": len(created_ids), "relation_count": len(relations_to_create), "merged": merge}


@app.post("/api/families/{family_id}/parse-import/preview")
async def preview_parse_import(family_id: str, data: dict):
    """对比两阶段解析结果与主谱，返回可新增成员/关系（不写入）。"""
    parsed_persons = data.get("persons") or []
    parsed_relations = data.get("relations") or []
    if not parsed_persons and not parsed_relations:
        raise HTTPException(status_code=400, detail="解析结果为空")

    conn = get_db()
    c = conn.cursor()
    family_row = c.execute("SELECT id FROM families WHERE id = ?", (family_id,)).fetchone()
    if not family_row:
        conn.close()
        raise HTTPException(status_code=404, detail="Family not found")

    persons_rows = c.execute("SELECT * FROM persons WHERE family_id = ?", (family_id,)).fetchall()
    rel_rows = c.execute("SELECT * FROM relations WHERE family_id = ?", (family_id,)).fetchall()
    conn.close()

    id_to_name = {row["id"]: row["name"] for row in persons_rows}
    persons = [row_to_person(r) for r in persons_rows]
    relations = []
    for r in rel_rows:
        fn = id_to_name.get(r["from_person_id"])
        tn = id_to_name.get(r["to_person_id"])
        if fn and tn:
            relations.append({
                "from": fn,
                "to": tn,
                "type": r["relation_type"] or "parent_child",
                "status": r.get("status") or "confirmed",
            })

    compare = compare_parsed_with_genealogy(
        persons, relations, parsed_persons, parsed_relations,
    )
    return {"success": True, "compare": compare}

async def update_person(person_id: str, person: dict):
    conn = get_db()
    c = conn.cursor()
    row = c.execute("SELECT family_id FROM persons WHERE id = ?", (person_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Person not found")
    family_id = dict(row)["family_id"]
    now = datetime.now().isoformat()

    parent_id = person.get("parent_id")
    c.execute(
        """UPDATE persons SET name=?, gender=?, birth_year=?, death_year=?, generation=?,
           generation_name=?, generation_prefix=?, parent_id=?,
           courtesy_name=?, art_name=?, county=?, town=?, village=?, biography=?, review_status=?
           WHERE id=?""",
        (
            person.get("name"), person.get("gender"), person.get("birth_year"), person.get("death_year"),
            person.get("generation"), person.get("generation_name"), person.get("generation_prefix"),
            parent_id, person.get("courtesy_name"), person.get("art_name"),
            person.get("county"), person.get("town"), person.get("village"), person.get("biography"),
            person.get("review_status", "confirmed"), person_id,
        ),
    )
    apply_person_relations(c, family_id, person_id, person, is_new=False, now=now)
    _persist_family_generations(c, family_id)
    conn.commit()
    conn.close()
    return {"success": True}

@app.delete("/api/persons/{person_id}")
async def delete_person(person_id: str):
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE persons SET parent_id = NULL WHERE parent_id = ?", (person_id,))
    c.execute("DELETE FROM relations WHERE from_person_id = ? OR to_person_id = ?", (person_id, person_id))
    c.execute("DELETE FROM persons WHERE id = ?", (person_id,))
    conn.commit()
    conn.close()
    return {"success": True}

@app.get("/api/families/{family_id}/relations")
async def get_relations(family_id: str):
    conn = get_db()
    c = conn.cursor()
    rel_rows = c.execute(
        """SELECT r.*, p1.name as from_name, p2.name as to_name
           FROM relations r
           LEFT JOIN persons p1 ON p1.id = r.from_person_id
           LEFT JOIN persons p2 ON p2.id = r.to_person_id
           WHERE r.family_id = ? ORDER BY r.relation_type, r.created_at""",
        (family_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rel_rows]


@app.post("/api/relations")
async def create_relation(relation: dict):
    family_id = relation.get("family_id")
    from_id = relation.get("from_person_id")
    to_id = relation.get("to_person_id")
    rtype = relation.get("relation_type") or "parent_child"
    if not family_id or not from_id or not to_id:
        raise HTTPException(status_code=400, detail="缺少 family_id / from_person_id / to_person_id")
    if from_id == to_id:
        raise HTTPException(status_code=400, detail="不能与自己建立关系")

    conn = get_db()
    c = conn.cursor()
    now = datetime.now().isoformat()
    try:
        rid = create_relation_record(
            c, family_id, from_id, to_id, rtype,
            status=relation.get("status", "confirmed"),
            confidence=float(relation.get("confidence", 1.0)),
            relation_subtype=relation.get("relation_subtype", "birth"),
            now=now,
        )
    except ValueError as exc:
        conn.close()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _persist_family_generations(c, family_id)
    conn.commit()
    conn.close()
    return {"id": rid, "success": True}


@app.put("/api/relations/{relation_id}")
async def update_relation(relation_id: str, data: dict):
    conn = get_db()
    c = conn.cursor()
    row = c.execute("SELECT id FROM relations WHERE id = ?", (relation_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Relation not found")
    c.execute(
        """UPDATE relations SET status=?, confidence=?, note=?, relation_subtype=COALESCE(?, relation_subtype)
           WHERE id=?""",
        (
            data.get("status", "confirmed"),
            data.get("confidence", 1.0),
            data.get("note"),
            data.get("relation_subtype"),
            relation_id,
        ),
    )
    conn.commit()
    conn.close()
    return {"success": True}


@app.delete("/api/relations/{relation_id}")
async def delete_relation(relation_id: str):
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM relations WHERE id = ?", (relation_id,))
    conn.commit()
    conn.close()
    return {"success": True}


@app.get("/api/families/{family_id}/tree")
async def get_family_tree(family_id: str, style: str = "su", hide_placeholders: bool = True):
    conn = get_db()
    c = conn.cursor()
    family = c.execute("SELECT * FROM families WHERE id = ?", (family_id,)).fetchone()
    if not family:
        conn.close()
        raise HTTPException(status_code=404, detail="Family not found")
    persons = [row_to_person(r) for r in c.execute(
        "SELECT * FROM persons WHERE family_id = ? ORDER BY generation, name", (family_id,)
    ).fetchall()]
    relations = [dict(r) for r in c.execute(
        "SELECT * FROM relations WHERE family_id = ?", (family_id,)
    ).fetchall()]
    conn.close()
    tree = build_family_tree(persons, relations, style=style, hide_placeholders=hide_placeholders)
    fam = dict(family)
    return {
        "success": True,
        **tree,
        "start_generation": int(fam.get("start_generation") or 1),
        "root_person_id": fam.get("root_person_id"),
    }


@app.post("/api/families/{family_id}/recalculate-generations")
async def recalculate_family_generations(family_id: str):
    conn = get_db()
    c = conn.cursor()
    family = c.execute("SELECT id FROM families WHERE id = ?", (family_id,)).fetchone()
    if not family:
        conn.close()
        raise HTTPException(status_code=404, detail="Family not found")
    result = _persist_family_generations(c, family_id)
    conn.commit()
    row = c.execute("SELECT * FROM families WHERE id = ?", (family_id,)).fetchone()
    conn.close()
    return {
        "success": True,
        "root_person_id": result.get("root_person_id"),
        "start_generation": int(dict(row).get("start_generation") or 1),
        "unresolved_count": len(result.get("unresolved_ids") or []),
        "unresolved_ids": result.get("unresolved_ids") or [],
    }


@app.post("/api/families/{family_id}/persons/kinship")
async def add_person_by_kinship(family_id: str, data: dict):
    """按称谓（子/孙/曾孙等）相对锚点成员添加，自动补全中间代际占位。"""
    anchor_id = data.get("anchor_id")
    kinship = data.get("kinship") or "子"
    person_data = data.get("person") or {}
    if not anchor_id:
        raise HTTPException(status_code=400, detail="缺少 anchor_id")
    if not (person_data.get("name") or "").strip():
        raise HTTPException(status_code=400, detail="缺少成员姓名")

    conn = get_db()
    c = conn.cursor()
    family, persons, relations = _load_family_generation_context(c, family_id)
    if not family:
        conn.close()
        raise HTTPException(status_code=404, detail="Family not found")

    start_gen = int(family.get("start_generation") or 1)
    existing_ids = {str(p["id"]) for p in persons if p.get("id")}
    existing_rel_keys = {
        (str(r["from_person_id"]), str(r["to_person_id"]), r["relation_type"])
        for r in relations
    }

    result = add_person_with_kinship(
        persons,
        relations,
        str(anchor_id),
        kinship,
        person_data,
        start_generation=start_gen,
    )
    if not result.get("success"):
        conn.close()
        raise HTTPException(status_code=400, detail=result.get("error", "添加失败"))

    now = datetime.now().isoformat()
    placeholders_added = 0
    relations_added = 0

    for p in result.get("persons", []):
        pid = str(p.get("id") or "")
        if not pid or pid in existing_ids:
            continue
        _insert_person_row(c, pid, family_id, p, now)
        existing_ids.add(pid)
        if p.get("is_placeholder"):
            placeholders_added += 1

    for rel in result.get("relations", []):
        fid = rel.get("from_person_id") or rel.get("from")
        tid = rel.get("to_person_id") or rel.get("to")
        rtype = rel.get("relation_type") or rel.get("type") or "parent_child"
        if not fid or not tid:
            continue
        key = (str(fid), str(tid), rtype)
        if key in existing_rel_keys:
            continue
        _insert_relation_row(
            c, family_id, str(fid), str(tid), rtype,
            status=rel.get("status", "inferred"),
            confidence=float(rel.get("confidence") if rel.get("confidence") is not None else 0.85),
            relation_subtype=rel.get("relation_subtype", "birth"),
            now=now,
        )
        existing_rel_keys.add(key)
        relations_added += 1

    new_person = dict(result["person"])
    new_pid = str(new_person.get("id") or uuid.uuid4().hex[:8])
    new_person["id"] = new_pid
    if result.get("parent_id"):
        new_person["parent_id"] = result["parent_id"]
    _insert_person_row(c, family_id, new_pid, new_person, now)

    parent_id = result.get("parent_id")
    delta = kinship_generation_delta(kinship)
    if parent_id and delta is not None and delta >= 1:
        rel_key = (str(parent_id), new_pid, "parent_child")
        if rel_key not in existing_rel_keys:
            _insert_relation_row(
                c, family_id, str(parent_id), new_pid, "parent_child",
                status="confirmed",
                confidence=1.0,
                relation_subtype=data.get("relation_subtype", "birth"),
                now=now,
            )
            relations_added += 1

    gen_result = _persist_family_generations(c, family_id)
    conn.commit()
    conn.close()

    return {
        "success": True,
        "id": new_pid,
        "target_generation": result.get("target_generation"),
        "placeholders_added": placeholders_added,
        "relations_added": relations_added,
        "root_person_id": gen_result.get("root_person_id"),
    }


@app.get("/api/families/{family_id}/search")
async def search_family_get(family_id: str, q: str = "", mode: str = "keyword"):
    return await _search_family_impl(family_id, q, mode)


@app.post("/api/families/{family_id}/search")
async def search_family_post(family_id: str, data: dict):
    return await _search_family_impl(
        family_id,
        data.get("q", ""),
        data.get("mode", "keyword"),
        use_ai=bool(data.get("use_ai")),
    )


async def _search_family_impl(family_id: str, q: str, mode: str = "keyword", use_ai: bool = False):
    conn = get_db()
    c = conn.cursor()
    persons = [row_to_person(r) for r in c.execute(
        "SELECT * FROM persons WHERE family_id = ?", (family_id,)
    ).fetchall()]
    relations = [dict(r) for r in c.execute(
        "SELECT * FROM relations WHERE family_id = ?", (family_id,)
    ).fetchall()]
    conn.close()

    if mode == "nl" or use_ai:
        selection = load_model_selection()
        parse_cfg = selection["parse"]

        async def ai_fn(prompt):
            return await call_text_model(parse_cfg["provider"], parse_cfg["model"], prompt)

        if _is_provider_configured(parse_cfg["provider"]):
            results, err = await nl_search_with_ai(persons, relations, q, ai_fn)
            if results:
                return {"success": True, "query": q, "mode": "nl", "count": len(results), "results": results}
        results = rule_based_nl_search(persons, q)
        return {"success": True, "query": q, "mode": "nl", "count": len(results), "results": results}

    results = search_persons(persons, q)
    return {"success": True, "query": q, "mode": "keyword", "count": len(results), "results": results}


@app.get("/api/families/{family_id}/export/pdf")
async def export_family_pdf(family_id: str, style: str = "su"):
    conn = get_db()
    c = conn.cursor()
    family = c.execute("SELECT * FROM families WHERE id = ?", (family_id,)).fetchone()
    if not family:
        conn.close()
        raise HTTPException(status_code=404, detail="Family not found")
    persons = [row_to_person(r) for r in c.execute(
        "SELECT * FROM persons WHERE family_id = ?", (family_id,)
    ).fetchall()]
    relations = [dict(r) for r in c.execute(
        "SELECT * FROM relations WHERE family_id = ?", (family_id,)
    ).fetchall()]
    conn.close()
    html = generate_genealogy_html(dict(family), persons, relations, style=style)
    return HTMLResponse(content=html)

# ==================== 族谱智能体 API ====================

def _is_provider_configured(provider_id: str) -> bool:
    api_key, _, group_id = get_provider_credentials(provider_id)
    if provider_id == "minimax":
        return bool(api_key and group_id)
    return bool(api_key)


@app.get("/api/agent/status")
async def agent_status():
    """族谱智能体状态：能力列表与 AI 是否就绪"""
    selection = load_model_selection()
    ocr = selection["ocr"]
    parse_cfg = selection["parse"]
    return get_agent_status(
        ocr_configured=_is_provider_configured(ocr["provider"]),
        parse_configured=_is_provider_configured(parse_cfg["provider"]),
        ocr_selection=ocr,
        parse_selection=parse_cfg,
    )


@app.post("/api/agent/generate")
async def agent_generate(data: dict):
    """自动整理族谱：推理父子/配偶关系，生成树预览；可选 persist 入库"""
    text = data.get("text", "")
    persons = data.get("persons", [])
    relations = data.get("relations", [])
    style = data.get("style", "su")
    family_id = data.get("family_id")
    persist = bool(data.get("persist"))

    built = auto_build_genealogy(text, persons, relations, style=style)
    if not built.get("success"):
        return built

    if persist and family_id:
        conn = get_db()
        c = conn.cursor()
        now = datetime.now().isoformat()
        existing = c.execute(
            "SELECT id, name, generation, gender, birth_year, parent_id FROM persons WHERE family_id = ?",
            (family_id,),
        ).fetchall()
        name_to_id = {dict(row)["name"]: dict(row)["id"] for row in existing if dict(row).get("name")}
        before_count = len(name_to_id)
        for p in built["persons"]:
            name = p.get("name")
            if not name or name in name_to_id:
                continue
            pid = str(uuid.uuid4())[:8]
            name_to_id[name] = pid
            _insert_person_row(c, pid, family_id, p, now)

        existing_rels = c.execute(
            "SELECT from_person_id, to_person_id, relation_type FROM relations WHERE family_id = ?",
            (family_id,),
        ).fetchall()
        existing_keys = {
            (r["from_person_id"], r["to_person_id"], r["relation_type"])
            for r in existing_rels
        }
        added = 0
        for rel in built.get("relations", []):
            from_name, to_name = rel.get("from"), rel.get("to")
            if not from_name or not to_name:
                continue
            from_id = name_to_id.get(from_name)
            to_id = name_to_id.get(to_name)
            if not from_id or not to_id:
                continue
            rtype = rel.get("type") or "parent_child"
            key = (from_id, to_id, rtype)
            if key in existing_keys:
                continue
            rid = str(uuid.uuid4())[:8]
            c.execute(
                """INSERT INTO relations (id, family_id, from_person_id, to_person_id, relation_type, status, confidence, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    rid, family_id, from_id, to_id, rtype,
                    rel.get("status", "inferred"), rel.get("confidence", 0.8), now,
                ),
            )
            existing_keys.add(key)
            added += 1
            if rtype == "parent_child":
                c.execute("UPDATE persons SET parent_id = ? WHERE id = ?", (from_id, to_id))

        roots = built.get("tree", {}).get("roots") or []
        if roots:
            root_name = roots[0].get("name")
            root_id = name_to_id.get(root_name)
            if root_id:
                c.execute(
                    "UPDATE families SET root_person_id = ?, updated_at = ? WHERE id = ?",
                    (root_id, now, family_id),
                )
        _persist_family_generations(c, family_id)
        conn.commit()
        conn.close()
        built["persisted"] = {"persons_added": len(name_to_id) - before_count, "relations_added": added}

    return built


@app.post("/api/families/{family_id}/rebuild")
async def rebuild_family_genealogy(family_id: str, data: dict | None = None):
    """对已有族谱重新推理关系并补全入库；dry_run 时仅对比原文差异并预览补全项。"""
    data = data or {}
    dry_run = bool(data.get("dry_run"))
    conn = get_db()
    c = conn.cursor()
    family_row = c.execute("SELECT id FROM families WHERE id = ?", (family_id,)).fetchone()
    if not family_row:
        conn.close()
        raise HTTPException(status_code=404, detail="Family not found")

    persons_rows = c.execute(
        "SELECT * FROM persons WHERE family_id = ?", (family_id,)
    ).fetchall()
    rel_rows = c.execute(
        "SELECT * FROM relations WHERE family_id = ?", (family_id,)
    ).fetchall()
    source_text, source_version = get_active_source_for_family(c, family_id)

    if not persons_rows:
        conn.close()
        return {"success": False, "error": "族谱尚无成员"}

    id_to_name = {row["id"]: row["name"] for row in persons_rows}
    persons = [dict(row) for row in persons_rows]
    persons_for_compare = [row_to_person(r) for r in persons_rows]
    relations = []
    for r in rel_rows:
        fn = id_to_name.get(r["from_person_id"])
        tn = id_to_name.get(r["to_person_id"])
        if fn and tn:
            relations.append({
                "from": fn,
                "to": tn,
                "type": r["relation_type"] or "parent_child",
                "status": r.get("status") or "confirmed",
            })

    compare = compare_genealogy_with_source(
        persons_for_compare,
        relations,
        source_text,
        source_version=source_version,
        style=data.get("style", "su"),
    )

    built = auto_build_genealogy(
        data.get("text") or source_text or "",
        persons,
        relations,
        style=data.get("style", "su"),
    )
    if not built.get("success"):
        conn.close()
        return built

    current_rel_set = {
        (rel["from"], rel["to"], rel.get("type") or "parent_child")
        for rel in relations
    }
    proposed_add = []
    for rel in built.get("relations") or []:
        fn, tn = rel.get("from"), rel.get("to")
        rtype = rel.get("type") or "parent_child"
        if fn and tn and (fn, tn, rtype) not in current_rel_set:
            proposed_add.append(rel)

    if dry_run:
        conn.close()
        return {
            "success": True,
            "dry_run": True,
            "compare": compare,
            "rebuild": {"relations_added": len(proposed_add)},
            "proposed_relations": proposed_add[:50],
            "stats": built.get("stats"),
        }

    now = datetime.now().isoformat()
    name_to_id = {p["name"]: p["id"] for p in persons if p.get("name")}
    existing_rels = c.execute(
        "SELECT from_person_id, to_person_id, relation_type FROM relations WHERE family_id = ?",
        (family_id,),
    ).fetchall()
    existing_keys = {
        (r["from_person_id"], r["to_person_id"], r["relation_type"])
        for r in existing_rels
    }
    added = 0
    for rel in built.get("relations", []):
        from_id = name_to_id.get(rel.get("from"))
        to_id = name_to_id.get(rel.get("to"))
        if not from_id or not to_id:
            continue
        rtype = rel.get("type") or "parent_child"
        key = (from_id, to_id, rtype)
        if key in existing_keys:
            continue
        rid = str(uuid.uuid4())[:8]
        c.execute(
            """INSERT INTO relations (id, family_id, from_person_id, to_person_id, relation_type, status, confidence, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                rid, family_id, from_id, to_id, rtype,
                rel.get("status", "inferred"), rel.get("confidence", 0.8), now,
            ),
        )
        existing_keys.add(key)
        added += 1
        if rtype == "parent_child":
            c.execute("UPDATE persons SET parent_id = ? WHERE id = ?", (from_id, to_id))

    roots = built.get("tree", {}).get("roots") or []
    if roots:
        root_id = name_to_id.get(roots[0].get("name"))
        if root_id:
            c.execute(
                "UPDATE families SET root_person_id = ?, updated_at = ? WHERE id = ?",
                (root_id, now, family_id),
            )
    _persist_family_generations(c, family_id)
    conn.commit()
    conn.close()

    built["rebuild"] = {"relations_added": added}
    built["compare"] = compare
    return built


def _fetch_family_relations_named(cursor, family_id: str, persons_rows: list) -> list[dict]:
    id_to_name: dict[str, str] = {}
    for row in persons_rows:
        data = dict(row) if not isinstance(row, dict) else row
        name = (data.get("name") or "").strip()
        pid = data.get("id")
        if name and pid:
            id_to_name[str(pid)] = name
    rel_rows = cursor.execute(
        "SELECT from_person_id, to_person_id, relation_type FROM relations WHERE family_id = ?",
        (family_id,),
    ).fetchall()
    out: list[dict] = []
    for r in rel_rows:
        fn = id_to_name.get(r["from_person_id"])
        tn = id_to_name.get(r["to_person_id"])
        if fn and tn:
            out.append({
                "from": fn,
                "to": tn,
                "type": r["relation_type"] or "parent_child",
            })
    return out


def _ensure_plan_relation_persons(
    cursor,
    family_id: str,
    plan: dict,
    name_to_id: dict,
    norm_to_canonical: dict,
    now: str,
    stats: dict,
) -> None:
    """关系端点若不在主谱，自动补建成员（替换写入/空谱时必需）。"""
    needed: set[str] = set()
    for rel in plan.get("relations_add") or []:
        for key in ("from", "to"):
            raw = (rel.get(key) or "").strip()
            if not raw:
                continue
            canonical = resolve_genealogy_name(raw, norm_to_canonical) or raw
            if canonical not in name_to_id and raw not in name_to_id:
                needed.add(canonical)

    for name in sorted(needed):
        if name in name_to_id:
            continue
        pid = str(uuid.uuid4())[:8]
        _insert_person_row(
            cursor,
            pid,
            family_id,
            {
                "name": name,
                "gender": "unknown",
                "review_status": "pending_review",
            },
            now,
        )
        name_to_id[name] = pid
        norm = normalize_person_name(name)
        if norm:
            norm_to_canonical[norm] = name
        stats["persons_added"] += 1


def _apply_organize_plan(
    cursor,
    family_id: str,
    plan: dict,
    persons: list[dict],
    now: str,
    *,
    apply_mode: str = "merge",
    diff: dict | None = None,
) -> dict:
    """将 AI 整理方案写入数据库。apply_mode: merge=增量合并, replace=完全按方案替换。"""
    persons = [dict(p) for p in persons]
    plan = reconcile_plan_with_genealogy(_normalize_plan(plan), persons)
    _, norm_to_canonical, _ = build_genealogy_name_index(persons)
    name_to_id = {p["name"]: p["id"] for p in persons if p.get("name") and p.get("id")}

    if apply_mode == "replace" and diff is None:
        rel_named = [
            {"from": r["from"], "to": r["to"], "type": r.get("type") or "parent_child"}
            for r in _fetch_family_relations_named(cursor, family_id, persons)
        ]
        diff = compute_organize_diff(persons, rel_named, plan, None)
    stats = {
        "persons_added": 0,
        "persons_updated": 0,
        "persons_removed": 0,
        "relations_added": 0,
        "relations_removed": 0,
        "apply_mode": apply_mode,
    }

    for np in plan.get("new_persons") or []:
        name = (np.get("name") or "").strip()
        if not name or name in name_to_id:
            continue
        if resolve_genealogy_name(name, norm_to_canonical) in name_to_id:
            continue
        pid = str(uuid.uuid4())[:8]
        person_row = {
            "name": name,
            "gender": np.get("gender", "unknown"),
            "generation": np.get("generation"),
            "review_status": "pending_review",
        }
        if np.get("parent_name") and np["parent_name"] in name_to_id:
            person_row["parent_id"] = name_to_id[np["parent_name"]]
        _insert_person_row(cursor, pid, family_id, person_row, now)
        name_to_id[name] = pid
        stats["persons_added"] += 1

    _ensure_plan_relation_persons(
        cursor, family_id, plan, name_to_id, norm_to_canonical, now, stats,
    )

    for upd in plan.get("person_updates") or []:
        name = upd.get("name")
        pid = name_to_id.get(name)
        if not pid:
            continue
        parent_id = name_to_id.get(upd.get("parent_name")) if upd.get("parent_name") else None
        cursor.execute(
            """UPDATE persons SET generation=COALESCE(?, generation), gender=COALESCE(?, gender),
               parent_id=COALESCE(?, parent_id) WHERE id=?""",
            (upd.get("generation"), upd.get("gender"), parent_id, pid),
        )
        stats["persons_updated"] += 1

    for rem in plan.get("relations_remove") or []:
        fn_name = resolve_genealogy_name(rem.get("from") or "", norm_to_canonical)
        tn_name = resolve_genealogy_name(rem.get("to") or "", norm_to_canonical)
        fn = name_to_id.get(fn_name)
        tn = name_to_id.get(tn_name)
        rtype = rem.get("type") or "parent_child"
        if not fn or not tn:
            continue
        cursor.execute(
            """DELETE FROM relations
               WHERE family_id=? AND from_person_id=? AND to_person_id=? AND relation_type=?""",
            (family_id, fn, tn, rtype),
        )
        if cursor.rowcount:
            stats["relations_removed"] += cursor.rowcount
            if rtype == "parent_child":
                cursor.execute("UPDATE persons SET parent_id = NULL WHERE id = ? AND parent_id = ?", (tn, fn))

    existing_rels = cursor.execute(
        "SELECT from_person_id, to_person_id, relation_type FROM relations WHERE family_id = ?",
        (family_id,),
    ).fetchall()
    existing_keys = {
        (r["from_person_id"], r["to_person_id"], r["relation_type"])
        for r in existing_rels
    }

    for rel in plan.get("relations_add") or []:
        fn_name = resolve_genealogy_name(rel.get("from") or "", norm_to_canonical)
        tn_name = resolve_genealogy_name(rel.get("to") or "", norm_to_canonical)
        fn = name_to_id.get(fn_name)
        tn = name_to_id.get(tn_name)
        rtype = rel.get("type") or "parent_child"
        if not fn or not tn or fn == tn:
            continue
        key = (fn, tn, rtype)
        if key in existing_keys:
            continue
        raw_conf = rel.get("confidence")
        conf = float(raw_conf) if raw_conf is not None else 0.9
        _insert_relation_row(
            cursor, family_id, fn, tn, rtype,
            status=rel.get("status", "confirmed"),
            confidence=conf,
            now=now,
        )
        existing_keys.add(key)
        stats["relations_added"] += 1

    if apply_mode == "replace" and diff:
        for rel in diff.get("extra_relations") or []:
            fn = name_to_id.get(rel.get("from"))
            tn = name_to_id.get(rel.get("to"))
            rtype = rel.get("type") or "parent_child"
            if not fn or not tn:
                continue
            cursor.execute(
                """DELETE FROM relations
                   WHERE family_id=? AND from_person_id=? AND to_person_id=? AND relation_type=?""",
                (family_id, fn, tn, rtype),
            )
            if cursor.rowcount:
                stats["relations_removed"] += cursor.rowcount
                if rtype == "parent_child":
                    cursor.execute(
                        "UPDATE persons SET parent_id = NULL WHERE id = ? AND parent_id = ?",
                        (tn, fn),
                    )
                existing_keys.discard((fn, tn, rtype))

        for name in diff.get("extra_persons") or []:
            pid = name_to_id.get(name)
            if not pid:
                continue
            cursor.execute(
                "DELETE FROM relations WHERE family_id=? AND (from_person_id=? OR to_person_id=?)",
                (family_id, pid, pid),
            )
            cursor.execute("DELETE FROM persons WHERE id=? AND family_id=?", (pid, family_id))
            if cursor.rowcount:
                stats["persons_removed"] += 1
                name_to_id.pop(name, None)

    root_name = plan.get("root_person_name")
    if root_name and root_name in name_to_id:
        cursor.execute(
            "UPDATE families SET root_person_id = ?, start_generation = COALESCE(?, start_generation), updated_at = ? WHERE id = ?",
            (name_to_id[root_name], plan.get("start_generation"), now, family_id),
        )
    elif plan.get("start_generation"):
        cursor.execute(
            "UPDATE families SET start_generation = ?, updated_at = ? WHERE id = ?",
            (plan.get("start_generation"), now, family_id),
        )

    _persist_family_generations(cursor, family_id)
    return stats


@app.post("/api/families/{family_id}/clear-genealogy")
async def clear_genealogy(family_id: str, data: dict | None = None):
    """清空主谱成员与关系（保留族谱记录与原文版本）。scope: all | branch。"""
    data = data or {}
    scope = (data.get("scope") or "all").strip().lower()
    root_person_id = (data.get("root_person_id") or "").strip() or None

    conn = get_db()
    c = conn.cursor()
    family_row = c.execute("SELECT id, root_person_id FROM families WHERE id = ?", (family_id,)).fetchone()
    if not family_row:
        conn.close()
        raise HTTPException(status_code=404, detail="Family not found")

    if scope == "branch":
        if not root_person_id:
            conn.close()
            raise HTTPException(status_code=400, detail="清空分支需指定成员")
        person_row = c.execute(
            "SELECT id, name FROM persons WHERE id = ? AND family_id = ?",
            (root_person_id, family_id),
        ).fetchone()
        if not person_row:
            conn.close()
            raise HTTPException(status_code=404, detail="成员不存在")

    try:
        stats = clear_family_genealogy(
            c, family_id, scope=scope, root_person_id=root_person_id,
        )
    except ValueError as exc:
        conn.close()
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    conn.commit()
    conn.close()
    return {"success": True, **stats}


@app.get("/api/families/{family_id}/ai-organize/state")
async def get_ai_organize_state(family_id: str):
    """读取族谱 AI 对话与待应用方案（按 family 持久化）。"""
    conn = get_db()
    c = conn.cursor()
    row = c.execute("SELECT id FROM families WHERE id = ?", (family_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Family not found")
    state = get_ai_chat_state(c, family_id)
    conn.close()
    return {"success": True, **state}


@app.put("/api/families/{family_id}/ai-organize/state")
async def put_ai_organize_state(family_id: str, data: dict):
    """保存族谱 AI 对话与待应用方案。"""
    conn = get_db()
    c = conn.cursor()
    row = c.execute("SELECT id FROM families WHERE id = ?", (family_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Family not found")
    allowed = {
        "messages", "session_id", "session_meta",
        "pending_plan", "pending_diff", "apply_mode", "clean_slate",
    }
    patch = {k: data[k] for k in allowed if k in data}
    if data.get("clear_messages"):
        clear_ai_chat_messages(c, family_id)
        rest = {k: data[k] for k in allowed if k in data}
        if rest:
            state = save_ai_chat_state(c, family_id, rest)
        else:
            state = get_ai_chat_state(c, family_id)
        conn.commit()
        conn.close()
        return {"success": True, **state}
    state = save_ai_chat_state(c, family_id, patch)
    conn.commit()
    conn.close()
    return {"success": True, **state}


@app.post("/api/families/{family_id}/ai-organize/refresh-diff")
async def refresh_ai_organize_diff(family_id: str, data: dict):
    """主谱变更后，按当前库内数据重新计算 AI 方案差异。"""
    plan = _normalize_plan(data.get("plan") or {})
    if (
        not plan.get("relations_add")
        and not plan.get("new_persons")
        and not plan.get("relations_remove")
    ):
        raise HTTPException(status_code=400, detail="无有效整理方案")

    conn = get_db()
    c = conn.cursor()
    family_row = c.execute("SELECT id FROM families WHERE id = ?", (family_id,)).fetchone()
    if not family_row:
        conn.close()
        raise HTTPException(status_code=404, detail="Family not found")

    persons_rows = c.execute("SELECT * FROM persons WHERE family_id = ?", (family_id,)).fetchall()
    rel_rows = c.execute("SELECT * FROM relations WHERE family_id = ?", (family_id,)).fetchall()
    conn.close()

    id_to_name = {r["id"]: r["name"] for r in persons_rows}
    persons = [row_to_person(r) for r in persons_rows]
    relations = []
    for r in rel_rows:
        fn = id_to_name.get(r["from_person_id"])
        tn = id_to_name.get(r["to_person_id"])
        if fn and tn:
            relations.append({
                "from": fn,
                "to": tn,
                "type": r["relation_type"] or "parent_child",
                "status": r.get("status") or "confirmed",
            })

    plan = reconcile_plan_with_genealogy(plan, persons)
    use_clean = should_use_clean_slate(
        "",
        clean_slate_flag=bool(data.get("clean_slate")),
        plan=plan,
        persons=persons,
    )
    if use_clean or not persons:
        plan["clean_slate"] = True
        use_clean = True

    built = merge_plan_into_genealogy(
        persons, relations, plan,
        clean_slate=use_clean,
    )
    diff = compute_organize_diff(persons, relations, plan, built)
    return {"success": True, "plan": plan, "diff": diff}


@app.post("/api/families/{family_id}/ai-organize")
async def ai_organize_family(family_id: str, data: dict):
    """对话式 AI 整理主谱：理解用户指令，返回方案与预览；可选 persist 入库。"""
    persist = bool(data.get("persist"))
    plan_input = data.get("plan")

    if persist and plan_input:
        conn = get_db()
        c = conn.cursor()
        try:
            family_row = c.execute("SELECT id FROM families WHERE id = ?", (family_id,)).fetchone()
            if not family_row:
                raise HTTPException(status_code=404, detail="Family not found")
            persons_rows = c.execute("SELECT * FROM persons WHERE family_id = ?", (family_id,)).fetchall()
            now = datetime.now().isoformat()
            apply_mode = (data.get("apply_mode") or "merge").strip().lower()
            if apply_mode not in ("merge", "replace"):
                apply_mode = "merge"
            normalized_plan = reconcile_plan_with_genealogy(
                _normalize_plan(plan_input),
                [dict(r) for r in persons_rows],
            )
            if normalized_plan.get("clean_slate"):
                apply_mode = "replace"
            apply_diff = data.get("diff")
            if apply_mode == "replace" and not apply_diff:
                persons_list = [row_to_person(r) for r in persons_rows]
                rel_named = _fetch_family_relations_named(c, family_id, persons_rows)
                use_clean = bool(normalized_plan.get("clean_slate") or not persons_list)
                built = merge_plan_into_genealogy(
                    persons_list,
                    rel_named,
                    normalized_plan,
                    clean_slate=use_clean,
                )
                apply_diff = compute_organize_diff(persons_list, rel_named, normalized_plan, built)
            apply_stats = _apply_organize_plan(
                c, family_id, normalized_plan,
                [dict(r) for r in persons_rows], now,
                apply_mode=apply_mode,
                diff=apply_diff,
            )
            conn.commit()
            return {
                "success": True,
                "applied": apply_stats,
                "explanation": plan_input.get("explanation", "已应用整理方案"),
            }
        except sqlite3.OperationalError as exc:
            conn.rollback()
            if "locked" in str(exc).lower():
                raise HTTPException(
                    status_code=503,
                    detail="数据库繁忙，请关闭多余的后端进程后重试（仅保留一个 python main.py）",
                ) from exc
            raise HTTPException(status_code=500, detail=f"数据库错误：{exc}") from exc
        finally:
            conn.close()

    message = (data.get("message") or "").strip()
    if not message:
        raise HTTPException(status_code=400, detail="请输入整理指令")

    refresh_context = bool(data.get("refresh_context"))
    clear_session_flag = bool(data.get("clear_session"))
    session_id = (data.get("session_id") or "").strip() or None

    if clear_session_flag and session_id:
        clear_organize_session(session_id, family_id)
        session_id = None

    session = get_organize_session(session_id, family_id) if session_id else None
    if not session:
        session_id = create_organize_session(family_id)
        session = get_organize_session(session_id, family_id)
        refresh_context = True

    context_mode = resolve_context_mode(session, refresh_context=refresh_context)

    conn = get_db()
    c = conn.cursor()
    family_row = c.execute("SELECT * FROM families WHERE id = ?", (family_id,)).fetchone()
    if not family_row:
        conn.close()
        raise HTTPException(status_code=404, detail="Family not found")

    family = dict(family_row)
    persons_rows = c.execute("SELECT * FROM persons WHERE family_id = ?", (family_id,)).fetchall()
    rel_rows = c.execute("SELECT * FROM relations WHERE family_id = ?", (family_id,)).fetchall()

    source_version = None
    if data.get("include_source") is False:
        source_text = ""
    else:
        version_id = data.get("source_version_id")
        if version_id:
            source_version = get_source_version(c, family_id, version_id)
            source_text = (source_version.get("source_text") or "").strip() if source_version else ""
        else:
            source_text = (data.get("source_text") or "").strip()
        if not source_text:
            source_text, source_version = get_active_source_for_family(c, family_id)
            source_text = (source_text or "").strip()
        if not source_text:
            source_text = (family.get("source_text") or "").strip()

    # 摘要模式：默认不再附带长原文，除非首轮/强制刷新/用户显式附带
    include_source_this_turn = bool(data.get("include_source"))
    if context_mode == "summary" and not refresh_context and not include_source_this_turn:
        source_text = ""
    elif context_mode == "summary" and session and session.get("source_included_once") and not include_source_this_turn:
        source_text = ""

    conn.close()

    persons = [row_to_person(r) for r in persons_rows]
    relations = [dict(r) for r in rel_rows]

    # 与 OCR「关系解析」一致：始终使用设置里保存的解析模型，不用前端默认 minimax 覆盖
    parse_cfg = load_model_selection()["parse"]
    parse_provider, parse_model = parse_cfg["provider"], parse_cfg["model"]
    ai_configured = _is_provider_configured(parse_provider)

    async def ai_fn(prompt: str):
        return await call_text_model(parse_provider, parse_model, prompt, max_tokens=4096)

    result = await organize_genealogy_with_chat(
        persons,
        relations,
        message,
        ai_fn,
        source_text=source_text,
        history=data.get("history") or [],
        style=data.get("style", "su"),
        ai_configured=ai_configured,
        context_mode=context_mode,
        session_summary=(session or {}).get("summary", ""),
        last_explanation=(session or {}).get("last_explanation", ""),
        clean_slate=bool(data.get("clean_slate")),
    )

    if result.get("success") and session_id:
        touch_organize_session(
            session_id,
            persons=persons,
            relations=relations,
            explanation=result.get("explanation", ""),
            source_included=bool(source_text),
        )
        session = get_organize_session(session_id, family_id) or session

    if not result.get("success"):
        result["parse"] = {"provider": parse_provider, "model": parse_model}
        return result

    preview = result.get("preview") or {}
    response = {
        "success": True,
        "used_ai": result.get("used_ai", False),
        "explanation": result.get("explanation", ""),
        "plan": result.get("plan"),
        "stats": preview.get("stats"),
        "parse": {"provider": parse_provider, "model": parse_model},
        "tree_preview": {
            "nodes": (preview.get("tree") or {}).get("nodes", [])[:40],
            "person_count": preview.get("stats", {}).get("person_count"),
            "relation_count": preview.get("stats", {}).get("relation_count"),
        },
        "warning": result.get("warning") or "",
        "fallback": result.get("fallback") or "",
        "source_included": bool(source_text),
        "source_length": len(source_text),
        "source_version": {
            "id": source_version.get("id"),
            "label": source_version.get("label"),
            "version_no": source_version.get("version_no"),
            "status": source_version.get("status"),
        } if source_version else None,
        "diff": result.get("diff"),
        "agent": {
            "session_id": session_id,
            "context_mode": result.get("context_mode") or context_mode,
            "turn_count": (session or {}).get("turn_count", 0),
            "summary": (session or {}).get("summary", ""),
        },
    }

    if data.get("persist") and result.get("plan"):
        conn = get_db()
        c = conn.cursor()
        now = datetime.now().isoformat()
        apply_mode = (data.get("apply_mode") or "merge").strip().lower()
        if apply_mode not in ("merge", "replace"):
            apply_mode = "merge"
        apply_stats = _apply_organize_plan(
            c, family_id, result["plan"],
            [dict(r) for r in persons_rows], now,
            apply_mode=apply_mode,
            diff=result.get("diff"),
        )
        conn.commit()
        conn.close()
        response["applied"] = apply_stats

    return response


@app.delete("/api/families/{family_id}/ai-organize/session")
async def clear_ai_organize_session(family_id: str, session_id: str | None = Query(default=None)):
    """清空整理智能体会话缓存。"""
    cleared = False
    if session_id:
        cleared = clear_organize_session(session_id, family_id)
    else:
        from agent.organize_session import clear_family_organize_sessions
        clear_family_organize_sessions(family_id)
        cleared = True
    return {"success": True, "cleared": cleared}


@app.post("/api/agent/validate")
async def agent_validate(data: dict):
    """校验成员与关系数据（不依赖 AI）"""
    persons = data.get("persons", [])
    relations = data.get("relations", [])
    pv = validate_genealogy_with_generations(persons, relations)
    rv = validate_relations(persons, relations)
    return {
        "success": True,
        "valid": pv["valid"] and rv["valid"],
        "persons": pv,
        "relations": rv,
        "generation_issues": [i for i in pv.get("issues", []) if i.get("field") in ("generation", "birth_year")],
    }


@app.post("/api/agent/scan")
async def agent_scan(data: dict):
    """扫描建谱流水线：OCR → 解析 → 校验"""
    image_base64 = data.get("image")
    ocr_provider, ocr_model = resolve_task_model(data, "ocr")
    parse_provider, parse_model = resolve_task_model(data, "parse")

    async def ocr_fn(provider, model, img, prompt):
        return await call_vision_model(provider, model, img, prompt)

    async def parse_fn(provider, model, prompt):
        return await call_text_model(provider, model, prompt)

    return await run_scan_pipeline(
        image_base64,
        ocr_provider=ocr_provider,
        ocr_model=ocr_model,
        parse_provider=parse_provider,
        parse_model=parse_model,
        ocr_fn=ocr_fn,
        parse_fn=parse_fn,
    )


# ==================== OCR API ====================

@app.post("/api/ocr/recognize")
async def ocr_recognize(data: dict):
    """OCR文字识别"""
    image_base64 = data.get("image")
    if not image_base64:
        raise HTTPException(status_code=400, detail="Missing image data")

    try:
        image_data = base64.b64decode(image_base64)
        filename = f"{uuid.uuid4().hex}.jpg"
        filepath = os.path.join(UPLOAD_DIR, filename)
        with open(filepath, "wb") as f:
            f.write(image_data)

        ocr_provider, ocr_model = resolve_task_model(data, "ocr")
        prompt = "请识别这张族谱图片中的所有文字，保持原有格式，识别所有人的姓名、生卒年、世代等信息。"

        recognized_text, ocr_error = await call_vision_model(ocr_provider, ocr_model, image_base64, prompt)

        if ocr_error:
            return {
                "success": False,
                "error": ocr_error,
                "provider": ocr_provider,
                "model": ocr_model,
            }

        return {
            "success": True,
            "text": recognized_text.strip(),
            "image_path": filename,
            "provider": ocr_provider,
            "model": ocr_model,
            "is_demo": False,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/ocr/extract-names")
async def ocr_extract_names(data: dict):
    """从 OCR/粘贴文字中 AI+规则识别人名，返回可标注位置。"""
    from agent.name_extractor import extract_names_from_full_text, find_name_occurrences

    text = (data.get("text") or "").strip()
    if not text:
        return {"success": True, "annotations": [], "names": []}

    names = extract_names_from_full_text(text)
    occurrences = find_name_occurrences(text, names)
    annotations = [
        {
            "id": f"{o['start']}-{o['end']}-{o['name']}",
            "name": o["name"],
            "start": o["start"],
            "end": o["end"],
            "source": "ai",
        }
        for o in occurrences
    ]
    return {
        "success": True,
        "names": names,
        "annotations": annotations,
        "count": len(annotations),
    }


@app.post("/api/ocr/parse")
async def ocr_parse(data: dict):
    """AI 两阶段解析族谱文字：关系描述稿 → 数字化 JSON"""
    raw_text = (data.get("text") or "").strip()

    if not raw_text:
        return {"success": True, "persons": [], "relations": [], "relation_description": ""}

    parse_provider, parse_model = resolve_task_model(data, "parse")
    skip_describe = bool(data.get("skip_describe"))

    async def parse_fn(prompt: str) -> tuple[str, str]:
        return await call_text_model(parse_provider, parse_model, prompt, max_tokens=8192)

    parsed = await run_two_stage_genealogy_parse(
        raw_text,
        parse_fn,
        skip_describe=skip_describe,
    )

    out = {
        "success": parsed.get("success", True),
        "persons": parsed.get("persons", []),
        "relations": parsed.get("relations", []),
        "tree_preview": parsed.get("tree_preview"),
        "genealogy_stats": parsed.get("genealogy_stats"),
        "relation_description": parsed.get("relation_description", ""),
        "relation_text_used": parsed.get("relation_text_used", raw_text),
        "provider": parse_provider,
        "model": parse_model,
        "used_ai": parsed.get("used_ai_digitize", False),
        "used_ai_describe": parsed.get("used_ai_describe", False),
        "parse_steps": parsed.get("parse_steps", []),
        "validation": parsed.get("validation"),
    }
    if parsed.get("warning"):
        out["warning"] = parsed["warning"]
    return out

# ==================== 导出/导入 ====================

@app.get("/api/families/{family_id}/export")
async def export_family(family_id: str):
    conn = get_db()
    c = conn.cursor()
    family = c.execute("SELECT * FROM families WHERE id = ?", (family_id,)).fetchone()
    persons = c.execute("SELECT * FROM persons WHERE family_id = ?", (family_id,)).fetchall()
    relations = c.execute("SELECT * FROM relations WHERE family_id = ?", (family_id,)).fetchall()
    conn.close()
    return {
        "family": dict(family) if family else None,
        "persons": [dict(p) for p in persons],
        "relations": [dict(r) for r in relations],
        "exported_at": datetime.now().isoformat()
    }

@app.post("/api/import")
async def import_family(data: dict):
    family = data.get("family")
    persons = data.get("persons", [])
    relations = data.get("relations", [])

    if not family:
        raise HTTPException(status_code=400, detail="Missing family data")

    conn = get_db()
    c = conn.cursor()
    fid = str(uuid.uuid4())[:8]
    now = datetime.now().isoformat()

    c.execute("INSERT INTO families (id, name, surname, description, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
              (fid, family.get("name"), family.get("surname"), family.get("description"), now, now))

    id_map = {}
    for p in persons:
        pid = str(uuid.uuid4())[:8]
        id_map[p.get("id", pid)] = pid
        c.execute("""INSERT INTO persons (id, family_id, name, gender, birth_year, death_year, generation,
            generation_name, generation_prefix, parent_id, status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (pid, fid, p.get("name"), p.get("gender"), p.get("birth_year"), p.get("death_year"),
             p.get("generation"), p.get("generation_name"), p.get("generation_prefix"),
             p.get("parent_id"), p.get("status", "confirmed"), now))

    for r in relations:
        rid = str(uuid.uuid4())[:8]
        c.execute("""INSERT INTO relations (id, family_id, from_person_id, to_person_id, relation_type, created_at)
            VALUES (?, ?, ?, ?, ?, ?)""",
            (rid, fid, id_map.get(r.get("from_person_id")), id_map.get(r.get("to_person_id")),
             r.get("relation_type"), now))

    conn.commit()
    conn.close()
    return {"id": fid, "success": True}

# 静态文件
dist_path = os.path.join(os.path.dirname(__file__), "../dist")
if os.path.exists(dist_path):
    from fastapi.staticfiles import StaticFiles
    app.mount("/", StaticFiles(directory=dist_path, html=True), name="static")

if __name__ == "__main__":
    import sys
    import uvicorn

    # Windows 下 reload 易残留多进程并锁死 SQLite，默认关闭；需热重载时：set DEV_RELOAD=1
    use_reload = os.environ.get("DEV_RELOAD") == "1" and sys.platform != "win32"
    if sys.platform == "win32" and os.environ.get("DEV_RELOAD") == "1":
        print("提示：Windows 不建议 DEV_RELOAD=1，易导致 8080 多进程与数据库锁死")
    uvicorn.run("main:app", host="0.0.0.0", port=8080, reload=use_reload)