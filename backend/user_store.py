"""用户与族谱归属（多用户数据隔离基础）。"""

from __future__ import annotations

import hashlib
import secrets
import sqlite3
import uuid
from datetime import datetime
from typing import Any

DEFAULT_USER_ID = "local-default"
DEFAULT_USER_EMAIL = "local@genealogy.local"


def _now() -> str:
    return datetime.now().isoformat()


def _hash_password(password: str, salt: str) -> str:
    return hashlib.sha256(f"{salt}:{password}".encode("utf-8")).hexdigest()


def ensure_user_tables(cursor: sqlite3.Cursor) -> None:
    cursor.execute(
        """CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            email TEXT UNIQUE NOT NULL,
            display_name TEXT,
            password_hash TEXT NOT NULL,
            password_salt TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT
        )"""
    )
    cursor.execute(
        """CREATE TABLE IF NOT EXISTS family_memberships (
            family_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            role TEXT DEFAULT 'owner',
            created_at TEXT NOT NULL,
            PRIMARY KEY (family_id, user_id)
        )"""
    )
    try:
        cursor.execute("ALTER TABLE families ADD COLUMN owner_user_id TEXT")
    except sqlite3.OperationalError:
        pass


def ensure_default_user(cursor: sqlite3.Cursor) -> str:
    ensure_user_tables(cursor)
    row = cursor.execute("SELECT id FROM users WHERE id = ?", (DEFAULT_USER_ID,)).fetchone()
    if row:
        return DEFAULT_USER_ID
    salt = secrets.token_hex(16)
    cursor.execute(
        """INSERT INTO users (id, email, display_name, password_hash, password_salt, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            DEFAULT_USER_ID,
            DEFAULT_USER_EMAIL,
            "本地用户",
            _hash_password("local", salt),
            salt,
            _now(),
            _now(),
        ),
    )
    return DEFAULT_USER_ID


def migrate_families_to_default_owner(cursor: sqlite3.Cursor) -> None:
    ensure_default_user(cursor)
    cursor.execute(
        "UPDATE families SET owner_user_id = ? WHERE owner_user_id IS NULL OR owner_user_id = ''",
        (DEFAULT_USER_ID,),
    )
    rows = cursor.execute("SELECT id, owner_user_id FROM families").fetchall()
    now = _now()
    for row in rows:
        fid = row["id"]
        owner_uid = row["owner_user_id"]
        if owner_uid and owner_uid != DEFAULT_USER_ID:
            continue
        if not owner_uid:
            cursor.execute(
                "UPDATE families SET owner_user_id = ? WHERE id = ?",
                (DEFAULT_USER_ID, fid),
            )
        exists = cursor.execute(
            "SELECT 1 FROM family_memberships WHERE family_id = ? AND user_id = ?",
            (fid, DEFAULT_USER_ID),
        ).fetchone()
        if not exists:
            cursor.execute(
                """INSERT OR IGNORE INTO family_memberships (family_id, user_id, role, created_at)
                   VALUES (?, ?, 'owner', ?)""",
                (fid, DEFAULT_USER_ID, now),
            )


def create_user(cursor: sqlite3.Cursor, *, email: str, password: str, display_name: str = "") -> dict:
    ensure_user_tables(cursor)
    email = email.strip().lower()
    if not email or not password:
        raise ValueError("邮箱与密码不能为空")
    if cursor.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone():
        raise ValueError("该邮箱已注册")
    uid = str(uuid.uuid4())[:12]
    salt = secrets.token_hex(16)
    now = _now()
    cursor.execute(
        """INSERT INTO users (id, email, display_name, password_hash, password_salt, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (uid, email, display_name or email.split("@")[0], _hash_password(password, salt), salt, now, now),
    )
    return get_user(cursor, uid)


def authenticate_user(cursor: sqlite3.Cursor, *, email: str, password: str) -> dict | None:
    ensure_user_tables(cursor)
    row = cursor.execute("SELECT * FROM users WHERE email = ?", (email.strip().lower(),)).fetchone()
    if not row:
        return None
    expected = _hash_password(password, row["password_salt"])
    if expected != row["password_hash"]:
        return None
    return get_user(cursor, row["id"])


def get_user(cursor: sqlite3.Cursor, user_id: str) -> dict | None:
    row = cursor.execute("SELECT id, email, display_name, created_at FROM users WHERE id = ?", (user_id,)).fetchone()
    return dict(row) if row else None


def list_families_for_user(cursor: sqlite3.Cursor, user_id: str) -> list[dict]:
    rows = cursor.execute(
        """SELECT f.*, m.role AS membership_role
           FROM families f
           JOIN family_memberships m ON m.family_id = f.id
           WHERE m.user_id = ?
           ORDER BY f.name""",
        (user_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def list_owned_families(cursor: sqlite3.Cursor, user_id: str) -> list[dict]:
    rows = cursor.execute(
        """SELECT f.*, m.role AS membership_role, COUNT(p.id) AS person_count
           FROM families f
           JOIN family_memberships m ON m.family_id = f.id
           LEFT JOIN persons p ON p.family_id = f.id
           WHERE m.user_id = ? AND m.role = 'owner'
           GROUP BY f.id
           ORDER BY f.name""",
        (user_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def list_followed_families(cursor: sqlite3.Cursor, user_id: str) -> list[dict]:
    rows = cursor.execute(
        """SELECT f.*, m.role AS membership_role, COUNT(p.id) AS person_count
           FROM families f
           JOIN family_memberships m ON m.family_id = f.id
           LEFT JOIN persons p ON p.family_id = f.id
           WHERE m.user_id = ? AND m.role IN ('follower', 'viewer')
           GROUP BY f.id
           ORDER BY f.name""",
        (user_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def follow_family(cursor: sqlite3.Cursor, family_id: str, user_id: str) -> dict[str, Any]:
    ensure_user_tables(cursor)
    family = cursor.execute(
        "SELECT id, name, owner_user_id FROM families WHERE id = ?",
        (family_id,),
    ).fetchone()
    if not family:
        return {"success": False, "error": "族谱不存在"}
    if family["owner_user_id"] == user_id:
        return {"success": False, "error": "已是本人族谱，无需关注"}
    owner = cursor.execute(
        "SELECT role FROM family_memberships WHERE family_id = ? AND user_id = ?",
        (family_id, user_id),
    ).fetchone()
    if owner and owner["role"] == "owner":
        return {"success": False, "error": "已是本人族谱，无需关注"}
    now = _now()
    cursor.execute(
        """INSERT OR REPLACE INTO family_memberships (family_id, user_id, role, created_at)
           VALUES (?, ?, 'follower', ?)""",
        (family_id, user_id, now),
    )
    return {"success": True, "family_id": family_id, "role": "follower"}


def unfollow_family(cursor: sqlite3.Cursor, family_id: str, user_id: str) -> dict[str, Any]:
    ensure_user_tables(cursor)
    row = cursor.execute(
        "SELECT role FROM family_memberships WHERE family_id = ? AND user_id = ?",
        (family_id, user_id),
    ).fetchone()
    if not row:
        return {"success": False, "error": "未关注该族谱"}
    if row["role"] == "owner":
        return {"success": False, "error": "本人族谱不能取消关注，请使用删除"}
    cursor.execute(
        "DELETE FROM family_memberships WHERE family_id = ? AND user_id = ?",
        (family_id, user_id),
    )
    return {"success": True}


def list_families_dashboard(cursor: sqlite3.Cursor, user_id: str) -> dict[str, Any]:
    """本人族谱、关注族谱、可关注的其他族谱。"""
    ensure_user_tables(cursor)
    owned = list_owned_families(cursor, user_id)
    followed = list_followed_families(cursor, user_id)
    member_ids = {f["id"] for f in owned + followed}
    all_rows = cursor.execute(
        """SELECT f.*, COUNT(p.id) AS person_count
           FROM families f
           LEFT JOIN persons p ON p.family_id = f.id
           GROUP BY f.id
           ORDER BY f.created_at DESC"""
    ).fetchall()
    discoverable = []
    for row in all_rows:
        item = dict(row)
        if item["id"] in member_ids:
            continue
        discoverable.append(item)
    return {
        "owned": owned,
        "followed": followed,
        "discoverable": discoverable,
    }


def assign_family_owner(cursor: sqlite3.Cursor, family_id: str, user_id: str) -> None:
    ensure_user_tables(cursor)
    now = _now()
    cursor.execute("UPDATE families SET owner_user_id = ? WHERE id = ?", (user_id, family_id))
    cursor.execute(
        """INSERT OR REPLACE INTO family_memberships (family_id, user_id, role, created_at)
           VALUES (?, ?, 'owner', ?)""",
        (family_id, user_id, now),
    )


def resolve_user_id(cursor: sqlite3.Cursor, header_user_id: str | None) -> str:
    ensure_default_user(cursor)
    migrate_families_to_default_owner(cursor)
    if header_user_id:
        row = cursor.execute("SELECT id FROM users WHERE id = ?", (header_user_id,)).fetchone()
        if row:
            return header_user_id
    return DEFAULT_USER_ID
