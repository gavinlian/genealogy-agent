import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from agent.tree import build_family_tree, flatten_tree


def _sample_data():
    persons = [
        {"id": "a", "name": "始祖", "generation": 1, "gender": "male"},
        {"id": "b", "name": "长子", "generation": 2, "gender": "male", "parent_id": "a"},
        {"id": "c", "name": "次子", "generation": 2, "gender": "male", "parent_id": "a"},
    ]
    relations = [
        {"from_person_id": "a", "to_person_id": "b", "relation_type": "parent_child"},
        {"from_person_id": "a", "to_person_id": "c", "relation_type": "parent_child"},
    ]
    return persons, relations


def test_build_tree_has_root():
    persons, relations = _sample_data()
    tree = build_family_tree(persons, relations, style="su")
    assert tree["root_count"] >= 1
    assert tree["person_count"] == 3
    assert tree["roots"][0]["name"] == "始祖"


def test_build_tree_children():
    persons, relations = _sample_data()
    tree = build_family_tree(persons, relations)
    root = tree["roots"][0]
    child_names = {c["name"] for c in root["children"]}
    assert child_names == {"长子", "次子"}


def test_flatten_tree_depth():
    persons, relations = _sample_data()
    tree = build_family_tree(persons, relations, style="eu")
    depths = {n["depth"] for n in tree["nodes"]}
    assert 0 in depths and 1 in depths


def test_tree_styles():
    persons, relations = _sample_data()
    for style in ("su", "eu", "tower", "silkworm", "radial"):
        tree = build_family_tree(persons, relations, style=style)
        assert tree["style"] == style
        assert tree["nodes"]
        axis = tree["nodes"][0]["layout"]["axis"]
        assert axis in ("vertical", "horizontal", "radial")


def test_silkworm_rows_by_generation():
    persons, relations = _sample_data()
    tree = build_family_tree(persons, relations, style="silkworm")
    gens = {n["generation"] for n in tree["nodes"]}
    assert gens == {1, 2}


def test_hide_placeholders_in_tree():
    persons = [
        {"id": "a", "name": "始祖", "generation": 1},
        {"id": "p", "name": "（待补）第2代", "generation": 2, "is_placeholder": True, "parent_id": "a"},
        {"id": "b", "name": "长子", "generation": 3, "parent_id": "p"},
    ]
    relations = [
        {"from_person_id": "a", "to_person_id": "p", "relation_type": "parent_child"},
        {"from_person_id": "p", "to_person_id": "b", "relation_type": "parent_child"},
    ]
    tree = build_family_tree(persons, relations, style="su", hide_placeholders=True)
    names = {n["name"] for n in tree["nodes"]}
    assert "（待补）第2代" not in names
    assert tree["placeholder_count"] == 1


def test_silkworm_compact_spacing_for_deep_tree():
    persons = [
        {"id": f"p{i}", "name": f"成员{i}", "generation": i, "gender": "male"}
        for i in range(1, 41)
    ]
    tree = build_family_tree(persons, [], style="silkworm")
    layout = tree["nodes"][0]["layout"]
    assert layout["node_height"] <= 88
    assert tree["bounds"]["height"] < 40 * 88


def test_tree_returns_bounds():
    persons, relations = _sample_data()
    tree = build_family_tree(persons, relations, style="silkworm")
    assert tree["bounds"]["width"] >= 480
    assert tree["bounds"]["height"] >= 360
