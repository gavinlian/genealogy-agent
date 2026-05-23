"""族谱搜索：关键词 + 规则化自然语言（无 AI 也能用）"""

from __future__ import annotations

import re
from typing import Any

from .search import search_persons


def rule_based_nl_search(persons: list[dict], query: str) -> list[dict]:
    """解析常见中文族谱问法，不依赖大模型"""
    q = (query or "").strip()
    if not q:
        return []

    # 「张三的弟弟」「李四的父亲」
    m = re.match(r"^(.+?)的(父亲|母亲|儿子|女儿|兄弟|姐妹|配偶|妻子|丈夫)$", q)
    if m:
        return _kinship_search(persons, m.group(1).strip(), m.group(2))

    # 「第12代」
    gm = re.search(r"第\s*(\d+)\s*代", q)
    if gm:
        gen = int(gm.group(1))
        return [
            {
                **{k: p.get(k) for k in ("id", "name", "gender", "generation", "generation_name", "birth_year", "death_year")},
                "match_reason": f"第{gen}代成员",
            }
            for p in persons
            if p.get("generation") == gen
        ]

    return search_persons(persons, q)


def _kinship_search(persons: list[dict], anchor_name: str, kin: str) -> list[dict]:
    by_name = {p.get("name"): p for p in persons if p.get("name")}
    anchor = by_name.get(anchor_name)
    if not anchor:
        return []

    aid = anchor.get("id")
    results = []
    kin = kin.replace("妻子", "配偶").replace("丈夫", "配偶")

    if kin in ("父亲", "母亲"):
        pid = anchor.get("parent_id")
        if pid:
            parent = next((p for p in persons if p.get("id") == pid), None)
            if parent:
                results.append(_wrap(parent, f"{anchor_name}的{kin}"))
    elif kin in ("儿子", "女儿", "子女"):
        for p in persons:
            if p.get("parent_id") == aid:
                g = p.get("gender") or "unknown"
                if kin == "子女":
                    results.append(_wrap(p, f"{anchor_name}的{kin}"))
                elif kin == "儿子" and g in ("male", "unknown"):
                    results.append(_wrap(p, f"{anchor_name}的{kin}"))
                elif kin == "女儿" and g in ("female", "unknown"):
                    results.append(_wrap(p, f"{anchor_name}的{kin}"))
    elif kin in ("兄弟", "姐妹", "兄弟姐妹"):
        parent_id = anchor.get("parent_id")
        if parent_id:
            for p in persons:
                if p.get("parent_id") == parent_id and p.get("id") != aid:
                    results.append(_wrap(p, f"{anchor_name}的{kin}"))

    return results


def _wrap(person: dict, reason: str) -> dict:
    return {
        "id": person.get("id"),
        "name": person.get("name"),
        "gender": person.get("gender"),
        "generation": person.get("generation"),
        "generation_name": person.get("generation_name"),
        "birth_year": person.get("birth_year"),
        "death_year": person.get("death_year"),
        "match_reason": reason,
    }


async def nl_search_with_ai(
    persons: list[dict],
    relations: list[dict],
    query: str,
    ai_fn,
) -> tuple[list[dict], str]:
    """
    优先 AI 解析查询意图，失败则规则搜索。
    ai_fn(prompt) -> (text, error)
    """
    names = [p.get("name") for p in persons if p.get("name")][:80]
    prompt = f"""你是族谱搜索助手。用户问：{query}

族谱成员姓名列表：{', '.join(names)}

请从列表中找出最匹配的人名，只返回 JSON：
{{"names": ["姓名1"], "explanation": "一句话说明"}}

只返回 JSON。"""

    text, err = await ai_fn(prompt)
    if text:
        import json
        from .parser import extract_json_content
        parsed = extract_json_content(text)
        if parsed and parsed.get("names"):
            name_set = set(parsed["names"])
            hits = [p for p in persons if p.get("name") in name_set]
            return [
                {**_wrap(p, parsed.get("explanation", "AI 匹配")), "match_reason": "AI 搜索"}
                for p in hits
            ], ""

    return rule_based_nl_search(persons, query), err or ""
