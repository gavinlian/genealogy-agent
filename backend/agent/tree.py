"""族谱树构建（苏式 / 欧式 / 宝塔式布局元数据）"""

from __future__ import annotations

from typing import Any


def _index_persons(persons: list[dict[str, Any]]) -> dict[str, dict]:
    return {p["id"]: p for p in persons if p.get("id")}


def _children_map(persons: list[dict], relations: list[dict]) -> dict[str, list[str]]:
    children: dict[str, list[str]] = {}
    for rel in relations:
        if rel.get("relation_type") != "parent_child":
            continue
        parent = rel.get("from_person_id")
        child = rel.get("to_person_id")
        if parent and child:
            children.setdefault(parent, []).append(child)

    for p in persons:
        pid = p.get("id")
        parent_id = p.get("parent_id")
        if pid and parent_id and pid not in children.get(parent_id, []):
            children.setdefault(parent_id, []).append(pid)
    return children


def _find_roots(persons: list[dict], children_map: dict[str, list[str]]) -> list[str]:
    child_ids = {cid for kids in children_map.values() for cid in kids}
    roots = [p["id"] for p in persons if p.get("id") and p["id"] not in child_ids]
    if not roots and persons:
        # 回退：世代最小者作根
        min_gen = min((p.get("generation") or 1) for p in persons)
        roots = [p["id"] for p in persons if (p.get("generation") or 1) == min_gen]
    return roots


def _build_node(
    person_id: str,
    by_id: dict,
    children_map: dict,
    visited: set[str] | None = None,
) -> dict:
    if visited is None:
        visited = set()
    if person_id in visited:
        return {
            "id": person_id,
            "name": by_id.get(person_id, {}).get("name", ""),
            "gender": "unknown",
            "children": [],
            "_cycle": True,
        }
    visited = visited | {person_id}
    p = by_id.get(person_id, {})
    kids = children_map.get(person_id, [])
    return {
        "id": person_id,
        "name": p.get("name", ""),
        "gender": p.get("gender", "unknown"),
        "birth_year": p.get("birth_year"),
        "death_year": p.get("death_year"),
        "generation": p.get("generation"),
        "generation_name": p.get("generation_name"),
        "status": p.get("status", "confirmed"),
        "children": [_build_node(cid, by_id, children_map, visited) for cid in kids],
    }


def _layout_meta(style: str, depth: int, index: int, generation: int | None = None) -> dict:
    if style == "eu":
        return {"axis": "horizontal", "offset_x": depth * 120, "offset_y": index * 56}
    if style == "tower":
        return {"axis": "vertical", "offset_x": index * 100, "offset_y": depth * 72}
    if style == "silkworm":
        # 垂丝图：严格按世代分行
        row = (generation or (depth + 1)) - 1
        return {"axis": "vertical", "offset_x": index * 128, "offset_y": row * 88, "generation_row": generation}
    if style == "radial":
        import math
        gen = generation or (depth + 1)
        radius = 70 + gen * 72
        total = max(index + 1, 1)
        angle = (2 * math.pi * index / total) - math.pi / 2
        cx, cy = 420, 320
        return {
            "axis": "radial",
            "offset_x": int(cx + radius * math.cos(angle)),
            "offset_y": int(cy + radius * math.sin(angle)),
            "generation_ring": gen,
        }
    # 苏式（默认）：竖向展开
    return {"axis": "vertical", "offset_x": index * 48, "offset_y": depth * 64}


