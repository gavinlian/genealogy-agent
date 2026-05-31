"""族谱智能体：发现队列、扫描记录、大库快照、用户调度设置。"""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timedelta
from typing import Any

from agent.agent_config import merge_schedule_settings


def _now() -> str:
    return datetime.now().isoformat()


def ensure_agent_discovery_tables(cursor: sqlite3.Cursor) -> None:
    cursor.execute(
        """CREATE TABLE IF NOT EXISTS agent_schedule_settings (
            user_id TEXT PRIMARY KEY,
            enabled INTEGER DEFAULT 1,
            daily_run_times TEXT,
            on_open_max_hours INTEGER DEFAULT 48,
            compare_owned_families INTEGER DEFAULT 1,
            compare_followed_families INTEGER DEFAULT 1,
            compare_snapshots INTEGER DEFAULT 1,
            min_match_confidence REAL DEFAULT 0.62,
            last_run_at TEXT,
            last_open_scan_at TEXT,
            updated_at TEXT
        )"""
    )
    cursor.execute(
        """CREATE TABLE IF NOT EXISTS agent_discoveries (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            family_id TEXT NOT NULL,
            discovery_type TEXT NOT NULL,
            title TEXT NOT NULL,
            summary TEXT,
            evidence_json TEXT,
            plan_json TEXT,
            confidence REAL DEFAULT 0.5,
            status TEXT DEFAULT 'pending',
            source_family_id TEXT,
            source_snapshot_id TEXT,
            fingerprint TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT
        )"""
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_agent_disc_user ON agent_discoveries(user_id, status)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_agent_disc_family ON agent_discoveries(family_id, status)"
    )
    cursor.execute(
        """CREATE TABLE IF NOT EXISTS agent_scan_runs (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            trigger TEXT NOT NULL,
            started_at TEXT NOT NULL,
            finished_at TEXT,
            families_scanned INTEGER DEFAULT 0,
            discoveries_new INTEGER DEFAULT 0,
            summary TEXT
        )"""
    )
    cursor.execute(
        """CREATE TABLE IF NOT EXISTS genealogy_snapshots (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            name TEXT NOT NULL,
            description TEXT,
            archive_json TEXT NOT NULL,
            person_count INTEGER DEFAULT 0,
            relation_count INTEGER DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT
        )"""
    )


def _row_settings(row: sqlite3.Row | None) -> dict[str, Any]:
    base = merge_schedule_settings(None)
    if not row:
        return base
    data = dict(row)
    times_raw = data.get("daily_run_times")
    if times_raw:
        try:
            data["daily_run_times"] = json.loads(times_raw)
        except json.JSONDecodeError:
            data["daily_run_times"] = base["daily_run_times"]
    else:
        data["daily_run_times"] = base["daily_run_times"]
    data["enabled"] = bool(data.get("enabled", 1))
    data["compare_owned_families"] = bool(data.get("compare_owned_families", 1))
    data["compare_followed_families"] = bool(data.get("compare_followed_families", 1))
    data["compare_snapshots"] = bool(data.get("compare_snapshots", 1))
    return merge_schedule_settings(data)


def get_schedule_settings(cursor: sqlite3.Cursor, user_id: str) -> dict[str, Any]:
    ensure_agent_discovery_tables(cursor)
    row = cursor.execute(
        "SELECT * FROM agent_schedule_settings WHERE user_id = ?",
        (user_id,),
    ).fetchone()
    settings = _row_settings(row)
    settings["last_run_at"] = dict(row)["last_run_at"] if row else None
    settings["last_open_scan_at"] = dict(row)["last_open_scan_at"] if row else None
    return settings


