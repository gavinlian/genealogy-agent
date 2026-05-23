"""成员与关系编辑测试"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from agent.person_editor import get_spouse_id, sync_parent_relation, sync_spouse_relation


def test_update_person_syncs_parent(client):
    fam = client.post("/api/families", json={"name": "编辑测试"})
    fid = fam.json()["id"]
    p1 = client.post("/api/persons", json={"family_id": fid, "name": "父亲", "generation": 1, "gender": "male"})
    p2 = client.post("/api/persons", json={"family_id": fid, "name": "儿子", "generation": 2, "gender": "male"})
    father_id = p1.json()["id"]
    son_id = p2.json()["id"]

    res = client.put(f"/api/persons/{son_id}", json={
        "name": "儿子",
        "generation": 2,
        "parent_id": father_id,
        "spouse_id": None,
    })
    assert res.json()["success"] is True

    son = next(p for p in client.get(f"/api/families/{fid}/persons").json() if p["id"] == son_id)
    assert son["parent_id"] == father_id

    rels = client.get(f"/api/families/{fid}/relations").json()
    assert any(
        r["relation_type"] == "parent_child"
        and r["from_person_id"] == father_id
        and r["to_person_id"] == son_id
        for r in rels
    )


def test_update_person_syncs_spouse(client):
    fam = client.post("/api/families", json={"name": "配偶测试"})
    fid = fam.json()["id"]
    h = client.post("/api/persons", json={"family_id": fid, "name": "丈夫", "gender": "male"})
    w = client.post("/api/persons", json={"family_id": fid, "name": "妻子", "gender": "female"})
    hid, wid = h.json()["id"], w.json()["id"]

    client.put(f"/api/persons/{hid}", json={
        "name": "丈夫",
        "spouse_id": wid,
        "parent_id": None,
    })

    rels = client.get(f"/api/families/{fid}/relations").json()
    assert any(r["relation_type"] == "spouse" for r in rels)

    persons = client.get(f"/api/families/{fid}/persons").json()
    husband = next(p for p in persons if p["id"] == hid)
    assert husband.get("spouse_id") == wid


def test_create_relation_parent_child(client):
    fam = client.post("/api/families", json={"name": "关系测试"})
    fid = fam.json()["id"]
    a = client.post("/api/persons", json={"family_id": fid, "name": "甲", "generation": 1})
    b = client.post("/api/persons", json={"family_id": fid, "name": "乙", "generation": 2})
    aid, bid = a.json()["id"], b.json()["id"]

    res = client.post("/api/relations", json={
        "family_id": fid,
        "from_person_id": aid,
        "to_person_id": bid,
        "relation_type": "parent_child",
    })
    assert res.json()["success"] is True

    child = next(p for p in client.get(f"/api/families/{fid}/persons").json() if p["id"] == bid)
    assert child["parent_id"] == aid


def test_create_relation_duplicate_fails(client):
    fam = client.post("/api/families", json={"name": "重复关系"})
    fid = fam.json()["id"]
    a = client.post("/api/persons", json={"family_id": fid, "name": "甲"})
    b = client.post("/api/persons", json={"family_id": fid, "name": "乙"})
    payload = {
        "family_id": fid,
        "from_person_id": a.json()["id"],
        "to_person_id": b.json()["id"],
        "relation_type": "parent_child",
    }
    assert client.post("/api/relations", json=payload).status_code == 200
    dup = client.post("/api/relations", json=payload)
    assert dup.status_code == 400


def test_update_family(client):
    fam = client.post("/api/families", json={"name": "旧名", "surname": "李"})
    fid = fam.json()["id"]
    res = client.put(f"/api/families/{fid}", json={"name": "新名", "surname": "李", "description": "简介"})
    assert res.json()["success"] is True
    assert res.json()["family"]["name"] == "新名"


def test_person_detail_includes_spouse(client):
    fam = client.post("/api/families", json={"name": "详情"})
    fid = fam.json()["id"]
    h = client.post("/api/persons", json={"family_id": fid, "name": "夫", "gender": "male"})
    w = client.post("/api/persons", json={"family_id": fid, "name": "妻", "gender": "female"})
    client.put(f"/api/persons/{h.json()['id']}", json={"name": "夫", "spouse_id": w.json()["id"]})

    detail = client.get(f"/api/persons/{h.json()['id']}").json()
    assert detail["success"] is True
    assert detail.get("spouse") is not None
    assert detail["spouse"]["name"] == "妻"


def test_delete_person_clears_children_parent(client):
    fam = client.post("/api/families", json={"name": "删除"})
    fid = fam.json()["id"]
    p = client.post("/api/persons", json={"family_id": fid, "name": "父", "generation": 1})
    c = client.post("/api/persons", json={
        "family_id": fid, "name": "子", "generation": 2, "parent_id": p.json()["id"],
    })
    client.delete(f"/api/persons/{p.json()['id']}")
    child = next(x for x in client.get(f"/api/families/{fid}/persons").json() if x["id"] == c.json()["id"])
    assert child.get("parent_id") is None
