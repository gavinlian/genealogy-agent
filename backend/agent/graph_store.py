"""族谱图查询层 — 亲属遍历、关系路径（Phase 1 GraphStore）。"""

from __future__ import annotations

from collections import deque
from typing import Any


class GraphStore:
    def __init__(self, persons: list[dict[str, Any]], relations: list[dict[str, Any]] | None = None):
        self._by_id: dict[str, dict[str, Any]] = {
            p["id"]: p for p in persons if p.get("id")
        }
        self._parents: dict[str, list[str]] = {pid: [] for pid in self._by_id}
        self._children: dict[str, list[str]] = {pid: [] for pid in self._by_id}
        self._spouses: dict[str, list[str]] = {pid: [] for pid in self._by_id}
        self._build_graph(relations or [], persons)

    def _build_graph(self, relations: list[dict], persons: list[dict]) -> None:
        for rel in relations:
            rtype = rel.get("relation_type") or rel.get("type") or "parent_child"
            if rtype == "parent_child":
                parent = rel.get("from_person_id") or rel.get("from")
                child = rel.get("to_person_id") or rel.get("to")
                if parent in self._by_id and child in self._by_id:
                    if parent not in self._parents[child]:
                        self._parents[child].append(parent)
                    if child not in self._children[parent]:
                        self._children[parent].append(child)
            elif rtype == "spouse":
                a = rel.get("from_person_id") or rel.get("from")
                b = rel.get("to_person_id") or rel.get("to")
                if a in self._by_id and b in self._by_id:
                    if b not in self._spouses[a]:
                        self._spouses[a].append(b)
                    if a not in self._spouses[b]:
                        self._spouses[b].append(a)

        for p in persons:
            pid = p.get("id")
            parent_id = p.get("parent_id")
            if pid and parent_id and parent_id in self._by_id:
                if parent_id not in self._parents[pid]:
                    self._parents[pid].append(parent_id)
                if pid not in self._children[parent_id]:
                    self._children[parent_id].append(pid)
            spouse_id = p.get("spouse_id")
            if pid and spouse_id and spouse_id in self._by_id:
                if spouse_id not in self._spouses[pid]:
                    self._spouses[pid].append(spouse_id)
                if pid not in self._spouses[spouse_id]:
                    self._spouses[spouse_id].append(pid)

    def get_person(self, person_id: str) -> dict[str, Any] | None:
        p = self._by_id.get(person_id)
        return dict(p) if p else None

    def find_by_name(self, name: str) -> list[dict[str, Any]]:
        name = (name or "").strip()
        if not name:
            return []
        exact = [dict(p) for p in self._by_id.values() if (p.get("name") or "") == name]
        if exact:
            return exact
        return [dict(p) for p in self._by_id.values() if name in (p.get("name") or "")]

    def get_parents(self, person_id: str) -> list[dict[str, Any]]:
        return [dict(self._by_id[pid]) for pid in self._parents.get(person_id, []) if pid in self._by_id]

    def get_children(self, person_id: str) -> list[dict[str, Any]]:
        return [dict(self._by_id[pid]) for pid in self._children.get(person_id, []) if pid in self._by_id]

    def get_siblings(self, person_id: str, *, include_self: bool = False) -> list[dict[str, Any]]:
        sibs: dict[str, dict] = {}
        for parent_id in self._parents.get(person_id, []):
            for cid in self._children.get(parent_id, []):
                if cid in self._by_id and (include_self or cid != person_id):
                    sibs[cid] = self._by_id[cid]
        return [dict(p) for p in sibs.values()]

    def get_ancestors(self, person_id: str, depth: int = 3) -> list[dict[str, Any]]:
        if person_id not in self._by_id or depth <= 0:
            return []
        seen: set[str] = set()
        result: list[dict] = []
        queue: deque[tuple[str, int]] = deque()
        for pid in self._parents.get(person_id, []):
            queue.append((pid, 1))
        while queue:
            pid, d = queue.popleft()
            if pid in seen or pid not in self._by_id:
                continue
            seen.add(pid)
            result.append({**dict(self._by_id[pid]), "_degree": d})
            if d < depth:
                for pp in self._parents.get(pid, []):
                    queue.append((pp, d + 1))
        return result

    def get_descendants(self, person_id: str, depth: int = 3) -> list[dict[str, Any]]:
        if person_id not in self._by_id or depth <= 0:
            return []
        seen: set[str] = set()
        result: list[dict] = []
        queue: deque[tuple[str, int]] = deque((cid, 1) for cid in self._children.get(person_id, []))
        while queue:
            pid, d = queue.popleft()
            if pid in seen or pid not in self._by_id:
                continue
            seen.add(pid)
            result.append({**dict(self._by_id[pid]), "_degree": d})
            if d < depth:
                for cid in self._children.get(pid, []):
                    queue.append((cid, d + 1))
        return result

    def get_cousins(self, person_id: str) -> list[dict[str, Any]]:
        """堂/表兄弟姐妹（MVP：父系叔伯子女 + 母系舅姨子女简化为同辈旁支）。"""
        if person_id not in self._by_id:
            return []
        exclude = {person_id} | {s["id"] for s in self.get_siblings(person_id, include_self=True)}
        cousins: dict[str, dict] = {}
        for parent_id in self._parents.get(person_id, []):
            for uncle_id in self._siblings_of(parent_id):
                for cid in self._children.get(uncle_id, []):
                    if cid not in exclude and cid in self._by_id:
                        cousins[cid] = self._by_id[cid]
        return [dict(p) for p in cousins.values()]

    def _siblings_of(self, person_id: str) -> list[str]:
        sibs: set[str] = set()
        for parent_id in self._parents.get(person_id, []):
            for cid in self._children.get(parent_id, []):
                if cid != person_id:
                    sibs.add(cid)
        return list(sibs)

    def find_relationship(self, person_a_id: str, person_b_id: str) -> dict[str, Any]:
        if person_a_id not in self._by_id or person_b_id not in self._by_id:
            return {"found": False, "summary": "成员不存在"}
        if person_a_id == person_b_id:
            return {"found": True, "summary": "同一人"}

        path = self._shortest_path(person_a_id, person_b_id)
        if not path:
            return {"found": False, "summary": "未找到关联路径（可能分属不同支系）"}

        a_name = self._by_id[person_a_id].get("name", "")
        b_name = self._by_id[person_b_id].get("name", "")
        hops = len(path) - 1
        return {
            "found": True,
            "summary": f"{a_name} 与 {b_name} 通过 {hops} 步家族关系相连",
            "path": [
                {"id": pid, "name": self._by_id[pid].get("name", ""), "edge": edge}
                for pid, edge in path
            ],
        }

    def _shortest_path(self, start: str, goal: str) -> list[tuple[str, str]] | None:
        """BFS，边类型：parent / child / spouse / sibling。"""
        if start == goal:
            return [(start, "self")]

        def neighbors(pid: str) -> list[tuple[str, str]]:
            out: list[tuple[str, str]] = []
            for parent_id in self._parents.get(pid, []):
                out.append((parent_id, "parent"))
            for child_id in self._children.get(pid, []):
                out.append((child_id, "child"))
            for spouse_id in self._spouses.get(pid, []):
                out.append((spouse_id, "spouse"))
            for sib_id in self._siblings_of(pid):
                out.append((sib_id, "sibling"))
            return out

        queue: deque[str] = deque([start])
        prev: dict[str, tuple[str, str]] = {}
        seen = {start}
        while queue:
            cur = queue.popleft()
            for nxt, edge in neighbors(cur):
                if nxt in seen:
                    continue
                seen.add(nxt)
                prev[nxt] = (cur, edge)
                if nxt == goal:
                    path: list[tuple[str, str]] = [(goal, edge)]
                    node = goal
                    while node in prev:
                        p, e = prev[node]
                        path.append((p, e))
                        node = p
                    path.reverse()
                    path[0] = (start, "start")
                    return path
                queue.append(nxt)
        return None

    def summarize_relatives(
        self,
        person_id: str,
        kind: str,
        *,
        depth: int = 3,
    ) -> dict[str, Any]:
        person = self.get_person(person_id)
        if not person:
            return {"success": False, "error": "成员不存在"}

        kind = (kind or "siblings").lower()
        fetchers = {
            "parents": lambda: self.get_parents(person_id),
            "children": lambda: self.get_children(person_id),
            "siblings": lambda: self.get_siblings(person_id),
            "cousins": lambda: self.get_cousins(person_id),
            "ancestors": lambda: self.get_ancestors(person_id, depth=depth),
            "descendants": lambda: self.get_descendants(person_id, depth=depth),
        }
        fn = fetchers.get(kind)
        if not fn:
            return {"success": False, "error": f"不支持的亲属类型: {kind}"}

        people = fn()
        return {
            "success": True,
            "kind": kind,
            "person": {"id": person_id, "name": person.get("name")},
            "count": len(people),
            "people": [
                {
                    "id": p.get("id"),
                    "name": p.get("name"),
                    "generation": p.get("generation"),
                    "courtesy_name": p.get("courtesy_name"),
                    "art_name": p.get("art_name"),
                }
                for p in people
            ],
        }
