import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from agent.minimax_client import DEFAULT_CHAT_ENDPOINT, extract_minimax_content, minimax_headers


def test_minimax_headers_use_group_id_header():
    h = minimax_headers("key123", "gid456")
    assert h["Authorization"] == "Bearer key123"
    assert h["GroupId"] == "gid456"


def test_extract_reasoning_content():
    data = {
        "base_resp": {"status_code": 0},
        "choices": [{"message": {"content": "", "reasoning_content": "OK"}}],
    }
    assert extract_minimax_content(data) == "OK"


def test_extract_nested_messages():
    data = {
        "base_resp": {"status_code": 0},
        "choices": [{"messages": [{"content": "识别成功"}]}],
    }
    assert extract_minimax_content(data) == "识别成功"
