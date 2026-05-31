"""跨族谱 / 大库人物匹配与相似度评分。"""

from __future__ import annotations

import re
from typing import Any


def normalize_person_name(name: str) -> str:
    s = (name or "").strip()
    s = re.sub(r"\s+", "", s)
    return s


def person_match_features(person: dict[str, Any], *, default_surname: str = "") -> dict[str, Any]:
    name = normalize_person_name(person.get("name") or "")
    surname = (person.get("surname") or default_surname or (name[:1] if name else "")).strip()
    return {
        "name": name,
        "surname": surname,
        "generation": person.get("generation"),
        "birth_year": person.get("birth_year"),
        "death_year": person.get("death_year"),
        "county": (person.get("county") or "").strip(),
        "town": (person.get("town") or "").strip(),
        "courtesy_name": (person.get("courtesy_name") or "").strip(),
        "gender": person.get("gender") or "unknown",
    }


def _year_close(a: int | None, b: int | None, tolerance: int = 3) -> bool:
    if a is None or b is None:
        return False
    return abs(int(a) - int(b)) <= tolerance


def score_person_match(
    left: dict[str, Any],
    right: dict[str, Any],
    *,
    left_surname: str = "",
    right_surname: str = "",
) -> float:
    """0~1 相似度；同名 + 世代/生卒/籍贯加权。"""
    fa = person_match_features(left, default_surname=left_surname)
    fb = person_match_features(right, default_surname=right_surname)
    if not fa["name"] or not fb["name"]:
        return 0.0
    if fa["name"] == fb["name"]:
        score = 0.72
    elif fa["name"] in fb["name"] or fb["name"] in fa["name"]:
        score = 0.58
    elif fa["surname"] and fa["surname"] == fb["surname"] and len(fa["name"]) >= 2 and len(fb["name"]) >= 2:
        if fa["name"][-1:] == fb["name"][-1:]:
            score = 0.45
        else:
            return 0.0
    else:
        return 0.0

    ga, gb = fa.get("generation"), fb.get("generation")
    if ga is not None and gb is not None:
        if int(ga) == int(gb):
            score += 0.12
        elif abs(int(ga) - int(gb)) == 1:
            score += 0.04
        else:
            score -= 0.08

    if _year_close(fa.get("birth_year"), fb.get("birth_year")):
        score += 0.08
    if _year_close(fa.get("death_year"), fb.get("death_year")):
        score += 0.06
    if fa.get("courtesy_name") and fa["courtesy_name"] == fb.get("courtesy_name"):
        score += 0.1
    if fa.get("county") and fa["county"] == fb.get("county"):
        score += 0.04
    if fa.get("gender") not in ("unknown", "") and fa["gender"] == fb.get("gender"):
        score += 0.03
    return max(0.0, min(1.0, score))


def find_person_matches(
    target_persons: list[dict[str, Any]],
    source_persons: list[dict[str, Any]],
    *,
    target_surname: str = "",
    source_surname: str = "",
    min_confidence: float = 0.62,
    limit: int = 30,
) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    for tp in target_persons:
        tname = normalize_person_name(tp.get("name") or "")
        if not tname:
            continue
        for sp in source_persons:
            sname = normalize_person_name(sp.get("name") or "")
            if not sname:
                continue
            conf = score_person_match(
                tp, sp,
                left_surname=target_surname,
                right_surname=source_surname,
            )
            if conf < min_confidence:
                continue
            matches.append({
                "target_person": tp,
                "source_person": sp,
                "confidence": round(conf, 3),
                "target_name": tname,
                "source_name": sname,
            })
    matches.sort(key=lambda m: m["confidence"], reverse=True)
    return matches[:limit]


def extract_persons_from_archive(archive: dict[str, Any]) -> list[dict[str, Any]]:
    root = archive.get("archive") or archive
    persons = root.get("persons") or []
    out: list[dict[str, Any]] = []
    for p in persons:
        if isinstance(p, dict) and p.get("native"):
            out.append(dict(p["native"]))
        elif isinstance(p, dict):
            out.append(p)
    return out
