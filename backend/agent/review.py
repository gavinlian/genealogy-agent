"""扫描校正：为待确认字段打标"""

from __future__ import annotations

from typing import Any


def annotate_persons_for_review(
    persons: list[dict[str, Any]],
    validation: dict | None = None,
) -> list[dict[str, Any]]:
    """给每位成员附加 _review_flags，供校正页高亮"""
    issue_by_name: dict[str, list[dict]] = {}
    for issue in (validation or {}).get("issues", []):
        name = issue.get("person")
        if name:
            issue_by_name.setdefault(name, []).append(issue)

    annotated = []
    for p in persons:
        copy = dict(p)
        flags: list[dict] = []
        name = copy.get("name") or ""

        if not copy.get("name"):
            flags.append({"field": "name", "level": "error", "message": "缺少姓名"})
        if copy.get("gender") in (None, "", "unknown"):
            flags.append({"field": "gender", "level": "warning", "message": "性别未确认"})
        if not copy.get("birth_year"):
            flags.append({"field": "birth_year", "level": "warning", "message": "缺生年"})
        if not copy.get("generation"):
            flags.append({"field": "generation", "level": "warning", "message": "缺世代"})

        for issue in issue_by_name.get(name, []):
            flags.append({
                "field": issue.get("field", ""),
                "level": issue.get("level", "warning"),
                "message": issue.get("message", ""),
            })

        copy["_review_flags"] = flags
        copy["review_status"] = "pending_review" if any(f["level"] == "error" for f in flags) else (
            "needs_review" if flags else "confirmed"
        )
        conf = copy.get("ai_confidence")
        if conf is None:
            conf = 0.6 if flags else 0.9
        if flags and conf > 0.75:
            conf = 0.75
        copy["ai_confidence"] = conf
        if conf < 0.55 and name:
            flags.append({"field": "name", "level": "warning", "message": "人名置信度偏低，请核对"})
        annotated.append(copy)
    return annotated


def annotate_relations_for_review(
    relations: list[dict],
    relation_validation: dict | None = None,
) -> list[dict]:
    result = []
    for rel in relations:
        copy = dict(rel)
        copy["status"] = copy.get("status") or "inferred"
        copy["confidence"] = copy.get("confidence") or 0.75
        result.append(copy)
    if relation_validation and not relation_validation.get("valid"):
        for issue in relation_validation.get("issues", []):
            result.append({
                "from": "",
                "to": "",
                "type": "parent_child",
                "status": "disputed",
                "confidence": 0.3,
                "_issue": issue.get("message"),
            })
    return result
