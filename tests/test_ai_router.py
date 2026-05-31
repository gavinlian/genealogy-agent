"""AI 路由与额度测试"""

import os
import sqlite3
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from agent.ai_plans import load_ai_plans, get_plan_limits  # noqa: E402
from agent.ai_quota import (  # noqa: E402
    ensure_ai_usage_table,
    get_quota_bucket,
    pick_tier,
    record_usage,
)
from agent.ai_router import resolve_route, is_platform_available  # noqa: E402


def _memory_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute(
        """CREATE TABLE ai_settings (
            id TEXT PRIMARY KEY, ocr_provider TEXT, ocr_model TEXT,
            parse_provider TEXT, parse_model TEXT, updated_at TEXT,
            routing_mode TEXT DEFAULT 'auto', ocr_tier TEXT DEFAULT 'auto',
            parse_tier TEXT DEFAULT 'auto', user_plan TEXT DEFAULT 'free')"""
    )
    c.execute(
        """INSERT INTO ai_settings VALUES
        ('default', 'minimax', 'MiniMax-M2.7', 'minimax', 'MiniMax-M2.7', 'now',
         'auto', 'auto', 'auto', 'free')"""
    )
    ensure_ai_usage_table(c)
    conn.commit()
    return conn


AI_PROVIDERS_STUB = {
    "siliconflow": {"supports_vision": True, "text_model": "t", "text_models": ["t"]},
    "minimax": {"supports_vision": True, "text_model": "t", "text_models": ["t"]},
    "deepseek": {"supports_vision": False, "text_model": "t", "text_models": ["t"]},
}


def _configured(provider_id: str) -> bool:
    return provider_id == "minimax"


class TestAiPlans(unittest.TestCase):
    def test_load_plans_has_free_tier(self):
        load_ai_plans.cache_clear()
        limits = get_plan_limits("free")
        self.assertIn("ocr", limits)
        self.assertGreater(limits["parse"]["fast"], 0)


class TestAiQuota(unittest.TestCase):
    def setUp(self):
        self.conn = _memory_db()
        self.c = self.conn.cursor()

    def tearDown(self):
        self.conn.close()

    def test_record_and_count_usage(self):
        record_usage(self.c, "u1", "parse", "fast", "siliconflow", "platform")
        self.conn.commit()
        bucket = get_quota_bucket(self.c, "u1", "parse", "fast")
        self.assertEqual(bucket["used"], 1)
        self.assertGreater(bucket["limit"], 0)

    def test_pick_tier_prefers_fast(self):
        tier, wait = pick_tier(self.c, "u1", "parse", "auto")
        self.assertEqual(tier, "fast")
        self.assertEqual(wait, 0)


class TestAiRouter(unittest.TestCase):
    def setUp(self):
        self.conn = _memory_db()
        self.c = self.conn.cursor()

    def tearDown(self):
        self.conn.close()

    def test_auto_byok_parse_when_no_platform(self):
        with patch.dict(os.environ, {}, clear=True):
            load_ai_plans.cache_clear()
            routed = resolve_route(
                self.c,
                "parse",
                "u1",
                ai_providers=AI_PROVIDERS_STUB,
                is_configured_fn=_configured,
                load_selection_fn=lambda: {
                    "ocr": {"provider": "minimax", "model": "m"},
                    "parse": {"provider": "minimax", "model": "m"},
                },
            )
        self.assertEqual(routed["provider"], "minimax")
        self.assertEqual(routed["source"], "byok")

    def test_auto_parse_local_fallback_without_keys(self):
        with patch.dict(os.environ, {}, clear=True):
            load_ai_plans.cache_clear()
            routed = resolve_route(
                self.c,
                "parse",
                "u1",
                ai_providers=AI_PROVIDERS_STUB,
                is_configured_fn=lambda _p: False,
                load_selection_fn=lambda: {
                    "ocr": {"provider": "minimax", "model": "m"},
                    "parse": {"provider": "minimax", "model": "m"},
                },
            )
        self.assertTrue(routed["fallback_local"])

    def test_platform_route_when_env_key_set(self):
        with patch.dict(os.environ, {"PLATFORM_AI_API_KEY": "sk-test"}, clear=False):
            load_ai_plans.cache_clear()
            self.assertTrue(is_platform_available())
            routed = resolve_route(
                self.c,
                "parse",
                "u1",
                ai_providers=AI_PROVIDERS_STUB,
                is_configured_fn=lambda _p: False,
                load_selection_fn=lambda: {
                    "ocr": {"provider": "minimax", "model": "m"},
                    "parse": {"provider": "minimax", "model": "m"},
                },
            )
        self.assertEqual(routed["source"], "platform")
        self.assertEqual(routed["provider"], "siliconflow")


if __name__ == "__main__":
    unittest.main()
