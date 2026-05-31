"""族谱智能体后台定时扫描。"""

from __future__ import annotations

import asyncio
import logging
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from typing import Callable

from agent.agent_config import load_agent_scheduler_defaults
from agent.agent_scanner import run_agent_scan
from agent_discovery_store import ensure_agent_discovery_tables, should_run_scheduled
from user_store import DEFAULT_USER_ID, ensure_default_user

logger = logging.getLogger("genealogy.agent_scheduler")

_get_db: Callable[[], sqlite3.Connection] | None = None
_task: asyncio.Task | None = None


def configure_scheduler(get_db_fn: Callable[[], sqlite3.Connection]) -> None:
    global _get_db
    _get_db = get_db_fn


@contextmanager
def _db_conn():
    if _get_db is None:
        raise RuntimeError("agent scheduler not configured")
    conn = _get_db()
    try:
        yield conn
    finally:
        conn.close()


def _list_active_user_ids(cursor: sqlite3.Cursor) -> list[str]:
    ensure_agent_discovery_tables(cursor)
    ensure_default_user(cursor)
    rows = cursor.execute("SELECT DISTINCT user_id FROM family_memberships").fetchall()
    ids = [r["user_id"] for r in rows if r["user_id"]]
    if DEFAULT_USER_ID not in ids:
        ids.append(DEFAULT_USER_ID)
    return ids or [DEFAULT_USER_ID]


def run_scheduled_scans_for_all_users() -> int:
    """同步执行一轮定时扫描，返回触发用户数。"""
    triggered = 0
    with _db_conn() as conn:
        c = conn.cursor()
        now = datetime.now()
        for uid in _list_active_user_ids(c):
            if should_run_scheduled(c, uid, now):
                try:
                    run_agent_scan(c, uid, trigger="scheduled")
                    conn.commit()
                    triggered += 1
                except Exception:
                    conn.rollback()
                    logger.exception("scheduled agent scan failed for user %s", uid)
    return triggered


async def agent_scheduler_loop() -> None:
    defaults = load_agent_scheduler_defaults()
    interval = max(60, int(defaults.get("check_interval_minutes") or 5) * 60)
    logger.info("agent scheduler started, check every %ss", interval)
    while True:
        try:
            await asyncio.to_thread(run_scheduled_scans_for_all_users)
        except Exception:
            logger.exception("agent scheduler tick failed")
        await asyncio.sleep(interval)


def start_agent_scheduler() -> asyncio.Task | None:
    global _task
    if _get_db is None:
        return None
    if _task and not _task.done():
        return _task
    _task = asyncio.create_task(agent_scheduler_loop())
    return _task


async def stop_agent_scheduler() -> None:
    global _task
    if _task and not _task.done():
        _task.cancel()
        try:
            await _task
        except asyncio.CancelledError:
            pass
    _task = None
