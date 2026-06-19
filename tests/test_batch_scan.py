"""批量图片 OCR 测试。"""

import asyncio
import os
import sys

BACKEND_DIR = os.path.join(os.path.dirname(__file__), "..", "backend")
sys.path.insert(0, BACKEND_DIR)


def test_batch_ocr_merges_pages():
    from agent.batch_scan import run_batch_ocr_pipeline

    calls: list[int] = []

    async def fake_ocr(provider, model, img, prompt):
        calls.append(1)
        page = len(calls)
        return f"第{page}页文字", ""

    result = asyncio.run(
        run_batch_ocr_pipeline(
            ["img1", "img2"],
            ocr_provider="p",
            ocr_model="m",
            ocr_fn=fake_ocr,
        )
    )
    assert result["success"] is True
    assert result["page_count"] == 2
    assert "===== 第 1 页 =====" in result["text"]
    assert "===== 第 2 页 =====" in result["text"]
    assert result["pages_recognized"] == 2