def _silkworm_spacing(by_gen: dict[int, list]) -> tuple[int, int]:
    gen_count = max(len(by_gen), 1)
    max_row = max((len(v) for v in by_gen.values()), default=1)
    row_h = max(32, min(88, 2800 // gen_count))
    col_w = max(64, min(128, 3200 // max(max_row, 1)))
    return col_w, row_h


def _radial_spacing(by_gen: dict[int, list]) -> tuple[int, float]:
    gen_count = max(len(by_gen), 1)
    max_row = max((len(v) for v in by_gen.values()), default=1)
    radius_step = max(28, min(78, 2200 // gen_count))
    cx = cy = 80 + radius_step * gen_count + max_row * 4
    return int(radius_step), float(max(cx, 320))


def _compute_bounds(nodes: list[dict], *, node_w: int = 128, node_h: int = 72) -> dict[str, int]:
    max_x = 0
    max_y = 0
    for n in nodes:
        layout = n.get("layout") or {}
        max_x = max(max_x, int(layout.get("offset_x") or 0) + node_w)
        max_y = max(max_y, int(layout.get("offset_y") or 0) + node_h)
    return {
        "width": max(max_x + 64, 480),
        "height": max(max_y + 64, 360),
    }


def flatten_silkworm_by_generation(persons: list[dict]) -> list[dict]:
    """垂丝图：按 generation 分行，不依赖树深度。"""
    if not persons:
        return []
    by_gen: dict[int, list[dict]] = {}
    for p in persons:
        g = int(p.get("generation") or 1)
        by_gen.setdefault(g, []).append(p)
    min_gen = min(by_gen.keys())
    col_w, row_h = _silkworm_spacing(by_gen)
    flat: list[dict] = []
    for gen in sorted(by_gen.keys()):
        row_persons = sorted(by_gen[gen], key=lambda x: (x.get("name") or ""))
        row = gen - min_gen
        for idx, p in enumerate(row_persons):
            flat.append({
                "id": p.get("id"),
                "name": p.get("name", ""),
                "gender": p.get("gender", "unknown"),
                "birth_year": p.get("birth_year"),
                "death_year": p.get("death_year"),
                "generation": gen,
                "generation_name": p.get("generation_name"),
                "status": p.get("status", "confirmed"),
                "is_placeholder": p.get("is_placeholder"),
                "depth": row,
                "layout": {
                    "axis": "vertical",
                    "offset_x": idx * col_w,
                    "offset_y": row * row_h,
                    "generation_row": gen,
                    "node_width": col_w,
                    "node_height": row_h,
                },
            })
    return flat


def flatten_radial_by_generation(persons: list[dict]) -> list[dict]:
    """圆形图谱：以中心为始祖环，同代成员等距分布。"""
    import math
    if not persons:
        return []
    by_gen: dict[int, list[dict]] = {}
    for p in persons:
        g = int(p.get("generation") or 1)
        by_gen.setdefault(g, []).append(p)
    min_gen = min(by_gen.keys())
    radius_step, center = _radial_spacing(by_gen)
    cx = cy = center
    flat: list[dict] = []
    for gen in sorted(by_gen.keys()):
        row_persons = sorted(by_gen[gen], key=lambda x: (x.get("name") or ""))
        count = len(row_persons)
        radius = radius_step + (gen - min_gen) * radius_step
        for idx, p in enumerate(row_persons):
            angle = (2 * math.pi * idx / count) - math.pi / 2
            flat.append({
                "id": p.get("id"),
                "name": p.get("name", ""),
                "gender": p.get("gender", "unknown"),
                "birth_year": p.get("birth_year"),
                "death_year": p.get("death_year"),
                "generation": gen,
                "generation_name": p.get("generation_name"),
                "status": p.get("status", "confirmed"),
                "is_placeholder": p.get("is_placeholder"),
                "depth": gen - min_gen,
                "layout": {
                    "axis": "radial",
                    "offset_x": int(cx + radius * math.cos(angle)),
                    "offset_y": int(cy + radius * math.sin(angle)),
                    "generation_ring": gen,
                    "node_width": 96,
                    "node_height": 56,
                },
            })
    return flat


def flatten_tree(nodes: list[dict], style: str = "su") -> list[dict]:
    """将树展平为可渲染列表"""
    flat: list[dict] = []

    def walk(node: dict, depth: int, index: int):
        layout = _layout_meta(style, depth, index, generation=node.get("generation"))
        flat.append({
            "id": node["id"],
            "name": node["name"],
            "gender": node.get("gender"),
            "birth_year": node.get("birth_year"),
            "death_year": node.get("death_year"),
            "generation": node.get("generation"),
            "generation_name": node.get("generation_name"),
            "status": node.get("status"),
            "depth": depth,
            "layout": layout,
        })
        for i, child in enumerate(node.get("children") or []):
            walk(child, depth + 1, i)

    for i, root in enumerate(nodes):
        walk(root, 0, i)
    return flat


def build_family_tree(
    persons: list[dict],
    relations: list[dict],
    *,
    style: str = "su",
    hide_placeholders: bool = True,
) -> dict:
    """构建族谱树结构"""
    style = style if style in ("su", "eu", "tower", "silkworm", "radial") else "su"
    by_id = _index_persons(persons)
    if not by_id:
        return {"style": style, "roots": [], "nodes": [], "bounds": {"width": 480, "height": 360}, "person_count": 0}

    display_persons = [
        p for p in persons
        if not (hide_placeholders and p.get("is_placeholder"))
    ]
    display_by_id = _index_persons(display_persons)

    children_map = _children_map(display_persons, relations)
    root_ids = _find_roots(display_persons, children_map)
    roots = [_build_node(rid, display_by_id, children_map) for rid in root_ids]
    if style == "silkworm":
        nodes = flatten_silkworm_by_generation(list(display_by_id.values()))
    elif style == "radial":
        nodes = flatten_radial_by_generation(list(display_by_id.values()))
    else:
        nodes = flatten_tree(roots, style)
    bounds = _compute_bounds(nodes)
    if style == "silkworm" and nodes:
        layout0 = nodes[0].get("layout") or {}
        bounds = _compute_bounds(
            nodes,
            node_w=int(layout0.get("node_width") or 128),
            node_h=int(layout0.get("node_height") or 72),
        )
    elif style == "radial" and nodes:
        layout0 = nodes[0].get("layout") or {}
        bounds = _compute_bounds(
            nodes,
            node_w=int(layout0.get("node_width") or 96),
            node_h=int(layout0.get("node_height") or 56),
        )
    return {
        "style": style,
        "roots": roots,
        "nodes": nodes,
        "bounds": bounds,
        "person_count": len(persons),
        "display_count": len(display_persons),
        "root_count": len(roots),
        "placeholder_count": len(persons) - len(display_persons),
    }
