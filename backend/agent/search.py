"""族谱成员搜索（关键词，MVP）"""

from __future__ import annotations

from typing import Any


def search_persons(persons: list[dict[str, Any]], query: str, *, limit: int = 50) -> list[dict]:
    q = (query or "").strip().lower()
    if not q:
        return []

    results = []
    for p in persons:
        name = (p.get("name") or "").lower()
        gen_name = (p.get("generation_name") or "").lower()
        gen = str(p.get("generation") or "")
        birth = str(p.get("birth_year") or "")
        death = str(p.get("death_year") or "")

        matched = (
            q in name
            or q in gen_name
            or q == gen
            or q in birth
            or q in death
        )
        if matched:
            results.append({
                "id": p.get("id"),
                "name": p.get("name"),
                "gender": p.get("gender"),
                "generation": p.get("generation"),
                "generation_name": p.get("generation_name"),
                "birth_year": p.get("birth_year"),
                "death_year": p.get("death_year"),
                "match_reason": _match_reason(q, p),
            })
        if len(results) >= limit:
            break
    return results


def _match_reason(q: str, person: dict) -> str:
    if q in (person.get("name") or "").lower():
        return "姓名匹配"
    if q in (person.get("generation_name") or "").lower():
        return "字号匹配"
    if q == str(person.get("generation") or ""):
        return "世代匹配"
    return "信息匹配"
