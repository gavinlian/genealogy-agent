"""两阶段解析测试"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from agent.two_stage_parse import run_two_stage_genealogy_parse


async def _mock_parse(prompt):
    if "第一步" in prompt:
        return "一世 张三 男 生1980\n二世 张四 男", ""
    return (
        '{"persons": [{"name": "张三", "gender": "male", "generation": 1}, {"name": "张四", "gender": "male", "generation": 2}], '
        '"relations": [{"from": "张三", "to": "张四", "type": "parent_child"}]}',
        "",
    )


def test_two_stage_parse_returns_relation_description():
    result = asyncio.run(
        run_two_stage_genealogy_parse("张三生1980\n张四男", _mock_parse)
    )
    assert result["success"] is True
    assert "张三" in result["relation_description"]
    assert len(result["persons"]) >= 2
    assert result["used_ai_describe"] is True
    assert result["used_ai_digitize"] is True
