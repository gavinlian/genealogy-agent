"""
代际起点与计算引擎 — 以始祖为第1代，沿父子链递增；支持隔代称谓与空缺占位。
"""

from __future__ import annotations

from typing import Any

# 相对始祖/锚点人物的代际偏移（本人相对锚点的世代差）
KINSHIP_GENERATION_OFFSET: dict[str, int] = {
    "本人": 0,
    "配偶": 0,
    "兄弟": 0,
    "姐妹": 0,
    "子": 1,
    "儿子": 1,
    "女儿": 1,
    "女": 1,
    "孙子": 2,
    "孙": 2,
    "孙女": 2,
    "曾孙": 3,
    "曾孙女": 3,
    "玄孙": 4,
    "来孙": 5,
}

# 关系子类型（宗法标注）
RELATION_SUBTYPES = frozenset({
    "birth",           # 亲生
    "adopted",         # 过继/嗣子
    "dual_inheritance",  # 兼祧
    "step",            # 继配子女
})


def normalize_kinship(label: str) -> str:
    s = (label or "").strip().replace(" ", "")
    for key in sorted(KINSHIP_GENERATION_OFFSET.keys(), key=len, reverse=True):
        if key in s or s == key:
            return key
    return s


def kinship_generation_delta(kinship: str) -> int | None:
    key = normalize_kinship(kinship)
    return KINSHIP_GENERATION_OFFSET.get(key)


def build_parent_map(
    persons: list[dict],
    relations: list[dict] | None = None,
) -> dict[str, str]:
    """child_id -> parent_id"""
    parent_map: dict[str, str] = {}
    for rel in relations or []:
        rtype = rel.get("relation_type") or rel.get("type")
        if rtype != "parent_child":
            continue
        parent = rel.get("from_person_id") or rel.get("from")
        child = rel.get("to_person_id") or rel.get("to")
        if parent and child:
            parent_map[str(child)] = str(parent)
    by_id = {str(p["id"]): p for p in persons if p.get("id")}
    for pid, p in by_id.items():
        if p.get("parent_id"):
            parent_map[pid] = str(p["parent_id"])
    return parent_map


def resolve_root_person_id(
    persons: list[dict],
    parent_map: dict[str, str],
    preferred_root_id: str | None = None,
) -> str | None:
    if preferred_root_id and any(str(p.get("id")) == str(preferred_root_id) for p in persons):
        return str(preferred_root_id)
    child_ids = set(parent_map.keys())
    roots = [str(p["id"]) for p in persons if p.get("id") and str(p["id"]) not in child_ids]
    if len(roots) == 1:
        return roots[0]
    if roots:
        # 多个根：取世代最小者
        root_persons = [p for p in persons if str(p.get("id")) in roots]
        root_persons.sort(key=lambda x: (x.get("generation") or 999, x.get("name") or ""))
        return str(root_persons[0]["id"])
    if persons:
        sorted_p = sorted(persons, key=lambda x: (x.get("generation") or 999, x.get("name") or ""))
        return str(sorted_p[0]["id"]) if sorted_p[0].get("id") else None
    return None


def depth_from_root(person_id: str, root_id: str, parent_map: dict[str, str]) -> int | None:
    """从始祖沿父链向上，计算深度（始祖=0）。"""
    if person_id == root_id:
        return 0
    depth = 0
    cur = person_id
    seen: set[str] = set()
    while cur and cur != root_id:
        if cur in seen:
            return None
        seen.add(cur)
        parent = parent_map.get(cur)
        if not parent:
            return None
        depth += 1
        cur = parent
    return depth if cur == root_id else None


def recalculate_generations(
    persons: list[dict],
    relations: list[dict] | None = None,
    *,
    root_person_id: str | None = None,
    start_generation: int = 1,
) -> dict[str, Any]:
    """
    以 root 为第 start_generation 代，按父子链重算所有成员 generation。
    返回 {persons, root_person_id, start_generation, unresolved_ids}
    """
    if not persons:
        return {
            "persons": [],
            "root_person_id": root_person_id,
            "start_generation": start_generation,
            "unresolved_ids": [],
        }

    start_generation = max(1, int(start_generation or 1))
    parent_map = build_parent_map(persons, relations)
    root_id = resolve_root_person_id(persons, parent_map, root_person_id)
    unresolved: list[str] = []

    updated: list[dict] = []
    for p in persons:
        copy = dict(p)
        pid = str(copy.get("id") or "")
        if not pid or not root_id:
            unresolved.append(pid)
            updated.append(copy)
            continue
        depth = depth_from_root(pid, root_id, parent_map)
        if depth is None:
            # 无法连到始祖：保留原世代或按 start 兜底
            if not copy.get("generation"):
                copy["generation"] = start_generation
            unresolved.append(pid)
        else:
            copy["generation"] = start_generation + depth
        updated.append(copy)

    return {
        "persons": updated,
        "root_person_id": root_id,
        "start_generation": start_generation,
        "unresolved_ids": unresolved,
    }


def build_placeholder_name(generation: int) -> str:
    return f"（待补）第{generation}代"