def save_schedule_settings(cursor: sqlite3.Cursor, user_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    ensure_agent_discovery_tables(cursor)
    current = get_schedule_settings(cursor, user_id)
    merged = merge_schedule_settings({**current, **payload})
    now = _now()
    times = merged.get("daily_run_times") or []
    if not isinstance(times, list):
        times = []
    times = [str(t).strip() for t in times if str(t).strip()]
    on_open_hours = int(merged.get("on_open_max_hours") or 48)
    on_open_hours = max(1, min(168, on_open_hours))
    confidence = float(merged.get("min_match_confidence") or 0.62)
    confidence = max(0.3, min(1.0, confidence))
    cursor.execute(
        """INSERT INTO agent_schedule_settings
           (user_id, enabled, daily_run_times, on_open_max_hours,
            compare_owned_families, compare_followed_families, compare_snapshots,
            min_match_confidence, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(user_id) DO UPDATE SET
             enabled=excluded.enabled,
             daily_run_times=excluded.daily_run_times,
             on_open_max_hours=excluded.on_open_max_hours,
             compare_owned_families=excluded.compare_owned_families,
             compare_followed_families=excluded.compare_followed_families,
             compare_snapshots=excluded.compare_snapshots,
             min_match_confidence=excluded.min_match_confidence,
             updated_at=excluded.updated_at""",
        (
            user_id,
            1 if merged.get("enabled", True) else 0,
            json.dumps(times, ensure_ascii=False),
            on_open_hours,
            1 if merged.get("compare_owned_families", True) else 0,
            1 if merged.get("compare_followed_families", True) else 0,
            1 if merged.get("compare_snapshots", True) else 0,
            confidence,
            now,
        ),
    )
    return get_schedule_settings(cursor, user_id)


def touch_scan_run(cursor: sqlite3.Cursor, user_id: str, *, field: str = "last_run_at") -> None:
    ensure_agent_discovery_tables(cursor)
    if field not in ("last_run_at", "last_open_scan_at"):
        return
    now = _now()
    row = cursor.execute(
        "SELECT user_id FROM agent_schedule_settings WHERE user_id = ?",
        (user_id,),
    ).fetchone()
    if row:
        cursor.execute(
            f"UPDATE agent_schedule_settings SET {field} = ?, updated_at = ? WHERE user_id = ?",
            (now, now, user_id),
        )
    else:
        save_schedule_settings(cursor, user_id, {})
        cursor.execute(
            f"UPDATE agent_schedule_settings SET {field} = ?, updated_at = ? WHERE user_id = ?",
            (now, now, user_id),
        )


def should_run_on_open(cursor: sqlite3.Cursor, user_id: str) -> bool:
    settings = get_schedule_settings(cursor, user_id)
    if not settings.get("enabled"):
        return False
    last = settings.get("last_open_scan_at") or settings.get("last_run_at")
    if not last:
        return True
    try:
        last_dt = datetime.fromisoformat(last)
    except ValueError:
        return True
    max_hours = int(settings.get("on_open_max_hours") or 48)
    return datetime.now() - last_dt >= timedelta(hours=max_hours)


def should_run_scheduled(cursor: sqlite3.Cursor, user_id: str, now: datetime | None = None) -> bool:
    settings = get_schedule_settings(cursor, user_id)
    if not settings.get("enabled"):
        return False
    now = now or datetime.now()
    times = settings.get("daily_run_times") or []
    if not times:
        return False
    last_run = settings.get("last_run_at")
    last_dt = None
    if last_run:
        try:
            last_dt = datetime.fromisoformat(last_run)
        except ValueError:
            last_dt = None
    for slot in times:
        parts = str(slot).strip().split(":")
        if len(parts) < 2:
            continue
        try:
            hour, minute = int(parts[0]), int(parts[1])
        except ValueError:
            continue
        scheduled = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if now < scheduled:
            continue
        if last_dt and last_dt >= scheduled:
            continue
        return True
    return False


def _discovery_fingerprint(payload: dict[str, Any]) -> str:
    parts = [
        payload.get("discovery_type") or "",
        payload.get("family_id") or "",
        payload.get("source_family_id") or "",
        payload.get("source_snapshot_id") or "",
        payload.get("title") or "",
    ]
    ev = payload.get("evidence") or {}
    if isinstance(ev, dict):
        parts.append(str(ev.get("person_name") or ""))
        parts.append(str(ev.get("match_name") or ""))
    return "|".join(parts)


def upsert_discovery(cursor: sqlite3.Cursor, user_id: str, payload: dict[str, Any]) -> str | None:
    ensure_agent_discovery_tables(cursor)
    fp = payload.get("fingerprint") or _discovery_fingerprint(payload)
    existing = cursor.execute(
        """SELECT id FROM agent_discoveries
           WHERE user_id = ? AND fingerprint = ? AND status = 'pending'""",
        (user_id, fp),
    ).fetchone()
    now = _now()
    evidence = payload.get("evidence")
    plan = payload.get("plan")
    if existing:
        cursor.execute(
            """UPDATE agent_discoveries SET
               title=?, summary=?, evidence_json=?, plan_json=?, confidence=?, updated_at=?
               WHERE id=?""",
            (
                payload.get("title") or "",
                payload.get("summary") or "",
                json.dumps(evidence, ensure_ascii=False) if evidence else None,
                json.dumps(plan, ensure_ascii=False) if plan else None,
                float(payload.get("confidence") or 0.5),
                now,
                existing["id"],
            ),
        )
        return existing["id"]

    did = str(uuid.uuid4())[:12]
    cursor.execute(
        """INSERT INTO agent_discoveries
           (id, user_id, family_id, discovery_type, title, summary,
            evidence_json, plan_json, confidence, status,
            source_family_id, source_snapshot_id, fingerprint, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?, ?, ?)""",
        (
            did,
            user_id,
            payload.get("family_id") or "",
            payload.get("discovery_type") or "unknown",
            payload.get("title") or "新发现",
            payload.get("summary") or "",
            json.dumps(evidence, ensure_ascii=False) if evidence else None,
            json.dumps(plan, ensure_ascii=False) if plan else None,
            float(payload.get("confidence") or 0.5),
            payload.get("source_family_id"),
            payload.get("source_snapshot_id"),
            fp,
            now,
            now,
        ),
    )
    return did


def list_discoveries(
    cursor: sqlite3.Cursor,
    user_id: str,
    *,
    family_id: str | None = None,
    status: str | None = "pending",
    limit: int = 100,
) -> list[dict[str, Any]]:
    ensure_agent_discovery_tables(cursor)
    sql = "SELECT * FROM agent_discoveries WHERE user_id = ?"
    params: list[Any] = [user_id]
    if family_id:
        sql += " AND family_id = ?"
        params.append(family_id)
    if status:
        sql += " AND status = ?"
        params.append(status)
    sql += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)
    rows = cursor.execute(sql, params).fetchall()
    out: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        for key in ("evidence_json", "plan_json"):
            raw = item.pop(key, None)
            if raw:
                try:
                    item[key.replace("_json", "")] = json.loads(raw)
                except json.JSONDecodeError:
                    item[key.replace("_json", "")] = {}
        out.append(item)
    return out


