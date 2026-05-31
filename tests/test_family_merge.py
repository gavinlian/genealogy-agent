"""跨族谱合并测试。"""

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


def test_merge_preview_and_apply_via_api(test_db):
    from fastapi.testclient import TestClient
    import main

    client = TestClient(main.app)
    target = client.post("/api/families", json={"name": "主谱", "surname": "张"}).json()
    source = client.post("/api/families", json={"name": "支谱", "surname": "张"}).json()
    tid, sid = target["id"], source["id"]

    client.post(
        "/api/persons/batch",
        json={
            "family_id": tid,
            "persons": [{"name": "张三", "generation": 1}],
            "relations": [],
        },
    )
    client.post(
        "/api/persons/batch",
        json={
            "family_id": sid,
            "persons": [
                {"name": "张三", "generation": 1, "courtesy_name": "子明"},
                {"name": "张四", "generation": 2},
            ],
            "relations": [{"from": "张三", "to": "张四", "type": "parent_child"}],
        },
    )
    client.put(
        f"/api/families/{sid}/source-text",
        json={"source_text": "支谱 OCR 原文", "origin": "ocr"},
    )

    preview = client.get(f"/api/families/{tid}/merge-preview?source_id={sid}").json()
    assert preview.get("success") is True
    assert preview["stats"]["persons_to_add"] == 1
    assert preview["stats"]["persons_to_update"] == 1
    assert preview["stats"]["relations_to_add"] == 1

    merged = client.post(
        f"/api/families/{tid}/merge-from",
        json={"source_family_id": sid},
    ).json()
    assert merged.get("success") is True
    assert merged.get("persons_added") == 1
    assert merged.get("ocr_text_merged") is True

    persons = client.get(f"/api/families/{tid}/persons").json()
    names = {p["name"] for p in persons}
    assert "张四" in names

    versions = client.get(f"/api/families/{tid}/source-versions").json()
    v1 = next((v for v in versions.get("versions") or [] if v.get("version_kind") == "ocr_raw"), None)
    assert v1 and "支谱 OCR 原文" in (v1.get("source_text") or "")


def test_agent_propose_merge_family(test_db):
    from fastapi.testclient import TestClient
    import main

    client = TestClient(main.app)
    target = client.post("/api/families", json={"name": "目标谱"}).json()
    source = client.post("/api/families", json={"name": "来源谱"}).json()
    tid, sid = target["id"], source["id"]
    client.post(
        "/api/persons/batch",
        json={"family_id": sid, "persons": [{"name": "王五", "generation": 1}], "relations": []},
    )

    chat = client.post(
        f"/api/families/{tid}/agent/chat",
        json={"message": "把来源谱合并进当前族谱", "use_llm": False},
    )
    # 规则回退可能不触发 merge；直接测工具路径用 source_family_id
    from agent.family_merge import build_family_merge_preview
    import sqlite3

    conn = sqlite3.connect(test_db)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    preview = build_family_merge_preview(c, tid, sid, "local-default")
    conn.close()
    assert preview["stats"]["persons_to_add"] == 1

    from agent.tool_executor import propose_write_tool
    from agent.graph_store import GraphStore

    conn = sqlite3.connect(test_db)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    persons = [dict(r) for r in c.execute("SELECT * FROM persons WHERE family_id = ?", (tid,)).fetchall()]
    rels = [dict(r) for r in c.execute("SELECT * FROM relations WHERE family_id = ?", (tid,)).fetchall()]
    graph = GraphStore(persons, rels)
    result = propose_write_tool(
        "propose_merge_family",
        {"source_family_id": sid},
        cursor=c,
        family_id=tid,
        graph=graph,
        persons=persons,
        relations=rels,
        context={"user_id": "local-default"},
    )
    conn.commit()
    conn.close()
    assert result.success
    assert result.confirmation
    assert result.confirmation["tool"] == "propose_merge_family"