def ensure_ancestor_chain(
    persons: list[dict],
    relations: list[dict],
    anchor_id: str,
    target_generation: int,
    *,
    start_generation: int = 1,
) -> tuple[list[dict], list[dict], str | None]:
    """
    从 anchor 到 target_generation 之间补全占位祖先（仅数据层）。
    返回 (new_persons, new_relations, leaf_parent_id) — 新成员应挂在 leaf_parent_id 下。
    """
    by_id = {str(p["id"]): dict(p) for p in persons if p.get("id")}
    anchor = by_id.get(str(anchor_id))
    if not anchor:
        return persons, relations, None

    anchor_gen = int(anchor.get("generation") or start_generation)
    if target_generation <= anchor_gen:
        return persons, relations, str(anchor_id)

    parent_map = build_parent_map(persons, relations)
    new_persons = list(persons)
    new_relations = list(relations)
    current_id = str(anchor_id)
    current_gen = anchor_gen

    while current_gen < target_generation - 1:
        next_gen = current_gen + 1
        # 是否已有子代可接续
        child_id = None
        for rel in new_relations:
            rtype = rel.get("relation_type") or rel.get("type")
            if rtype != "parent_child":
                continue
            fid = rel.get("from_person_id") or rel.get("from")
            tid = rel.get("to_person_id") or rel.get("to")
            if str(fid) == current_id:
                cand = by_id.get(str(tid)) or next(
                    (p for p in new_persons if str(p.get("id")) == str(tid)), None
                )
                if cand and int(cand.get("generation") or 0) == next_gen:
                    child_id = str(tid)
                    break

        if not child_id:
            import uuid
            child_id = str(uuid.uuid4())[:8]
            placeholder = {
                "id": child_id,
                "name": build_placeholder_name(next_gen),
                "gender": "unknown",
                "generation": next_gen,
                "parent_id": current_id,
                "is_placeholder": True,
                "review_status": "pending_review",
            }
            new_persons.append(placeholder)
            by_id[child_id] = placeholder
            new_relations.append({
                "from_person_id": current_id,
                "to_person_id": child_id,
                "relation_type": "parent_child",
                "type": "parent_child",
                "status": "inferred",
                "relation_subtype": "birth",
                "confidence": 0.5,
            })

        current_id = child_id
        current_gen = next_gen

    return new_persons, new_relations, current_id


def add_person_with_kinship(
    persons: list[dict],
    relations: list[dict],
    anchor_id: str,
    kinship: str,
    person_data: dict,
    *,
    start_generation: int = 1,
) -> dict[str, Any]:
    """按称谓（如曾孙）相对锚点人物添加成员，必要时补占位代际。"""
    delta = kinship_generation_delta(kinship)
    if delta is None:
        return {"success": False, "error": f"无法识别亲属称谓：{kinship}"}

    by_id = {str(p["id"]): p for p in persons if p.get("id")}
    anchor = by_id.get(str(anchor_id))
    if not anchor:
        return {"success": False, "error": "锚点成员不存在"}

    anchor_gen = int(anchor.get("generation") or start_generation)
    target_gen = anchor_gen + delta if delta > 0 else anchor_gen

    if delta == 0 and kinship in ("兄弟", "姐妹", "配偶"):
        parent_id = anchor.get("parent_id")
        target_gen = anchor_gen
    elif delta >= 1:
        persons, relations, parent_id = ensure_ancestor_chain(
            persons, relations, anchor_id, target_gen, start_generation=start_generation
        )
    else:
        parent_id = anchor.get("parent_id")

    new_person = dict(person_data)
    new_person["generation"] = target_gen
    if delta >= 1 and parent_id:
        new_person["parent_id"] = parent_id

    return {
        "success": True,
        "person": new_person,
        "persons": persons,
        "relations": relations,
        "target_generation": target_gen,
        "parent_id": parent_id,
    }


def validate_generation_logic(
    persons: list[dict],
    relations: list[dict] | None = None,
) -> list[dict]:
    """辈分与生年矛盾检测。"""
    issues: list[dict] = []
    by_id = {str(p["id"]): p for p in persons if p.get("id")}
    parent_map = build_parent_map(persons, relations)

    for p in persons:
        name = p.get("name") or "未知"
        pid = str(p.get("id") or "")
        gen = p.get("generation")
        birth = p.get("birth_year")

        parent_id = parent_map.get(pid) or p.get("parent_id")
        if parent_id:
            parent = by_id.get(str(parent_id))
            if parent:
                pgen = parent.get("generation")
                if gen is not None and pgen is not None and int(gen) <= int(pgen):
                    issues.append({
                        "level": "error",
                        "person": name,
                        "field": "generation",
                        "message": f"世代 {gen} 不应小于等于父辈 {parent.get('name')}（第{pgen}代）",
                    })
                pb = parent.get("birth_year")
                if birth is not None and pb is not None:
                    if birth < pb:
                        issues.append({
                            "level": "error",
                            "person": name,
                            "field": "birth_year",
                            "message": f"生年 {birth} 早于父辈 {parent.get('name')}（{pb}）",
                        })
                    elif birth - pb < 12:
                        issues.append({
                            "level": "warning",
                            "person": name,
                            "field": "birth_year",
                            "message": f"与父辈 {parent.get('name')} 年龄差仅 {birth - pb} 岁，请核对",
                        })

        # 祖父级检查（隔代）
        if parent_id and parent_map.get(str(parent_id)):
            gp_id = parent_map.get(str(parent_id))
            gp = by_id.get(str(gp_id)) if gp_id else None
            if gp and birth is not None and gp.get("birth_year") is not None:
                if birth < gp.get("birth_year"):
                    issues.append({
                        "level": "error",
                        "person": name,
                        "field": "birth_year",
                        "message": f"生年 {birth} 早于祖辈 {gp.get('name')}（{gp.get('birth_year')}）",
                    })

    return issues
