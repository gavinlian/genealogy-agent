"""族谱原文版本管理"""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime
from typing import Any


def _now() -> str:
    return datetime.now().isoformat()


def _parse_annotations(raw: Any) -> str:
    if raw is None:
        return "[]"
    if isinstance(raw, str):
        return raw or "[]"
    return json.dumps(raw, ensure_ascii=False)


def _row_to_version(row: sqlite3.Row | dict) -> dict:
    data = dict(row)
    ann = data.get("source_annotations") or "[]"
    try:
        data["source_annotations"] = json.loads(ann) if isinstance(ann, str) else ann
    except json.JSONDecodeError:
        data["source_annotations"] = []
    return data


def ensure_versions_table(cursor: sqlite3.Cursor) -> None:
    cursor.execute(
        """CREATE TABLE IF NOT EXISTS family_source_versions (
            id TEXT PRIMARY KEY,
            family_id TEXT NOT NULL,
            version_no INTEGER NOT NULL,
            label TEXT,
            source_text TEXT NOT NULL DEFAULT '',
            source_annotations TEXT DEFAULT '[]',
            status TEXT DEFAULT 'draft',
            note TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT,
            UNIQUE(family_id, version_no)
        )"""
    )
    try:
        cursor.execute("ALTER TABLE families ADD COLUMN active_source_version_id TEXT")
    except sqlite3.OperationalError:
        pass


def get_active_source_for_family(cursor: sqlite3.Cursor, family_id: str) -> tuple[str, dict | None]:
    """返回 (原文, 活跃版本信息)。优先已确认/活跃版本，否则 families.source_text。"""
    migrate_legacy_family_source(cursor, family_id)
    payload = list_source_versions(cursor, family_id)
    active_id = payload.get("active_version_id")
    version = None
    if active_id:
        version = get_source_version(cursor, family_id, active_id)
    if not version and payload.get("versions"):
        confirmed = [v for v in payload["versions"] if v.get("status") == "confirmed"]
        version = confirmed[-1] if confirmed else payload["versions"][-1]
    if version and (version.get("source_text") or "").strip():
        return version["source_text"], version
    row = cursor.execute(
        "SELECT source_text FROM families WHERE id = ?",
        (family_id,),
    ).fetchone()
    text = (row["source_text"] or "") if row else ""
    return text, version


def migrate_legacy_family_source(cursor: sqlite3.Cursor, family_id: str) -> str | None:
    """将 families 表中的旧原文迁移为第 1 版。返回 active version id。"""
    ensure_versions_table(cursor)
    existing = cursor.execute(
        "SELECT COUNT(*) AS c FROM family_source_versions WHERE family_id = ?",
        (family_id,),
    ).fetchone()
    if existing and existing["c"]:
        active = cursor.execute(
            "SELECT active_source_version_id FROM families WHERE id = ?",
            (family_id,),
        ).fetchone()
        if active and active["active_source_version_id"]:
            return active["active_source_version_id"]
        latest = cursor.execute(
            """SELECT id FROM family_source_versions
               WHERE family_id = ? ORDER BY version_no DESC LIMIT 1""",
            (family_id,),
        ).fetchone()
        if latest:
            vid = latest["id"]
            cursor.execute(
                "UPDATE families SET active_source_version_id = ? WHERE id = ?",
                (vid, family_id),
            )
            return vid
        return None

    row = cursor.execute(
        "SELECT source_text, source_annotations FROM families WHERE id = ?",
        (family_id,),
    ).fetchone()
    if not row:
        return None
    text = (row["source_text"] or "").strip()
    if not text:
        return None
    return create_source_version(
        cursor,
        family_id,
        source_text=row["source_text"] or "",
        source_annotations=row["source_annotations"] or "[]",
        label="第1版 · OCR 原始",
        status="confirmed",
        set_active=True,
    )


def list_source_versions(cursor: sqlite3.Cursor, family_id: str) -> dict:
    migrate_legacy_family_source(cursor, family_id)
    rows = cursor.execute(
        """SELECT * FROM family_source_versions
           WHERE family_id = ? ORDER BY version_no ASC""",
        (family_id,),
    ).fetchall()
    family = cursor.execute(
        "SELECT active_source_version_id FROM families WHERE id = ?",
        (family_id,),
    ).fetchone()
    versions = [_row_to_version(r) for r in rows]
    active_id = family["active_source_version_id"] if family else None
    if not active_id and versions:
        active_id = versions[-1]["id"]
    return {"versions": versions, "active_version_id": active_id}


def get_source_version(cursor: sqlite3.Cursor, family_id: str, version_id: str) -> dict | None:
    row = cursor.execute(
        "SELECT * FROM family_source_versions WHERE id = ? AND family_id = ?",
        (version_id, family_id),
    ).fetchone()
    return _row_to_version(row) if row else None


def _next_version_no(cursor: sqlite3.Cursor, family_id: str) -> int:
    row = cursor.execute(
        "SELECT MAX(version_no) AS m FROM family_source_versions WHERE family_id = ?",
        (family_id,),
    ).fetchone()
    return int((row["m"] or 0) + 1)


def _sync_family_from_version(cursor: sqlite3.Cursor, family_id: str, version_id: str) -> None:
    row = cursor.execute(
        "SELECT source_text, source_annotations FROM family_source_versions WHERE id = ?",
        (version_id,),
    ).fetchone()
    if not row:
        return
    cursor.execute(
        """UPDATE families SET source_text=?, source_annotations=?,
           active_source_version_id=?, updated_at=? WHERE id=?""",
        (row["source_text"], row["source_annotations"], version_id, _now(), family_id),
    )


