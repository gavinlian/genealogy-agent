"""族谱数据校验工具"""

from typing import Any


def validate_genealogy_persons(persons: list[dict[str, Any]]) -> dict:
    """
    校验成员列表，返回 issues 与是否通过。
    规则：生卒年逻辑、合理年份范围、重名提示。
    """
    issues: list[dict] = []
    names_seen: dict[str, int] = {}
    current_year = 2026

    for idx, person in enumerate(persons):
        name = person.get("name") or f"第{idx + 1}人"
        birth = person.get("birth_year")
        death = person.get("death_year")
        generation = person.get("generation")

        if birth is not None and death is not None and birth > death:
            issues.append({
                "level": "error",
                "person": name,
                "field": "birth_year/death_year",
                "message": f"生年 {birth} 晚于卒年 {death}",
            })

        if birth is not None and (birth < 1000 or birth > current_year):
            issues.append({
                "level": "warning",
                "person": name,
                "field": "birth_year",
                "message": f"生年 {birth} 超出常见范围",
            })

        if death is not None and (death < 1000 or death > current_year):
            issues.append({
                "level": "warning",
                "person": name,
                "field": "death_year",
                "message": f"卒年 {death} 超出常见范围",
            })

        if generation is not None and generation < 1:
            issues.append({
                "level": "error",
                "person": name,
                "field": "generation",
                "message": "世代必须大于 0",
            })

        if name in names_seen:
            names_seen[name] += 1
            issues.append({
                "level": "warning",
                "person": name,
                "field": "name",
                "message": f"姓名「{name}」出现 {names_seen[name]} 次，请核对",
            })
        else:
            names_seen[name] = 1

    errors = [i for i in issues if i["level"] == "error"]
    return {
        "valid": len(errors) == 0,
        "issue_count": len(issues),
        "error_count": len(errors),
        "warning_count": len(issues) - len(errors),
        "issues": issues,
    }


def validate_genealogy_with_generations(
    persons: list[dict[str, Any]],
    relations: list[dict] | None = None,
) -> dict:
    """成员校验 + 代际/生年逻辑校验。"""
    base = validate_genealogy_persons(persons)
    from .generation_engine import validate_generation_logic
    gen_issues = validate_generation_logic(persons, relations)
    issues = base.get("issues", []) + gen_issues
    errors = [i for i in issues if i["level"] == "error"]
    return {
        "valid": len(errors) == 0,
        "issue_count": len(issues),
        "error_count": len(errors),
        "warning_count": len(issues) - len(errors),
        "issues": issues,
    }


def validate_relations(persons: list[dict], relations: list[dict]) -> dict:
    """校验关系：父子名必须存在于 persons"""
    issues = []
    names = {p.get("name") for p in persons if p.get("name")}

    for rel in relations:
        from_name = rel.get("from")
        to_name = rel.get("to")
        if from_name and from_name not in names:
            issues.append({
                "level": "error",
                "field": "relations",
                "message": f"关系中的父「{from_name}」不在成员列表",
            })
        if to_name and to_name not in names:
            issues.append({
                "level": "error",
                "field": "relations",
                "message": f"关系中的子「{to_name}」不在成员列表",
            })

    errors = [i for i in issues if i["level"] == "error"]
    return {
        "valid": len(errors) == 0,
        "issues": issues,
    }
