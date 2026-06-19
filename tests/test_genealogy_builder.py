"""族谱自动整理引擎测试"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from agent.genealogy_builder import (
    auto_build_genealogy,
    parse_genealogy_text_enhanced,
    dedupe_persons,
    infer_relations_by_generation,
)
from agent.parser import parse_genealogy_text


MULTIGEN_TEXT = """张氏族谱
一世 张公
二世 张子 生1950
三世 孙一 男 生1980
孙二 男 生1985"""


def test_parse_enhanced_multigen():
    result = parse_genealogy_text_enhanced(MULTIGEN_TEXT)
    names = [p["name"] for p in result["persons"]]
    assert "张公" in names
    assert "张子" in names
    assert len(result["persons"]) >= 3


def test_auto_build_infers_parent_child_without_ai_relations():
    persons = [
        {"name": "张公", "generation": 1, "gender": "male"},
        {"name": "张子", "generation": 2, "gender": "male"},
        {"name": "孙一", "generation": 3, "gender": "male"},
    ]
    built = auto_build_genealogy(MULTIGEN_TEXT, persons, [])
    rels = built["relations"]
    pc = [r for r in rels if r.get("type") == "parent_child"]
    assert len(pc) >= 2
    assert built["stats"]["person_count"] >= 3
    assert built["tree"]["root_count"] >= 1


def test_auto_build_from_text_only():
    built = auto_build_genealogy(MULTIGEN_TEXT)
    assert built["success"] is True
    assert built["stats"]["person_count"] >= 2
    assert len(built["tree"]["nodes"]) >= 2


def test_parse_genealogy_text_delegates_enhanced():
    text = """第一代
张三 生于1980 卒于2020
配李四
张五 男"""
    result = parse_genealogy_text(text)
    names = [p["name"] for p in result["persons"]]
    assert "张三" in names


def test_dedupe_persons_merges_fields():
    merged = dedupe_persons([
        {"name": "王五", "generation": 1},
        {"name": "王五", "birth_year": 1980},
    ])
    assert len(merged) == 1
    assert merged[0]["birth_year"] == 1980


def test_infer_relations_by_generation():
    persons = [
        {"name": "父", "generation": 1, "gender": "male"},
        {"name": "子", "generation": 2, "gender": "male"},
    ]
    rels = infer_relations_by_generation(persons)
    assert any(r["from"] == "父" and r["to"] == "子" for r in rels)


def test_agent_generate_api(client):
    res = client.post("/api/agent/generate", json={"text": MULTIGEN_TEXT})
    data = res.json()
    assert data["success"] is True
    assert data["stats"]["person_count"] >= 2
    assert "tree" in data


def test_rebuild_family_adds_relations(client):
    create = client.post("/api/families", json={"name": "陈氏"})
    fid = create.json()["id"]
    client.post("/api/persons/batch", json={
        "family_id": fid,
        "persons": [
            {"name": "陈公", "generation": 1, "gender": "male"},
            {"name": "陈孙", "generation": 2, "gender": "male"},
            {"name": "陈曾", "generation": 3, "gender": "male"},
        ],
        "relations": [],
    })
    rebuild = client.post(f"/api/families/{fid}/rebuild", json={})
    assert rebuild.json()["success"] is True
    tree = client.get(f"/api/families/{fid}/tree").json()
    assert tree["person_count"] >= 3


def test_scan_pipeline_auto_builds_relations():
    import asyncio
    from agent.pipeline import run_scan_pipeline

    async def _ocr(provider, model, image, prompt):
        return MULTIGEN_TEXT, ""

    async def _parse(provider, model, prompt):
        return (
            '{"persons": [{"name": "张公", "generation": 1}, {"name": "张子", "generation": 2}, {"name": "孙一", "generation": 3}], "relations": []}',
            "",
        )

    result = asyncio.run(
        run_scan_pipeline(
            "aGVsbG8=",
            ocr_provider="minimax",
            ocr_model="x",
            parse_provider="minimax",
            parse_model="x",
            ocr_fn=_ocr,
            parse_fn=_parse,
        )
    )
    assert result["success"] is True
    assert result.get("genealogy_stats", {}).get("relation_count", 0) >= 2
    assert len(result.get("relations", [])) >= 2


def test_batch_save_after_generate(client):
    create = client.post("/api/families", json={"name": "刘氏"})
    fid = create.json()["id"]
    built = client.post("/api/agent/generate", json={
        "text": "一世 刘公\n二世 刘子",
    }).json()
    batch = client.post("/api/persons/batch", json={
        "family_id": fid,
        "persons": built["persons"],
        "relations": built["relations"],
    })
    assert batch.json()["relation_count"] >= 1
    tree = client.get(f"/api/families/{fid}/tree").json()
    assert tree["root_count"] >= 1


def test_parse_local_restart_epoch_offset():
    text = "一世 张公\n二世 张子"
    result = parse_genealogy_text_enhanced(
        text,
        generation_scheme="local_restart",
        generation_epoch_offset=15,
    )
    by_name = {p["name"]: p for p in result["persons"]}
    assert by_name["张公"]["source_generation"] == 1
    assert by_name["张公"]["generation"] == 15
    assert by_name["张子"]["source_generation"] == 2
    assert by_name["张子"]["generation"] == 16
