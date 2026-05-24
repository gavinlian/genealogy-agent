"""MVP 验收用例（对齐 .cursor/plans 族谱工具 MVP）"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))


def test_mvp_family_tree_api(client):
    create = client.post("/api/families", json={"name": "张氏", "surname": "张"})
    fid = create.json()["id"]
    client.post("/api/persons", json={
        "family_id": fid, "name": "张公", "generation": 1, "gender": "male",
    })
    p2 = client.post("/api/persons", json={
        "family_id": fid, "name": "张孙", "generation": 2, "gender": "male",
        "parent_id": None,
    })
    # 建立父子
    persons = client.get(f"/api/families/{fid}/persons").json()
    root = next(p for p in persons if p["name"] == "张公")
    child = next(p for p in persons if p["name"] == "张孙")
    client.post("/api/relations", json={
        "family_id": fid,
        "from_person_id": root["id"],
        "to_person_id": child["id"],
        "relation_type": "parent_child",
    })

    for style in ("su", "eu", "tower"):
        tree = client.get(f"/api/families/{fid}/tree?style={style}").json()
        assert tree["success"] is True
        assert tree["person_count"] >= 2


def test_mvp_search_api(client):
    create = client.post("/api/families", json={"name": "李氏"})
    fid = create.json()["id"]
    client.post("/api/persons", json={
        "family_id": fid, "name": "李明", "generation_name": "如玉",
    })
    res = client.get(f"/api/families/{fid}/search?q=李明")
    data = res.json()
    assert data["success"] is True
    assert data["count"] >= 1


def test_mvp_batch_with_relations(client):
    create = client.post("/api/families", json={"name": "王氏"})
    fid = create.json()["id"]
    batch = client.post("/api/persons/batch", json={
        "family_id": fid,
        "persons": [
            {"name": "王父", "generation": 1, "gender": "male"},
            {"name": "王子", "generation": 2, "gender": "male"},
        ],
        "relations": [{"from": "王父", "to": "王子", "type": "parent_child"}],
    })
    assert batch.json()["success"] is True
    assert batch.json()["relation_count"] == 1

    persons = client.get(f"/api/families/{fid}/persons").json()
    child = next(p for p in persons if p["name"] == "王子")
    assert child["parent_id"] is not None


def test_mvp_export_import_roundtrip(client):
    create = client.post("/api/families", json={"name": "赵氏"})
    fid = create.json()["id"]
    client.post("/api/persons", json={"family_id": fid, "name": "赵一"})

    exported = client.get(f"/api/families/{fid}/export").json()
    assert exported["family"]["name"] == "赵氏"
    assert len(exported["persons"]) >= 1

    imported = client.post("/api/import", json=exported)
    assert imported.json()["success"] is True


def test_mvp_agent_validate(client):
    res = client.post("/api/agent/validate", json={
        "persons": [{"name": "测试", "birth_year": 2000, "death_year": 1990}],
        "relations": [],
    })
    assert res.json()["valid"] is False


def test_mvp_ocr_parse_local(client):
    res = client.post("/api/ocr/parse", json={"text": "张三生1980\n张四男"})
    assert res.status_code == 200
    assert len(res.json()["persons"]) >= 1


def test_merge_apply_preserves_existing_with_clean_slate_plan(client):
    """插入合并时即使方案带 clean_slate、diff 含 extra_persons，也不应删已有成员。"""
    create = client.post("/api/families", json={"name": "陈氏"})
    fid = create.json()["id"]
    client.post("/api/persons", json={"family_id": fid, "name": "陈公", "generation": 1, "gender": "male"})
    client.post("/api/persons", json={"family_id": fid, "name": "陈甲", "generation": 2, "gender": "male"})

    plan = {
        "explanation": "补新支",
        "clean_slate": True,
        "new_persons": [{"name": "陈乙", "generation": 2, "gender": "male"}],
        "relations_add": [{"from": "陈公", "to": "陈乙", "type": "parent_child", "status": "confirmed"}],
    }
    diff = {
        "extra_persons": ["陈甲"],
        "extra_relations": [],
        "has_replace_impact": True,
        "clean_slate": True,
    }
    res = client.post(f"/api/families/{fid}/ai-organize", json={
        "persist": True,
        "plan": plan,
        "apply_mode": "merge",
        "diff": diff,
    })
    body = res.json()
    assert body["success"] is True
    assert body["applied"]["persons_removed"] == 0
    names = {p["name"] for p in client.get(f"/api/families/{fid}/persons").json()}
    assert {"陈公", "陈甲", "陈乙"}.issubset(names)
