"""扫描流水线测试（mock AI，不调用真实 API）"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from agent.pipeline import run_scan_pipeline

FAKE_IMAGE = "aGVsbG8="  # base64 of "hello"


async def _mock_ocr_ok(provider, model, image, prompt):
    return "张三生1980\n张四男", ""


async def _mock_parse_ok(provider, model, prompt):
    if "第一步" in prompt or "关系描述稿" in prompt:
        return (
            "一世 张三 男 生1980\n一世 张四 男",
            "",
        )
    return (
        '{"persons": [{"name": "张三", "gender": "male", "birth_year": 1980, "death_year": null, "generation": 1}, {"name": "张四", "gender": "male", "generation": 1}], "relations": []}',
        "",
    )


async def _mock_ocr_fail(provider, model, image, prompt):
    return "", "未配置 API Key"


def test_scan_pipeline_success():
    result = asyncio.run(
        run_scan_pipeline(
            FAKE_IMAGE,
            ocr_provider="minimax",
            ocr_model="MiniMax-M2.7",
            parse_provider="minimax",
            parse_model="MiniMax-M2.7",
            ocr_fn=_mock_ocr_ok,
            parse_fn=_mock_parse_ok,
        )
    )
    assert result["success"] is True
    assert result["step"] == "complete"
    assert len(result["persons"]) >= 1
    assert "validation" in result


def test_scan_pipeline_ocr_failure():
    result = asyncio.run(
        run_scan_pipeline(
            FAKE_IMAGE,
            ocr_provider="minimax",
            ocr_model="MiniMax-M2.7",
            parse_provider="minimax",
            parse_model="MiniMax-M2.7",
            ocr_fn=_mock_ocr_fail,
            parse_fn=_mock_parse_ok,
        )
    )
    assert result["success"] is False
    assert result["step"] == "ocr"
