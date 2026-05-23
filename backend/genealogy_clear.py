"""清空族谱主谱数据（保留族谱记录与原文版本）。"""

from __future__ import annotations

from datetime import datetime


def collect_branch_person_ids(cursor, family_id: str, root_person_id: str) -> set[str]:
    """选中成员及其全部后代（不含配偶旁支）。"""
    rows = cursor.execute(
        "SELECT id, parent_id FROM persons WHERE family_id = ?",
        (family_id,),
    ).fetchall()
    valid_ids = {r["id"] for r in rows}
    if root_person_id not in valid_ids:
        return set()

    parent_to_children: dict[str, list[str]] = {}
    for row in rows:
        parent_id = row["parent_id"]
        if parent_id and parent_id in valid_ids:
            parent_to_children.setdefault(parent_id, []).append(row["id"])

    rel_rows = cursor.execute(
        """SELECT from_person_id, to_person_id FROM relations
           WHERE family_id = ? AND relation_type = 'parent_child'""",
        (family_id,),
    ).fetchall()
    for row in rel_rows:
        parent_id = row["from_person_id"]
        child_id = row["to_person_id"]
        if parent_id in valid_ids and child_id in valid_ids:
            parent_to_children.setdefault(parent_id, []).append(child_id)

    branch: set[str] = set()
    queue = [root_person_id]
    while queue:
        current = queue.pop()
        if current in branch:
            continue
        branch.add(current)
        for child_id in parent_to_children.get(current, []):
            if child_id not in branch:
                queue.append(child_id)
    return branch


def clear_family_genealogy(
    cursor,
    family_id: str,
    *,
    scope: str = "all",
    root_person_id: str | None = None,
    now: str | None = None,
) -> dict:
    """
    清空主谱成员与关系，保留 families 与原文版本。
    scope: all=整谱；branch=选中成员及其后代。
    """
    scope = (scope or "all").strip().lower()
    if scope not in ("all", "branch"):
        raise ValueError("scope 只能是 all 或 branch")
    if scope == "branch" and not root_person_id:
        raise ValueError("清空分支需指定 root_person_id")

    ts = now or datetime.now().isoformat()
    person_rows = cursor.execute(
        "SELECT id FROM persons WHERE family_id = ?",
        (family_id,),
    ).fetchall()
    all_ids = {r["id"] for r in person_rows}

    if scope == "all":
        target_ids = all_ids
    else:
        target_ids = collect_branch_person_ids(cursor, family_id, root_person_id or "")
        if not target_ids:
            return {
                "scope": scope,
                "persons_removed": 0,
                "relations_removed": 0,
            }

    relations_removed = 0
    if target_ids:
        placeholders = ",".join("?" for _ in target_ids)
        rel_rows = cursor.execute(
            f"""SELECT id FROM relations
                WHERE family_id = ?
                  AND (from_person_id IN ({placeholders}) OR to_person_id IN ({placeholders}))""",
            (family_id, *target_ids, *target_ids),
        ).fetchall()
        for row in rel_rows:
            cursor.execute("DELETE FROM relations WHERE id = ?", (row["id"],))
            relations_removed += 1

        for pid in target_ids:
            cursor.execute(
                "UPDATE persons SET parent_id = NULL WHERE parent_id = ? AND family_id = ?",
                (pid, family_id),
            )

        persons_removed = 0
        for pid in target_ids:
            cursor.execute("DELETE FROM persons WHERE id = ? AND family_id = ?", (pid, family_id))
            if cursor.rowcount:
                persons_removed += 1
    else:
        persons_removed = 0

    family_row = cursor.execute(
        "SELECT root_person_id FROM families WHERE id = ?",
        (family_id,),
    ).fetchone()
    updates: dict[str, object] = {"updated_at": ts}
    if family_row and family_row["root_person_id"] in target_ids:
        updates["root_person_id"] = None

    if scope == "all":
        cursor.execute(
            "UPDATE families SET root_person_id = NULL, updated_at = ? WHERE id = ?",
            (ts, family_id),
        )
    elif updates.get("root_person_id") is None:
        cursor.execute(
            "UPDATE families SET root_person_id = NULL, updated_at = ? WHERE id = ?",
            (ts, family_id),
        )
    else:
        cursor.execute(
            "UPDATE families SET updated_at = ? WHERE id = ?",
            (ts, family_id),
        )

    return {
        "scope": scope,
        "root_person_id": root_person_id if scope == "branch" else None,
        "persons_removed": persons_removed,
        "relations_removed": relations_removed,
    }
