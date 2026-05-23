# -*- coding: utf-8 -*-
"""文字版测试"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from agent.relation_text import build_local_relation_description


def test_build_local_relation_description():
    raw = "第一世 张三\n第二世 李四\n张三之子李四"
    text = build_local_relation_description(raw)
    assert "张三" in text
    assert "李四" in text
