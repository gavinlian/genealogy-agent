import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from agent.search import search_persons


def test_search_by_name():
    persons = [
        {"id": "1", "name": "张三", "generation": 1},
        {"id": "2", "name": "李四", "generation": 2},
    ]
    r = search_persons(persons, "张三")
    assert len(r) == 1
    assert r[0]["name"] == "张三"


def test_search_by_generation():
    persons = [{"id": "1", "name": "甲", "generation": 3}]
    r = search_persons(persons, "3")
    assert len(r) == 1


def test_search_empty_query():
    assert search_persons([{"name": "x"}], "") == []
