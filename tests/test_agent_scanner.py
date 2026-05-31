"""族谱智能体：人物匹配与扫描。"""

import json
import os
import sys

import pytest

BACKEND_DIR = os.path.join(os.path.dirname(__file__), "..", "backend")
sys.path.insert(0, BACKEND_DIR)


@pytest.fixture()
def test_db(monkeypatch):
    fd, path = __import__("tempfile").mkstemp(suffix=".db")
    os.close(fd)
    monkeypatch.setattr("main.DB_PATH", path)
    import main

    main.init_db()
    yield path
    try:
        os.remove(path)
    except OSError:
        pass


def test_person_match_same_name_generation():
    from agent.person_matcher import score_person_match, find_person_matches

    a = {"name": "张三", "generation": 3, "birth_year": 1920}
    b = {"name": "张三", "generation": 3, "birth_year": 1921}
    assert score_person_match(a, b) >= 0.8
    matches = find_person_matches([a], [b], min_confidence=0.62)
    assert len(matches) == 1


def test_agent_scan_creates_discovery(test_db):
    from fastapi.testclient import TestClient
    import main

    client = TestClient(main.app)
    fam = client.post("/api/families", json={"name": "张氏", "surname": "张"}).json()
    fid = fam["id"]
    client.post(
        "/api/persons/batch",
        json={
            "family_id": fid,
            "persons": [{"name": "张公", "generation": 1}, {"name": "张三", "generation": 2}],
            "relations": [{"from": "张公", "to": "张三", "type": "parent_child"}],
        },
    )
    client.put(
        f"/api/families/{fid}/source-text",
        json={
            "source_text": "一世 张公 男 子张三\n二世 张三 男 子张四",
            "origin": "manual",
        },
    )
    res = client.post("/api/agent/genealogy-scan", json={"trigger": "manual"})
    assert res.status_code == 200
    body = res.json()
    assert body.get("success") is True
    disc = client.get("/api/agent/discoveries").json()
    assert disc.get("success") is True


def test_follow_family(test_db):
    from fastapi.testclient import TestClient
    import main
    import sqlite3

    client = TestClient(main.app)
    a = client.post("/api/families", json={"name": "甲谱"}).json()
    b = client.post("/api/families", json={"name": "乙谱"}).json()
    conn = sqlite3.connect(test_db)
    conn.execute("UPDATE families SET owner_user_id = 'other-user' WHERE id = ?", (b["id"],))
    conn.execute("DELETE FROM family_memberships WHERE family_id = ?", (b["id"],))
    conn.commit()
    conn.close()
    dash = client.get("/api/families/dashboard").json()
    assert dash.get("success") is True
    assert any(x["id"] == a["id"] for x in dash.get("owned", []))
    follow = client.post(f"/api/families/{b['id']}/follow").json()
    assert follow.get("success") is True
    dash2 = client.get("/api/families/dashboard").json()
    assert any(x["id"] == b["id"] for x in dash2.get("followed", []))


def test_genealogy_snapshot(test_db):
    from fastapi.testclient import TestClient
    import main

    client = TestClient(main.app)
    fam = client.post("/api/families", json={"name": "快照源"}).json()
    snap = client.post(
        "/api/genealogy-snapshots/from-family/" + fam["id"],
        json={"name": "测试大库"},
    ).json()
    assert snap.get("success") is True
    listed = client.get("/api/genealogy-snapshots").json()
    assert len(listed.get("snapshots") or []) >= 1
