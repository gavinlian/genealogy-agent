"""LLM 响应解析测试"""

import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from agent.llm_utils import extract_anthropic_text


def test_extract_anthropic_text_skips_thinking():
    message = SimpleNamespace(
        content=[
            SimpleNamespace(type="thinking", thinking="内部推理", text=None),
            SimpleNamespace(type="text", text='{"persons": []}'),
        ]
    )
    assert extract_anthropic_text(message) == '{"persons": []}'


def test_extract_anthropic_text_multiple_text_blocks():
    message = SimpleNamespace(
        content=[
            SimpleNamespace(type="text", text='{"persons": ['),
            SimpleNamespace(type="text", text='], "relations": []}'),
        ]
    )
    assert '"persons"' in extract_anthropic_text(message)