def create_source_version(
    cursor: sqlite3.Cursor,
    family_id: str,
    *,
    source_text: str = "",
    source_annotations: Any = "[]",
    label: str | None = None,
    status: str = "draft",
    note: str | None = None,
    set_active: bool = False,
) -> str:
    ensure_versions_table(cursor)
    version_no = _next_version_no(cursor, family_id)
    if not label:
        if version_no == 1:
            label = "第1版 · OCR 原始"
        else:
            label = f"第{version_no}版"
    vid = str(uuid.uuid4())[:8]
    now = _now()
    ann = _parse_annotations(source_annotations)
    cursor.execute(
        """INSERT INTO family_source_versions (
            id, family_id, version_no, label, source_text, source_annotations,
            status, note, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (vid, family_id, version_no, label, source_text or "", ann, status, note, now, now),
    )
    if set_active or status == "confirmed":
        _sync_family_from_version(cursor, family_id, vid)
    return vid


def update_source_version(
    cursor: sqlite3.Cursor,
    family_id: str,
    version_id: str,
    *,
    source_text: str | None = None,
    source_annotations: Any = None,
    label: str | None = None,
    note: str | None = None,
) -> dict | None:
    row = cursor.execute(
        "SELECT * FROM family_source_versions WHERE id = ? AND family_id = ?",
        (version_id, family_id),
    ).fetchone()
    if not row:
        return None
    now = _now()
    text = source_text if source_text is not None else row["source_text"]
    ann = _parse_annotations(source_annotations) if source_annotations is not None else row["source_annotations"]
    lbl = label if label is not None else row["label"]
    nte = note if note is not None else row["note"]
    cursor.execute(
        """UPDATE family_source_versions SET source_text=?, source_annotations=?,
           label=?, note=?, updated_at=? WHERE id=?""",
        (text, ann, lbl, nte, now, version_id),
    )
    family = cursor.execute(
        "SELECT active_source_version_id FROM families WHERE id = ?",
        (family_id,),
    ).fetchone()
    if family and family["active_source_version_id"] == version_id:
        _sync_family_from_version(cursor, family_id, version_id)
    return get_source_version(cursor, family_id, version_id)


def confirm_source_version(cursor: sqlite3.Cursor, family_id: str, version_id: str) -> dict | None:
    row = cursor.execute(
        "SELECT id FROM family_source_versions WHERE id = ? AND family_id = ?",
        (version_id, family_id),
    ).fetchone()
    if not row:
        return None
    now = _now()
    cursor.execute(
        "UPDATE family_source_versions SET status='confirmed', updated_at=? WHERE id=?",
        (now, version_id),
    )
    _sync_family_from_version(cursor, family_id, version_id)
    return get_source_version(cursor, family_id, version_id)


def set_active_source_version(cursor: sqlite3.Cursor, family_id: str, version_id: str) -> dict | None:
    row = cursor.execute(
        "SELECT id FROM family_source_versions WHERE id = ? AND family_id = ?",
        (version_id, family_id),
    ).fetchone()
    if not row:
        return None
    _sync_family_from_version(cursor, family_id, version_id)
    return get_source_version(cursor, family_id, version_id)


TEXT_EDITION_NOTE_PREFIX = "text_from:"


def upsert_text_edition_from_source(
    cursor: sqlite3.Cursor,
    family_id: str,
    source_version_id: str,
    relation_text: str,
    *,
    set_active: bool = False,
) -> dict:
    """基于指定原文版本生成/更新「文字版」草稿；默认不切换当前选中版本。"""
    src = get_source_version(cursor, family_id, source_version_id)
    if not src:
        raise ValueError("原文版本不存在")
    note = f"{TEXT_EDITION_NOTE_PREFIX}{source_version_id}"
    src_label = src.get("label") or f"第{src.get('version_no', 1)}版"
    label = f"文字版 · {src_label}"
    text = (relation_text or "").strip()
    if not text:
        raise ValueError("无法生成文字版内容")

    existing = cursor.execute(
        "SELECT id FROM family_source_versions WHERE family_id = ? AND note = ?",
        (family_id, note),
    ).fetchone()

    if existing:
        update_source_version(
            cursor,
            family_id,
            existing["id"],
            source_text=text,
            label=label,
            note=note,
        )
        version = get_source_version(cursor, family_id, existing["id"])
    else:
        vid = create_source_version(
            cursor,
            family_id,
            source_text=text,
            label=label,
            status="draft",
            note=note,
            set_active=set_active,
        )
        version = get_source_version(cursor, family_id, vid)

    if set_active and version:
        set_active_source_version(cursor, family_id, version["id"])

    if not version:
        raise ValueError("文字版保存失败")
    return version


def delete_source_version(cursor: sqlite3.Cursor, family_id: str, version_id: str) -> dict | None:
    """删除指定原文版本；至少保留一版。若删的是活跃版，自动切换到最近可用版本。"""
    payload = list_source_versions(cursor, family_id)
    versions = payload.get("versions") or []
    if len(versions) <= 1:
        raise ValueError("至少需保留一个原文版本")
    target = get_source_version(cursor, family_id, version_id)
    if not target:
        return None

    active_id = payload.get("active_version_id")
    remaining = [v for v in versions if v["id"] != version_id]
    cursor.execute(
        "DELETE FROM family_source_versions WHERE id = ? AND family_id = ?",
        (version_id, family_id),
    )

    new_active_id = active_id
    if active_id == version_id:
        confirmed = [v for v in remaining if v.get("status") == "confirmed"]
        new_active_id = (confirmed[-1]["id"] if confirmed else remaining[-1]["id"])
        _sync_family_from_version(cursor, family_id, new_active_id)

    return {
        "deleted_id": version_id,
        "deleted_label": target.get("label"),
        "active_version_id": new_active_id,
        "remaining_count": len(remaining),
    }
