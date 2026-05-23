"""v1.1 族谱能力测试"""


def test_person_detail_api(client):
    create = client.post("/api/families", json={"name": "陈氏"})
    fid = create.json()["id"]
    p = client.post("/api/persons", json={
        "family_id": fid, "name": "陈父", "generation": 1, "courtesy_name": "伯仁",
    })
    pid = p.json()["id"]
    res = client.get(f"/api/persons/{pid}")
    data = res.json()
    assert data["person"]["name"] == "陈父"
    assert data["person"]["courtesy_name"] == "伯仁"


def test_nl_search_kinship(client):
    create = client.post("/api/families", json={"name": "林氏"})
    fid = create.json()["id"]
    batch = client.post("/api/persons/batch", json={
        "family_id": fid,
        "persons": [
            {"name": "林公", "generation": 1},
            {"name": "林儿", "generation": 2},
        ],
        "relations": [{"from": "林公", "to": "林儿", "type": "parent_child"}],
    })
    assert batch.json()["success"]

    res = client.post(f"/api/families/{fid}/search", json={"q": "林公的儿子", "mode": "nl"})
    data = res.json()
    assert data["count"] >= 1
    assert any(r["name"] == "林儿" for r in data["results"])


def test_export_pdf_html(client):
    create = client.post("/api/families", json={"name": "周氏"})
    fid = create.json()["id"]
    client.post("/api/persons", json={"family_id": fid, "name": "周一"})
    res = client.get(f"/api/families/{fid}/export/pdf?style=su")
    assert res.status_code == 200
    assert "周氏" in res.text


def test_scan_returns_review_flags(client, monkeypatch):
    async def mock_ocr(*a, **k):
        return "张三生1980\n张四男", ""

    async def mock_parse(*a, **k):
        prompt = a[2] if len(a) > 2 else k.get("prompt", "")
        if "第一步" in prompt or "关系描述稿" in prompt:
            return "一世 张三 男 生1980\n一世 张四 男", ""
        return '{"persons":[{"name":"张三","gender":"male","birth_year":1980,"generation":1}],"relations":[]}', ""

    import main
    monkeypatch.setattr(main, "call_vision_model", mock_ocr)
    monkeypatch.setattr(main, "call_text_model", mock_parse)

    res = client.post("/api/agent/scan", json={"image": "aGVsbG8="})
    data = res.json()
    assert data["success"]
    assert "_review_flags" in data["persons"][0] or data.get("needs_review") is not None
