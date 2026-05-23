"""原文版本管理测试"""

import os
import sqlite3
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from source_versions import (
    create_source_version,
    ensure_versions_table,
    list_source_versions,
    migrate_legacy_family_source,
    confirm_source_version,
    update_source_version,
)


def _mem_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute(
        """CREATE TABLE families (
            id TEXT PRIMARY KEY, name TEXT, source_text TEXT, source_annotations TEXT,
            active_source_version_id TEXT, updated_at TEXT)"""
    )
    ensure_versions_table(c)
    c.execute(
        "INSERT INTO families (id, name, source_text, source_annotations) VALUES (?, ?, ?, ?)",
        ("f1", "测试族谱", "一世 张三", "[]"),
    )
    conn.commit()
    return conn


def test_migrate_legacy_creates_v1():
    conn = _mem_db()
    c = conn.cursor()
    vid = migrate_legacy_family_source(c, "f1")
    conn.commit()
    assert vid
    payload = list_source_versions(c, "f1")
    assert len(payload["versions"]) == 1
    assert payload["versions"][0]["version_no"] == 1
    assert payload["versions"][0]["status"] == "confirmed"


def test_create_second_version():
    conn = _mem_db()
    c = conn.cursor()
    migrate_legacy_family_source(c, "f1")
    vid2 = create_source_version(
        c, "f1",
        source_text="二世 李四",
        source_annotations=[],
        label="第2版",
        status="draft",
    )
    conn.commit()
    assert vid2
    payload = list_source_versions(c, "f1")
    assert len(payload["versions"]) == 2
    assert payload["versions"][1]["label"] == "第2版"


def test_confirm_sets_active():
    conn = _mem_db()
    c = conn.cursor()
    migrate_legacy_family_source(c, "f1")
    vid2 = create_source_version(
        c, "f1", source_text="校对稿", source_annotations=[], label="第2版", status="draft",
    )
    confirmed = confirm_source_version(c, "f1", vid2)
    conn.commit()
    assert confirmed["status"] == "confirmed"
    row = c.execute("SELECT source_text, active_source_version_id FROM families WHERE id='f1'").fetchone()
    assert row["source_text"] == "校对稿"
    assert row["active_source_version_id"] == vid2


def test_delete_version_switches_active():
    from source_versions import delete_source_version

    conn = _mem_db()
    c = conn.cursor()
    v1 = migrate_legacy_family_source(c, "f1")
    vid2 = create_source_version(
        c, "f1", source_text="草稿2", source_annotations=[], label="第2版", status="draft", set_active=True,
    )
    result = delete_source_version(c, "f1", vid2)
    conn.commit()
    assert result["deleted_id"] == vid2
    assert result["active_version_id"] == v1
    payload = list_source_versions(c, "f1")
    assert len(payload["versions"]) == 1


def test_delete_last_version_rejected():
    from source_versions import delete_source_version
    import pytest

    conn = _mem_db()
    c = conn.cursor()
    v1 = migrate_legacy_family_source(c, "f1")
    with pytest.raises(ValueError, match="至少需保留"):
        delete_source_version(c, "f1", v1)
