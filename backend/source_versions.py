"""族谱原文版本管理"""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime
from typing import Any

VERSION_KIND_OCR_RAW = "ocr_raw"
VERSION_KIND_RELATION_DESC = "relation_desc"
VERSION_KIND_CUSTOM = "custom"
VERSION_KIND_FUSION = "fusion"

DEFAULT_LABELS = {
    VERSION_KIND_OCR_RAW: "版本一 · OCR 原文",
    VERSION_KIND_RELATION_DESC: "版本二 · 关系描述",
    VERSION_KIND_CUSTOM: "版本三 · 自定义",
    VERSION_KIND_FUSION: "融合稿 · 多版合并",
}

TEXT_EDITION_NOTE_PREFIX = "text_from:"
DERIVED_FROM_NOTE_PREFIX = "derived_from:"
LAYOUT_NOTE_PREFIX = "layout:"
IMAGE_NOTE_PREFIX = "image:"
PDF_NOTE_PREFIX = "pdf:"

VALID_SOURCE_LAYOUTS = frozenset({"horizontal_ltr", "horizontal_rtl", "vertical_rl", "prose"})
DEFAULT_SOURCE_LAYOUT = "horizontal_ltr"


def parse_version_note(note: str | None) -> dict[str, str | None]:
    """解析版本 note 中的 layout / image / derived_from 等字段。"""
    out: dict[str, str | None] = {
        "layout": DEFAULT_SOURCE_LAYOUT,
        "image_path": None,
        "pdf_path": None,
        "derived_from": None,
    }
    for part in (note or "").split("|"):
        token = part.strip()
        if not token:
            continue
        if token.startswith(LAYOUT_NOTE_PREFIX):
            layout = token[len(LAYOUT_NOTE_PREFIX):].strip()
            if layout in VALID_SOURCE_LAYOUTS:
                out["layout"] = layout
        elif token.startswith(IMAGE_NOTE_PREFIX):
            out["image_path"] = token[len(IMAGE_NOTE_PREFIX):].strip() or None
        elif token.startswith(PDF_NOTE_PREFIX):
            out["pdf_path"] = token[len(PDF_NOTE_PREFIX):].strip() or None
        elif token.startswith(DERIVED_FROM_NOTE_PREFIX):
            out["derived_from"] = token[len(DERIVED_FROM_NOTE_PREFIX):].strip() or None
    return out


