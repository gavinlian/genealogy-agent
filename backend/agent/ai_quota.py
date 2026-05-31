"""AI 用量与月度额度（免费 / Pro）。"""

from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime
from typing import Any

from agent.ai_plans import get_plan, get_plan_limits, load_ai_plans


def ensure_ai_usage_table(cursor: sqlite3.Cursor) -> None:
    cursor.execute(
        """CREATE TABLE IF NOT EXISTS ai_usage (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            task TEXT NOT NULL,
            tier TEXT NOT NULL,
            provider TEXT,
            source TEXT,
            created_at TEXT NOT NULL
        )"""
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_ai_usage_user_created ON ai_usage(user_id, created_at)"
    )


def month_start_iso() -> str:
    now = datetime.now()
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()


def count_usage(
    cursor: sqlite3.Cursor,
    user_id: str,
    task: str,
    tier: str,
    *,
    since: str | None = None,
) -> int:
    since = since or month_start_iso()
    row = cursor.execute(
        """SELECT COUNT(*) AS cnt FROM ai_usage
           WHERE user_id = ? AND task = ? AND tier = ? AND created_at >= ?""",
        (user_id, task, tier, since),
    ).fetchone()
    return int(row["cnt"]) if row else 0


def get_quota_bucket(
    cursor: sqlite3.Cursor,
    user_id: str,
    task: str,
    tier: str,
    plan_id: str = "free",
) -> dict[str, Any]:
    limits = get_plan_limits(plan_id)
    task_limits = limits.get(task) or {}
    limit = int(task_limits.get(tier) or 0)
    used = count_usage(cursor, user_id, task, tier)
    remaining = max(0, limit - used)
    return {
        "task": task,
        "tier": tier,
        "used": used,
        "limit": limit,
        "remaining": remaining,
        "reset_at": month_start_iso(),
    }


def get_quota_summary(
    cursor: sqlite3.Cursor,
    user_id: str,
    plan_id: str = "free",
) -> dict[str, Any]:
    plan = get_plan(plan_id)
    cfg = load_ai_plans()
    pro_plan = (cfg.get("plans") or {}).get("pro") or {}
    buckets: dict[str, dict[str, Any]] = {}
    for task in ("ocr", "parse", "agent"):
        for tier in ("fast", "slow"):
            key = f"{task}_{tier}"
            buckets[key] = get_quota_bucket(cursor, user_id, task, tier, plan_id)
    return {
        "plan_id": plan_id,
        "plan_label": plan.get("label") or plan_id,
        "plan_description": plan.get("description") or "",
        "pro_coming_soon": bool(pro_plan.get("coming_soon")),
        "pro_price_monthly_cny": pro_plan.get("price_monthly_cny"),
        "buckets": buckets,
        "reset_at": month_start_iso(),
    }


def pick_tier(
    cursor: sqlite3.Cursor,
    user_id: str,
    task: str,
    preferred: str,
    plan_id: str = "free",
) -> tuple[str, int]:
    """返回实际使用的 tier 与模拟排队毫秒数。"""
    if preferred in ("fast", "slow"):
        bucket = get_quota_bucket(cursor, user_id, task, preferred, plan_id)
        if bucket["remaining"] > 0 or bucket["limit"] == 0:
            wait_ms = _queue_wait_ms(bucket) if preferred == "slow" else 0
            return preferred, wait_ms
        if preferred == "fast":
            slow = get_quota_bucket(cursor, user_id, task, "slow", plan_id)
            if slow["remaining"] > 0 or slow["limit"] == 0:
                return "slow", _queue_wait_ms(slow)
        return preferred, 0

    fast = get_quota_bucket(cursor, user_id, task, "fast", plan_id)
    if fast["remaining"] > 0 or fast["limit"] == 0:
        return "fast", 0
    slow = get_quota_bucket(cursor, user_id, task, "slow", plan_id)
    if slow["remaining"] > 0 or slow["limit"] == 0:
        return "slow", _queue_wait_ms(slow)
    return "slow", _queue_wait_ms(slow)


def _queue_wait_ms(bucket: dict[str, Any]) -> int:
    limit = int(bucket.get("limit") or 0)
    used = int(bucket.get("used") or 0)
    if limit <= 0:
        return 0
    ratio = min(1.0, used / limit)
    return int(min(8000, 500 + ratio * 4500))


def can_use_platform_quota(
    cursor: sqlite3.Cursor,
    user_id: str,
    task: str,
    tier: str,
    plan_id: str = "free",
) -> bool:
    bucket = get_quota_bucket(cursor, user_id, task, tier, plan_id)
    if bucket["limit"] == 0:
        return True
    return bucket["remaining"] > 0


def record_usage(
    cursor: sqlite3.Cursor,
    user_id: str,
    task: str,
    tier: str,
    provider: str,
    source: str,
) -> None:
    cursor.execute(
        """INSERT INTO ai_usage (id, user_id, task, tier, provider, source, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (str(uuid.uuid4()), user_id, task, tier, provider, source, datetime.now().isoformat()),
    )
