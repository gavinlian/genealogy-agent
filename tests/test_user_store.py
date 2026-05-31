import os
import sqlite3
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from user_store import (
    DEFAULT_USER_ID,
    assign_family_owner,
    authenticate_user,
    create_user,
    ensure_default_user,
    list_families_for_user,
    migrate_families_to_default_owner,
)


def _mem_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("CREATE TABLE families (id TEXT PRIMARY KEY, name TEXT, owner_user_id TEXT)")
    conn.commit()
    return conn


def test_default_user_and_family_migration():
    conn = _mem_db()
    c = conn.cursor()
    c.execute("INSERT INTO families (id, name) VALUES ('f1', '李氏')")
    uid = ensure_default_user(c)
    migrate_families_to_default_owner(c)
    conn.commit()
    assert uid == DEFAULT_USER_ID
    row = c.execute("SELECT owner_user_id FROM families WHERE id='f1'").fetchone()
    assert row["owner_user_id"] == DEFAULT_USER_ID


def test_register_and_login():
    conn = _mem_db()
    c = conn.cursor()
    ensure_default_user(c)
    user = create_user(c, email="test@example.com", password="secret123", display_name="测试")
    conn.commit()
    authed = authenticate_user(c, email="test@example.com", password="secret123")
    assert authed and authed["id"] == user["id"]
    assert authenticate_user(c, email="test@example.com", password="wrong") is None


def test_family_membership_list():
    conn = _mem_db()
    c = conn.cursor()
    c.execute("INSERT INTO families (id, name) VALUES ('f1', '王氏')")
    uid = ensure_default_user(c)
    assign_family_owner(c, "f1", uid)
    conn.commit()
    families = list_families_for_user(c, uid)
    assert len(families) == 1
    assert families[0]["id"] == "f1"
