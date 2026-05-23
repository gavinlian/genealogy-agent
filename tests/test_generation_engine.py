import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from agent.generation_engine import (
    add_person_with_kinship,
    ensure_ancestor_chain,
    kinship_generation_delta,
    recalculate_generations,
    validate_generation_logic,
)


def _base_persons():
    return [
        {"id": "a", "name": "始祖", "generation": 1, "gender": "male"},
        {"id": "b", "name": "长子", "generation": 2, "gender": "male", "parent_id": "a"},
    ]


def _base_relations():
    return [
        {"from_person_id": "a", "to_person_id": "b", "relation_type": "parent_child"},
    ]


def test_kinship_delta():
    assert kinship_generation_delta("曾孙") == 3
    assert kinship_generation_delta("子") == 1


def test_recalculate_from_root():
    persons = _base_persons()
    relations = _base_relations()
    result = recalculate_generations(
        persons, relations, root_person_id="a", start_generation=1
    )
    by_id = {p["id"]: p for p in result["persons"]}
    assert by_id["a"]["generation"] == 1
    assert by_id["b"]["generation"] == 2
    assert result["root_person_id"] == "a"


def test_recalculate_custom_start_generation():
    persons = _base_persons()
    relations = _base_relations()
    result = recalculate_generations(
        persons, relations, root_person_id="a", start_generation=5
    )
    by_id = {p["id"]: p for p in result["persons"]}
    assert by_id["a"]["generation"] == 5
    assert by_id["b"]["generation"] == 6


def test_ensure_ancestor_chain_creates_placeholders():
    persons = _base_persons()
    relations = _base_relations()
    new_persons, new_relations, leaf_id = ensure_ancestor_chain(
        persons, relations, "b", target_generation=4, start_generation=1
    )
    placeholders = [p for p in new_persons if p.get("is_placeholder")]
    assert len(placeholders) == 1
    assert placeholders[0]["generation"] == 3
    assert leaf_id is not None


def test_add_person_with_kinship_great_grandchild():
    persons = _base_persons()
    relations = _base_relations()
    result = add_person_with_kinship(
        persons,
        relations,
        "a",
        "曾孙",
        {"name": "小明", "gender": "male"},
        start_generation=1,
    )
    assert result["success"] is True
    assert result["target_generation"] == 4
    placeholders = [p for p in result["persons"] if p.get("is_placeholder")]
    # 已有长子（第2代），仅需补第3代占位
    assert len(placeholders) == 1


def test_validate_generation_logic_birth_before_parent():
    persons = [
        {"id": "a", "name": "祖父", "generation": 1, "birth_year": 1900},
        {"id": "b", "name": "孙子", "generation": 3, "birth_year": 1890, "parent_id": "a"},
    ]
    relations = [{"from_person_id": "a", "to_person_id": "b", "relation_type": "parent_child"}]
    issues = validate_generation_logic(persons, relations)
    assert any(i["level"] == "error" for i in issues)
