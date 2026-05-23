"""族谱文字本地解析（无 AI 降级）"""

import json
import re


def _strip_llm_wrappers(text: str) -> str:
    text = re.sub(r"\x3cthink\x3e[\s\S]*?\x3c/think\x3e", "", text, flags=re.IGNORECASE)
    text = re.sub(r"```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    return text.replace("```", "").strip()


def _repair_json_text(text: str) -> str:
    text = re.sub(r"//[^\n]*", "", text)
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    text = re.sub(r",\s*([}\]])", r"\1", text)
    text = re.sub(r"\bNone\b", "null", text)
    text = re.sub(r"\bTrue\b", "true", text)
    text = re.sub(r"\bFalse\b", "false", text)
    return text.strip()


def _extract_json_brace_block(text: str) -> str | None:
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


def _extract_all_json_blocks(text: str) -> list[str]:
    blocks: list[str] = []
    pos = 0
    while pos < len(text):
        idx = text.find("{", pos)
        if idx < 0:
            break
        block = _extract_json_brace_block(text[idx:])
        if block:
            blocks.append(block)
            pos = idx + max(len(block), 1)
        else:
            pos = idx + 1
    return blocks


def _try_load_json(candidate: str):
    if not candidate:
        return None
    for variant in (candidate, _repair_json_text(candidate)):
        try:
            return json.loads(variant)
        except json.JSONDecodeError:
            continue
    return None


def extract_json_content(content: str):
    if not content:
        return None
    text = _strip_llm_wrappers(content.strip())
    candidates: list[str] = []

    if "```json" in content:
        candidates.append(content.split("```json", 1)[1].split("```", 1)[0].strip())
    elif "```" in content:
        for part in content.split("```"):
            part = part.strip()
            if part.startswith("{"):
                candidates.append(part)

    candidates.append(text)
    for block in _extract_all_json_blocks(text):
        candidates.append(block)
    for block in _extract_all_json_blocks(content):
        candidates.append(block)

    seen: set[str] = set()
    best_dict = None
    best_score = -1
    organize_keys = {
        "explanation", "relations_add", "relations_remove", "person_updates",
        "new_persons", "persons", "relations", "plan",
    }

    for candidate in candidates:
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        loaded = _try_load_json(candidate)
        if loaded is None:
            continue
        if isinstance(loaded, dict):
            score = sum(1 for key in organize_keys if key in loaded)
            if score > best_score:
                best_score = score
                best_dict = loaded
        elif best_dict is None:
            best_dict = loaded

    return best_dict


def parse_genealogy_text(text: str) -> dict:
    """从族谱纯文本提取人物与关系（规则引擎，委托增强解析）"""
    from .genealogy_builder import parse_genealogy_text_enhanced

    return parse_genealogy_text_enhanced(text)
