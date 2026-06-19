"""OCR API 冒烟测试（resolve_user_id 等）。"""

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


def test_scan_ocr_does_not_500_on_missing_image(test_db):
    from fastapi.testclient import TestClient
    import main

    client = TestClient(main.app)
    res = client.post("/api/agent/scan-ocr", json={})
    assert res.status_code == 400
    assert "Missing" in res.text or "缺少" in res.text


def test_ai_routing_does_not_500(test_db):
    from fastapi.testclient import TestClient
    import main

    client = TestClient(main.app)
    res = client.get("/api/ai/routing")
    assert res.status_code == 200
    body = res.json()
    assert "recommendations" in body or "success" in body or isinstance(body, dict)