def merge_version_note(
    note: str | None,
    *,
    layout: str | None = None,
    image_path: str | None = None,
    pdf_path: str | None = None,
) -> str | None:
    """合并 note 字段，保留未覆盖的既有信息。"""
    parsed = parse_version_note(note)
    if layout and layout in VALID_SOURCE_LAYOUTS:
        parsed["layout"] = layout
    if image_path is not None:
        val = (image_path or "").strip()
        parsed["image_path"] = val if val and not val.lower().endswith(".pdf") else None
    if pdf_path is not None:
        parsed["pdf_path"] = pdf_path or None

    parts: list[str] = []
    if parsed.get("image_path"):
        parts.append(f"{IMAGE_NOTE_PREFIX}{parsed['image_path']}")
    if parsed.get("pdf_path"):
        parts.append(f"{PDF_NOTE_PREFIX}{parsed['pdf_path']}")
    if parsed.get("layout") and parsed["layout"] != DEFAULT_SOURCE_LAYOUT:
        parts.append(f"{LAYOUT_NOTE_PREFIX}{parsed['layout']}")
    if parsed.get("derived_from"):
        parts.append(f"{DERIVED_FROM_NOTE_PREFIX}{parsed['derived_from']}")

    for part in (note or "").split("|"):
        token = part.strip()
        if not token:
            continue
        if token.startswith(TEXT_EDITION_NOTE_PREFIX):
            parts.append(token)

    return "|".join(parts) if parts else None


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
    note_meta = parse_version_note(data.get("note"))
    data["layout_hint"] = note_meta.get("layout") or DEFAULT_SOURCE_LAYOUT
    img = note_meta.get("image_path")
    if img and str(img).lower().endswith(".pdf"):
        img = None
    data["image_path"] = img
    data["pdf_path"] = note_meta.get("pdf_path")
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
            version_kind TEXT DEFAULT 'custom',
            created_at TEXT NOT NULL,
            updated_at TEXT,
            UNIQUE(family_id, version_no)
        )"""
    )
    try:
        cursor.execute("ALTER TABLE families ADD COLUMN active_source_version_id TEXT")
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute(
            "ALTER TABLE family_source_versions ADD COLUMN version_kind TEXT DEFAULT 'custom'"
        )
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
    version_kind: str = VERSION_KIND_CUSTOM,
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
            status, note, version_kind, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (vid, family_id, version_no, label, source_text or "", ann, status, note, version_kind, now, now),
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
    image_path: str | None = None,
    layout_hint: str | None = None,
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
    if image_path is not None or layout_hint is not None:
        nte = merge_version_note(
            nte,
            layout=layout_hint if layout_hint in VALID_SOURCE_LAYOUTS else None,
            image_path=image_path,
        )
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


def find_version_by_kind(cursor: sqlite3.Cursor, family_id: str, kind: str) -> dict | None:
    """按 version_kind 查找该族谱最新一版（OCR 三版流水线）。"""
    migrate_legacy_family_source(cursor, family_id)
    row = cursor.execute(
        """SELECT * FROM family_source_versions
           WHERE family_id = ? AND version_kind = ?
           ORDER BY version_no DESC LIMIT 1""",
        (family_id, kind),
    ).fetchone()
    return _row_to_version(row) if row else None


def attach_source_image(
    cursor: sqlite3.Cursor,
    family_id: str,
    image_path: str,
) -> dict:
    """为已有族谱挂上扫描原图（写入版本一 OCR 原文；无则自动创建该版）。"""
    migrate_legacy_family_source(cursor, family_id)
    v1 = find_version_by_kind(cursor, family_id, VERSION_KIND_OCR_RAW)
    note = merge_version_note(v1.get("note") if v1 else None, image_path=image_path)
    if v1:
        updated = update_source_version(cursor, family_id, v1["id"], image_path=image_path)
        if not updated:
            raise ValueError("无法更新版本一原文")
        return updated

    row = cursor.execute(
        "SELECT source_text, source_annotations FROM families WHERE id = ?",
        (family_id,),
    ).fetchone()
    text = (row["source_text"] or "").strip() if row else ""
    ann = row["source_annotations"] if row else None
    return upsert_version_by_kind(
        cursor,
        family_id,
        VERSION_KIND_OCR_RAW,
        source_text=text,
        source_annotations=ann,
        label=DEFAULT_LABELS.get(VERSION_KIND_OCR_RAW),
        status="draft",
        note=note,
    )


def upsert_version_by_kind(
    cursor: sqlite3.Cursor,
    family_id: str,
    kind: str,
    *,
    source_text: str = "",
    source_annotations: Any = None,
    label: str | None = None,
    status: str = "draft",
    note: str | None = None,
    parent_version_id: str | None = None,
    set_active: bool = False,
) -> dict:
    """按 kind 创建或更新固定语义版本（版本一/二/三）。"""
    ensure_versions_table(cursor)
    existing = find_version_by_kind(cursor, family_id, kind)
    lbl = label or DEFAULT_LABELS.get(kind, f"版本 · {kind}")
    nte = note
    if parent_version_id:
        derived = f"{DERIVED_FROM_NOTE_PREFIX}{parent_version_id}"
        nte = derived if not note else f"{note}|{derived}"

    if existing:
        version = update_source_version(
            cursor,
            family_id,
            existing["id"],
            source_text=source_text,
            source_annotations=source_annotations,
            label=lbl,
            note=nte,
        )
        if version and status:
            cursor.execute(
                "UPDATE family_source_versions SET status=?, updated_at=? WHERE id=?",
                (status, _now(), existing["id"]),
            )
            version = get_source_version(cursor, family_id, existing["id"])
    else:
        vid = create_source_version(
            cursor,
            family_id,
            source_text=source_text,
            source_annotations=source_annotations or "[]",
            label=lbl,
            status=status,
            note=nte,
            version_kind=kind,
            set_active=set_active,
        )
        version = get_source_version(cursor, family_id, vid)

    if set_active and version:
        set_active_source_version(cursor, family_id, version["id"])
        version = get_source_version(cursor, family_id, version["id"])

    if not version:
        raise ValueError(f"无法保存 {lbl}")
    return version


def get_digitize_source_for_family(cursor: sqlite3.Cursor, family_id: str) -> tuple[str, dict | None]:
    """数字化/组谱优先用版本三 > 版本二 > 版本一。"""
    migrate_legacy_family_source(cursor, family_id)
    for kind in (VERSION_KIND_CUSTOM, VERSION_KIND_RELATION_DESC, VERSION_KIND_OCR_RAW):
        version = find_version_by_kind(cursor, family_id, kind)
        if version and (version.get("source_text") or "").strip():
            return version["source_text"], version
    return get_active_source_for_family(cursor, family_id)


def save_ocr_scan_versions(
    cursor: sqlite3.Cursor,
    family_id: str,
    *,
    ocr_text: str = "",
    relation_description: str = "",
    custom_text: str = "",
    source_annotations: Any = None,
    image_path: str | None = None,
    pdf_path: str | None = None,
    layout_hint: str = DEFAULT_SOURCE_LAYOUT,
    active_kind: str = VERSION_KIND_RELATION_DESC,
) -> dict:
    """OCR 扫描入库：版本一 OCR 原文 + 版本二 关系描述 + 可选版本三 用户修正。"""
    ocr = (ocr_text or "").strip()
    rel = (relation_description or "").strip()
    custom = (custom_text or "").strip()
    if not ocr and not rel:
        raise ValueError("至少需要版本一 OCR 原文或版本二关系描述")

    img = (image_path or "").strip()
    if img.lower().endswith(".pdf"):
        img = ""
    pdf = (pdf_path or "").strip()

    v1 = find_version_by_kind(cursor, family_id, VERSION_KIND_OCR_RAW)
    note_v1 = merge_version_note(
        v1.get("note") if v1 else None,
        layout=layout_hint if layout_hint in VALID_SOURCE_LAYOUTS else DEFAULT_SOURCE_LAYOUT,
        image_path=img or None,
        pdf_path=pdf or None,
    )
    if ocr:
        v1 = upsert_version_by_kind(
            cursor,
            family_id,
            VERSION_KIND_OCR_RAW,
            source_text=ocr,
            source_annotations=source_annotations,
            status="confirmed",
            note=note_v1,
        )

    v2 = find_version_by_kind(cursor, family_id, VERSION_KIND_RELATION_DESC)
    if rel:
        v2 = upsert_version_by_kind(
            cursor,
            family_id,
            VERSION_KIND_RELATION_DESC,
            source_text=rel,
            parent_version_id=v1["id"] if v1 else None,
            status="draft",
            set_active=active_kind == VERSION_KIND_RELATION_DESC,
        )

    v3 = find_version_by_kind(cursor, family_id, VERSION_KIND_CUSTOM)
    if custom:
        parent_id = v2["id"] if v2 else (v1["id"] if v1 else None)
        v3 = upsert_version_by_kind(
            cursor,
            family_id,
            VERSION_KIND_CUSTOM,
            source_text=custom,
            parent_version_id=parent_id,
            status="confirmed",
            set_active=active_kind == VERSION_KIND_CUSTOM,
        )

    active = v2 or v1
    if active_kind == VERSION_KIND_OCR_RAW and v1:
        active = v1
    elif active_kind == VERSION_KIND_RELATION_DESC and v2:
        active = v2
    elif active_kind == VERSION_KIND_CUSTOM and v3:
        active = v3
    if active:
        set_active_source_version(cursor, family_id, active["id"])

    payload = list_source_versions(cursor, family_id)
    return {
        "version_ocr_raw": v1,
        "version_relation_desc": v2,
        "version_custom": v3,
        "active_version_id": active["id"] if active else payload.get("active_version_id"),
        **payload,
    }


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
            version_kind=VERSION_KIND_RELATION_DESC,
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
