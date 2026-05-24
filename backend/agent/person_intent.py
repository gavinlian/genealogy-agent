"""从自然语言描述提取成员字段（规则层，不依赖 LLM）。"""

from __future__ import annotations

import re
from typing import Any

from agent.name_extractor import is_valid_person_name, normalize_person_name
from agent.source_person_sync import extract_line_profile_fields

PATCHABLE = frozenset({
    "name", "gender", "birth_year", "death_year", "generation", "generation_name",
    "courtesy_name", "art_name", "county", "town", "village", "biography",
})

_CN_NUM = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}


def _parse_chinese_generation(text: str) -> int | None:
    m = re.search(r"第?\s*([0-9一二三四五六七八九十百]+)\s*世", text)
    if not m:
        return None
    token = m.group(1)
    if token.isdigit():
        return int(token)
    if len(token) == 1 and token in _CN_NUM:
        return _CN_NUM[token]
    if token == "十":
        return 10
    if "十" in token:
        parts = token.split("十")
        hi = _CN_NUM.get(parts[0], 1) if parts[0] else 1
        lo = _CN_NUM.get(parts[1], 0) if len(parts) > 1 and parts[1] else 0
        return hi * 10 + lo
    return None


def extract_person_name_from_text(text: str) -> str | None:
    patterns = [
        r"(?:成员|人物|把)?([\u4e00-\u9fff]{2,4})(?:的|，|,|字|号|第|\s|$)",
        r"给([\u4e00-\u9fff]{2,4})(?:改|写|填|补)",
        r"^([\u4e00-\u9fff]{2,4})(?:字|号|，|,|第|\s)",
    ]
    for pat in patterns:
        m = re.search(pat, text)
        if m:
            name = normalize_person_name(m.group(1))
            if name and is_valid_person_name(name):
                return name
    return None


def extract_person_patch_from_text(text: str) -> dict[str, Any]:
    """从用户一段话里提取可写入主谱的字段。"""
    raw = (text or "").strip()
    if not raw:
        return {}

    patch: dict[str, Any] = dict(extract_line_profile_fields(raw))

    gen = _parse_chinese_generation(raw)
    if gen is not None:
        patch["generation"] = gen

    m = re.search(r"(?:改|写|填|设为|叫做|名为)\s*([\u4e00-\u9fff]{2,4})", raw)
    if m and re.search(r"名|姓名|名字", raw):
        name = normalize_person_name(m.group(1))
        if is_valid_person_name(name):
            patch["name"] = name

    if re.search(r"\b男\b|男性|儿子|父亲|丈夫", raw):
        patch["gender"] = "male"
    elif re.search(r"\b女\b|女性|女儿|妻子|母亲", raw):
        patch["gender"] = "female"

    bio_m = re.search(r"(?:简介|传记|生平)[：:]\s*(.+)", raw)
    if bio_m:
        patch["biography"] = bio_m.group(1).strip()[:2000]

    return {k: v for k, v in patch.items() if k in PATCHABLE and v not in (None, "")}


def looks_like_person_update(text: str) -> bool:
    """是否像在描述/修改成员资料（而非单纯提问）。"""
    raw = (text or "").strip()
    if len(raw) < 4:
        return False
    if re.search(r"(?:是什么|叫什么|多少|有没有|查一下|查询|请问|告诉我|是谁的)", raw):
        return False
    patch = extract_person_patch_from_text(raw)
    if not patch:
        return False
    if re.search(r"改|填|补|更新|设为|写入|录入|改成|改为|补充", raw):
        return True
    if re.search(r"字|号|第\s*[\d一二三四五六七八九十]+\s*世|世代|生于|卒于|简介|传记|生平|字辈|籍贯", raw):
        return True
    return False
