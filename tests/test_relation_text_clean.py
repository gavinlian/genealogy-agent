"""关系描述稿清洗测试"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from agent.relation_text import clean_relation_description


def test_clean_relation_description_strips_meta_lines():
    raw = """根据 OCR 原文分析如下：

一世 张公 男 配李氏 子张三
二世 张三 男

【说明】以上为整理结果"""
    out = clean_relation_description(raw)
    assert "张公" in out
    assert "张三" in out
    assert "根据 OCR" not in out
    assert "【说明】" not in out


def test_clean_relation_description_keeps_relation_block():
    raw = """一世 张公 男

【关系】
张公 配 李氏
张公 → 张三（父子）"""
    out = clean_relation_description(raw)
    assert "【关系】" in out
    assert "张公 配 李氏" in out
