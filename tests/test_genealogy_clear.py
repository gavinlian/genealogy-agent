# -*- coding: utf-8 -*-
"""清空主谱测试"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from genealogy_clear import clear_family_genealogy, collect_branch_person_ids


class FakeCursor:
    def __init__(self, persons, relations, family_id="f1", root_person_id="p1"):
        self.persons = {p["id"]: dict(p) for p in persons}
        self.relations = [dict(r) for r in relations]
        self.family_id = family_id
        self.root_person_id = root_person_id
        self.rowcount = 0

    def execute(self, sql, params=()):
        self.last_sql = sql
        self.last_params = params
        sql_norm = " ".join(sql.split())
        if "SELECT id, parent_id FROM persons WHERE family_id" in sql_norm:
            self._rows = [
                {"id": pid, "parent_id": p.get("parent_id")}
                for pid, p in self.persons.items()
                if p.get("family_id") == params[0]
            ]
        elif "SELECT id FROM persons WHERE family_id" in sql_norm:
            self._rows = [{"id": pid} for pid, p in self.persons.items() if p.get("family_id") == params[0]]
        elif "SELECT from_person_id, to_person_id FROM relations" in sql_norm:
            self._rows = [
                {"from_person_id": r["from_person_id"], "to_person_id": r["to_person_id"]}
                for r in self.relations
                if r.get("family_id") == params[0] and r.get("relation_type") == "parent_child"
            ]
        elif "SELECT id FROM relations" in sql_norm and "IN" in sql_norm:
            target = set(params[1 : 1 + (len(params) - 1) // 2])
            self._rows = []
            for r in self.relations:
                if r.get("family_id") != params[0]:
                    continue
                if r["from_person_id"] in target or r["to_person_id"] in target:
                    self._rows.append({"id": r["id"]})
        elif sql_norm.startswith("DELETE FROM relations"):
            rid = params[0]
            before = len(self.relations)
            self.relations = [r for r in self.relations if r["id"] != rid]
            self.rowcount = before - len(self.relations)
        elif sql_norm.startswith("UPDATE persons SET parent_id = NULL"):
            pid, fid = params
            for p in self.persons.values():
                if p.get("family_id") == fid and p.get("parent_id") == pid:
                    p["parent_id"] = None
            self.rowcount = 1
        elif sql_norm.startswith("DELETE FROM persons"):
            pid, fid = params
            if pid in self.persons and self.persons[pid].get("family_id") == fid:
                del self.persons[pid]
                self.rowcount = 1
            else:
                self.rowcount = 0
        elif "SELECT root_person_id FROM families" in sql_norm:
            self._rows = [{"root_person_id": self.root_person_id}]
        elif sql_norm.startswith("UPDATE families SET root_person_id = NULL"):
            self.root_person_id = None
            self.rowcount = 1
        elif sql_norm.startswith("UPDATE families SET updated_at"):
            self.rowcount = 1
        else:
            self._rows = []
        return self

    def fetchall(self):
        return getattr(self, "_rows", [])

    def fetchone(self):
        rows = getattr(self, "_rows", [])
        return rows[0] if rows else None


def test_collect_branch_person_ids():
    persons = [
        {"id": "p1", "family_id": "f1", "parent_id": None},
        {"id": "p2", "family_id": "f1", "parent_id": "p1"},
        {"id": "p3", "family_id": "f1", "parent_id": "p2"},
        {"id": "p4", "family_id": "f1", "parent_id": "p1"},
    ]
    relations = [
        {"id": "r1", "family_id": "f1", "from_person_id": "p1", "to_person_id": "p2", "relation_type": "parent_child"},
        {"id": "r2", "family_id": "f1", "from_person_id": "p2", "to_person_id": "p3", "relation_type": "parent_child"},
    ]
    c = FakeCursor(persons, relations)
    branch = collect_branch_person_ids(c, "f1", "p2")
    assert branch == {"p2", "p3"}


def test_clear_family_genealogy_all():
    persons = [
        {"id": "p1", "family_id": "f1", "parent_id": None},
        {"id": "p2", "family_id": "f1", "parent_id": "p1"},
    ]
    relations = [
        {"id": "r1", "family_id": "f1", "from_person_id": "p1", "to_person_id": "p2", "relation_type": "parent_child"},
    ]
    c = FakeCursor(persons, relations)
    stats = clear_family_genealogy(c, "f1", scope="all")
    assert stats["persons_removed"] == 2
    assert stats["relations_removed"] == 1
    assert c.persons == {}


def test_clear_family_genealogy_branch():
    persons = [
        {"id": "p1", "family_id": "f1", "parent_id": None},
        {"id": "p2", "family_id": "f1", "parent_id": "p1"},
        {"id": "p3", "family_id": "f1", "parent_id": "p2"},
    ]
    relations = [
        {"id": "r1", "family_id": "f1", "from_person_id": "p1", "to_person_id": "p2", "relation_type": "parent_child"},
        {"id": "r2", "family_id": "f1", "from_person_id": "p2", "to_person_id": "p3", "relation_type": "parent_child"},
    ]
    c = FakeCursor(persons, relations, root_person_id="p1")
    stats = clear_family_genealogy(c, "f1", scope="branch", root_person_id="p2")
    assert stats["persons_removed"] == 2
    assert "p1" in c.persons
    assert "p2" not in c.persons
