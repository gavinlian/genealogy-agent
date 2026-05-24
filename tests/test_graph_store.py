# -*- coding: utf-8 -*-
"""GraphStore 亲属查询"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from agent.graph_store import GraphStore


def _sample_graph():
    persons = [
        {"id": "a", "name": "始祖", "parent_id": None},
        {"id": "b", "name": "长子", "parent_id": "a"},
        {"id": "c", "name": "次子", "parent_id": "a"},
        {"id": "d", "name": "长孙", "parent_id": "b"},
        {"id": "e", "name": "次孙", "parent_id": "b"},
        {"id": "f", "name": "堂兄弟", "parent_id": "c"},
    ]
    relations = [
        {"from_person_id": "a", "to_person_id": "b", "relation_type": "parent_child"},
        {"from_person_id": "a", "to_person_id": "c", "relation_type": "parent_child"},
        {"from_person_id": "b", "to_person_id": "d", "relation_type": "parent_child"},
        {"from_person_id": "b", "to_person_id": "e", "relation_type": "parent_child"},
        {"from_person_id": "c", "to_person_id": "f", "relation_type": "parent_child"},
    ]
    return persons, relations


def test_siblings_and_cousins():
    persons, relations = _sample_graph()
    g = GraphStore(persons, relations)
    sibs = g.get_siblings("d")
    assert {p["name"] for p in sibs} == {"次孙"}
    cousins = g.get_cousins("d")
    assert {p["name"] for p in cousins} == {"堂兄弟"}


def test_find_relationship():
    persons, relations = _sample_graph()
    g = GraphStore(persons, relations)
    r = g.find_relationship("d", "f")
    assert r["found"] is True
    assert "堂兄弟" in r["summary"] or "相连" in r["summary"]


def test_ancestors_descendants():
    persons, relations = _sample_graph()
    g = GraphStore(persons, relations)
    anc = g.get_ancestors("d", depth=2)
    assert {p["name"] for p in anc} >= {"长子", "始祖"}
    desc = g.get_descendants("b", depth=2)
    assert {p["name"] for p in desc} >= {"长孙", "次孙"}