def count_pending_discoveries(cursor: sqlite3.Cursor, user_id: str, family_id: str | None = None) -> int:
    ensure_agent_discovery_tables(cursor)
    if family_id:
        row = cursor.execute(
            "SELECT COUNT(*) AS c FROM agent_discoveries WHERE user_id = ? AND family_id = ? AND status = 'pending'",
            (user_id, family_id),
        ).fetchone()
    else:
        row = cursor.execute(
            "SELECT COUNT(*) AS c FROM agent_discoveries WHERE user_id = ? AND status = 'pending'",
            (user_id,),
        ).fetchone()
    return int(row["c"]) if row else 0


def update_discovery_status(cursor: sqlite3.Cursor, discovery_id: str, user_id: str, status: str) -> bool:
    ensure_agent_discovery_tables(cursor)
    cur = cursor.execute(
        "UPDATE agent_discoveries SET status = ?, updated_at = ? WHERE id = ? AND user_id = ?",
        (status, _now(), discovery_id, user_id),
    )
    return cur.rowcount > 0


def get_discovery(cursor: sqlite3.Cursor, discovery_id: str, user_id: str) -> dict[str, Any] | None:
    ensure_agent_discovery_tables(cursor)
    row = cursor.execute(
        "SELECT * FROM agent_discoveries WHERE id = ? AND user_id = ?",
        (discovery_id, user_id),
    ).fetchone()
    if not row:
        return None
    item = dict(row)
    for key in ("evidence_json", "plan_json"):
        raw = item.pop(key, None)
        if raw:
            try:
                item[key.replace("_json", "")] = json.loads(raw)
            except json.JSONDecodeError:
                item[key.replace("_json", "")] = {}
    return item


