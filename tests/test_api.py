"""HTTP API 测试"""

import base64


def test_agent_status_endpoint(client):
    resp = client.get("/api/agent/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["domain"] == "genealogy"
    assert "scan" in data["tasks"]


def test_agent_validate_endpoint(client):
    resp = client.post(
        "/api/agent/validate",
        json={
            "persons": [{"name": "测试", "birth_year": 2010, "death_year": 2000}],
            "relations": [],
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["valid"] is False


def test_families_crud(client):
    create = client.post("/api/families", json={"name": "测试族", "surname": "测"})
    assert create.status_code == 200
    fid = create.json()["id"]

    listing = client.get("/api/families")
    assert listing.status_code == 200
    assert any(f["id"] == fid for f in listing.json())

    delete = client.delete(f"/api/families/{fid}")
    assert delete.status_code == 200


def test_agent_scan_missing_image(client):
    resp = client.post("/api/agent/scan", json={})
    assert resp.status_code == 200
    assert resp.json()["success"] is False


def test_ai_test_missing_key(client):
    resp = client.post(
        "/api/ai/test",
        json={"task": "parse", "provider": "minimax", "model": "MiniMax-M2.7"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is False
    assert any(x in data["message"] for x in ("API Key", "未配置", "Group ID"))


def test_ai_test_unknown_task(client):
    resp = client.post("/api/ai/test", json={"task": "invalid"})
    assert resp.status_code == 400


def test_ocr_parse_local_fallback(client):
    text = "张三生1980卒2020\n张四男"
    resp = client.post("/api/ocr/parse", json={"text": text})
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert len(data["persons"]) >= 1
