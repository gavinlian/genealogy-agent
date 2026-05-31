import os
import sqlite3
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from agent.source_fusion import build_source_fusion, save_fusion_as_version
from source_versions import (
    VERSION_KIND_FUSION,
    VERSION_KIND_OCR_RAW,
    VERSION_KIND_RELATION_DESC,
    create_source_version,
    ensure_versions_table,
    migrate_legacy_family_source,
)


def _mem_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute(
        """CREATE TABLE families (
            id TEXT PRIMARY KEY, name TEXT, source_text TEXT, source_annotations TEXT,
            active_source_version_id TEXT)"""
    )
    c.execute(
        """CREATE TABLE persons (
            id TEXT PRIMARY KEY, family_id TEXT, name TEXT, generation INTEGER,
            gender TEXT, parent_id TEXT)"""
    )
    c.execute(
        """CREATE TABLE relations (
            id TEXT PRIMARY KEY, family_id TEXT, from_person_id TEXT, to_person_id TEXT,
            relation_type TEXT)"""
    )
    ensure_versions_table(c)
    c.execute("INSERT INTO families (id, name, source_text) VALUES ('f1', '测试', '')")
    conn.commit()
    return conn


def test_build_source_fusion_merges_versions():
    conn = _mem_db()
    c = conn.cursor()
    migrate_legacy_family_source(c, "f1")
    create_source_version(
        c, "f1",
        source_text="一世 张三\n二世 张四",
        label="OCR",
        version_kind=VERSION_KIND_OCR_RAW,
    )
    create_source_version(
        c, "f1",
        source_text="张三 → 张四",
        label="关系",
        version_kind=VERSION_KIND_RELATION_DESC,
    )
    conn.commit()
    result = build_source_fusion(c, "f1", tree_persons=[], tree_relations=[])
    assert result["success"]
    assert "第一步" in result["stepped_text"]
    assert result["stats"]["version_count"] >= 2


def test_save_fusion_as_version():
    conn = _mem_db()
    c = conn.cursor()
    migrate_legacy_family_source(c, "f1")
    version = save_fusion_as_version(c, "f1", "融合测试稿\n\n第二步")
    conn.commit()
    assert version["version_kind"] == VERSION_KIND_FUSION
    assert "融合测试稿" in version["source_text"]
