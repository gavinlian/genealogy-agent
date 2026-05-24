# -*- coding: utf-8 -*-
"""文字版 → 主谱人物资料回填"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from agent.source_person_sync import (
    build_source_person_index,
    compute_person_detail_patches,
    extract_line_profile_fields,
)


def test_build_source_person_index_extracts_courtesy_and_bio():
    text = "第1世 张三，字子明，生于1980年，卒于2020年，任某县教谕。"
    index = build_source_person_index(text)
    assert "张三" in index
    profile = index["张三"]
    assert profile.get("courtesy_name") == "子明"
    assert profile.get("birth_year") == 1980
    assert profile.get("death_year") == 2020
    assert profile.get("biography")


def test_extract_line_profile_fields_art_name():
    fields = extract_line_profile_fields("李四，字仲文，号竹溪居士，生于清咸丰年间。")
    assert fields.get("courtesy_name") == "仲文"
    assert fields.get("art_name") == "竹溪居士"


def test_compute_person_detail_patches_fills_empty_fields_only():
    source = "第2世 李四，字仲文，生于1850年，卒于1910年。"
    persons = [
        {"id": "1", "name": "李四", "birth_year": None, "biography": ""},
        {"id": "2", "name": "王五", "birth_year": 1900},
    ]
    patches = compute_person_detail_patches(persons, source)
    by_name = {p["name"]: p for p in patches}
    assert "李四" in by_name
    assert by_name["李四"].get("birth_year") == 1850
    assert by_name["李四"].get("courtesy_name") == "仲文"
    assert "王五" not in by_name


def test_sync_person_details_api(client):
    create = client.post("/api/families", json={"name": "测试"})
    fid = create.json()["id"]
    client.post("/api/persons", json={"family_id": fid, "name": "赵六", "generation": 1})
    client.put(f"/api/families/{fid}/source-text", json={
        "source_text": "第1世 赵六，字伯常，生于1920年，卒于1998年。",
    })
    res = client.post(f"/api/families/{fid}/sync-person-details", json={})
    assert res.json()["success"] is True
    assert res.json().get("persons_updated", 0) >= 1
    persons = client.get(f"/api/families/{fid}/persons").json()
    person = next(p for p in persons if p["name"] == "赵六")
    assert person.get("courtesy_name") == "伯常"
    assert person.get("birth_year") == 1920