def start_scan_run(cursor: sqlite3.Cursor, user_id: str, trigger: str) -> str:
    ensure_agent_discovery_tables(cursor)
    rid = str(uuid.uuid4())[:12]
    cursor.execute(
        """INSERT INTO agent_scan_runs (id, user_id, trigger, started_at)
           VALUES (?, ?, ?, ?)""",
        (rid, user_id, trigger, _now()),
    )
    return rid


def finish_scan_run(
    cursor: sqlite3.Cursor,
    run_id: str,
    *,
    families_scanned: int,
    discoveries_new: int,
    summary: str,
) -> None:
    cursor.execute(
        """UPDATE agent_scan_runs SET finished_at=?, families_scanned=?, discoveries_new=?, summary=?
           WHERE id=?""",
        (_now(), families_scanned, discoveries_new, summary, run_id),
    )


def get_last_scan_run(cursor: sqlite3.Cursor, user_id: str) -> dict[str, Any] | None:
    ensure_agent_discovery_tables(cursor)
    row = cursor.execute(
        """SELECT * FROM agent_scan_runs WHERE user_id = ?
           ORDER BY started_at DESC LIMIT 1""",
        (user_id,),
    ).fetchone()
    return dict(row) if row else None


def list_snapshots(cursor: sqlite3.Cursor, user_id: str) -> list[dict[str, Any]]:
    ensure_agent_discovery_tables(cursor)
    rows = cursor.execute(
        "SELECT id, user_id, name, description, person_count, relation_count, created_at, updated_at FROM genealogy_snapshots WHERE user_id = ? ORDER BY created_at DESC",
        (user_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_snapshot(cursor: sqlite3.Cursor, snapshot_id: str, user_id: str) -> dict[str, Any] | None:
    ensure_agent_discovery_tables(cursor)
    row = cursor.execute(
        "SELECT * FROM genealogy_snapshots WHERE id = ? AND user_id = ?",
        (snapshot_id, user_id),
    ).fetchone()
    if not row:
        return None
    item = dict(row)
    try:
        item["archive"] = json.loads(item.pop("archive_json") or "{}")
    except json.JSONDecodeError:
        item["archive"] = {}
    return item


def create_snapshot(cursor: sqlite3.Cursor, user_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    ensure_agent_discovery_tables(cursor)
    archive = payload.get("archive") or payload
    persons = (archive.get("persons") or archive.get("archive", {}).get("persons") or [])
    relations = (archive.get("relations") or archive.get("archive", {}).get("relations") or [])
    sid = str(uuid.uuid4())[:12]
    now = _now()
    cursor.execute(
        """INSERT INTO genealogy_snapshots
           (id, user_id, name, description, archive_json, person_count, relation_count, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            sid,
            user_id,
            (payload.get("name") or "大库快照").strip(),
            (payload.get("description") or "").strip(),
            json.dumps(archive, ensure_ascii=False),
            len(persons),
            len(relations),
            now,
            now,
        ),
    )
    return get_snapshot(cursor, sid, user_id) or {"id": sid}


def delete_snapshot(cursor: sqlite3.Cursor, snapshot_id: str, user_id: str) -> bool:
    ensure_agent_discovery_tables(cursor)
    cur = cursor.execute(
        "DELETE FROM genealogy_snapshots WHERE id = ? AND user_id = ?",
        (snapshot_id, user_id),
    )
    return cur.rowcount > 0
