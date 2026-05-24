"""从族谱原文/文字版向主谱成员回填生卒、字号、简介等字段。"""

from __future__ import annotations

import re
from typing import Any

from .genealogy_builder import parse_genealogy_text_enhanced
from .name_extractor import extract_names_from_line, is_valid_person_name, normalize_person_name

PERSON_DETAIL_FIELDS = (
    "birth_year",
    "death_year",
    "generation",
    "generation_name",
    "generation_prefix",
    "gender",
    "courtesy_name",
    "art_name",
    "county",
    "town",
    "village",
    "biography",
    "parent_name",
)

_BIO_KEYWORDS = ("生", "卒", "字", "号", "配", "葬", "居", "娶", "迁", "任", "官")


def extract_line_profile_fields(line: str) -> dict[str, Any]:
    """从单行族谱文字提取生卒、字、号等结构化字段。"""
    text = (line or "").strip()
    if not text:
        return {}

    fields: dict[str, Any] = {}

    birth_m = (
        re.search(r"(?:生[于]?|出生于?)(\d{4})", text)
        or re.search(r"(\d{4})\s*年[^。\n]{0,12}生", text)
    )
    death_m = (
        re.search(r"卒[于]?(\d{4}|今)", text)
        or re.search(r"(\d{4})\s*年[^。\n]{0,12}卒", text)
    )
    if birth_m:
        fields["birth_year"] = int(birth_m.group(1))
    if death_m:
        token = death_m.group(1)
        if token != "今":
            fields["death_year"] = int(token)

    courtesy_patterns = (
        r"字\s*[：:]\s*([\u4e00-\u9fff·]{1,6})",
        r"字\s+([\u4e00-\u9fff]{1,4})",
        r"字([\u4e00-\u9fff]{1,4})(?=[，,。；;\s]|$|号|配|生|卒|葬)",
    )
    for pat in courtesy_patterns:
        m = re.search(pat, text)
        if m:
            cn = normalize_person_name(m.group(1))
            if cn and is_valid_person_name(cn, allow_single_char=True):
                fields["courtesy_name"] = cn
                break

    art_patterns = (
        r"号\s*[：:]\s*([\u4e00-\u9fff·]{2,10})",
        r"号\s+([\u4e00-\u9fff]{2,8})",
        r"号([\u4e00-\u9fff]{2,8})(?=[，,。；;\s]|$|配|生|卒|葬)",
    )
    for pat in art_patterns:
        m = re.search(pat, text)
        if m:
            an = normalize_person_name(m.group(1))
            if an and is_valid_person_name(an, allow_single_char=True):
                fields["art_name"] = an
                break

    gen_prefix_m = re.search(r"([^\s，,]{1,4})字辈", text)
    if gen_prefix_m:
        fields["generation_prefix"] = gen_prefix_m.group(1).strip()

    return fields


def _line_as_biography(line: str, person_name: str) -> str:
    text = re.sub(
        r"^(?:第\s*)?[一二三四五六七八九十百千万\d]+\s*[世代]\s*",
        "",
        (line or "").strip(),
    )
    if not text or person_name not in text:
        return ""
    if any(kw in text for kw in _BIO_KEYWORDS) or len(text) > len(person_name) + 4:
        return text[:500]
    return ""


def _merge_profile(base: dict | None, incoming: dict) -> dict:
    out = dict(base or {})
    for key, val in incoming.items():
        if key.startswith("_"):
            continue
        if val in (None, "", "unknown"):
            continue
        if out.get(key) in (None, "", "unknown"):
            out[key] = val
        elif key == "biography" and isinstance(val, str) and len(val) > len(str(out.get("biography") or "")):
            out[key] = val
    return out


def build_source_person_index(source_text: str) -> dict[str, dict]:
    """解析原文，按姓名聚合最完整的人物资料（含行内简介）。"""
    text = (source_text or "").strip()
    if not text:
        return {}

    parsed = parse_genealogy_text_enhanced(text)
    index: dict[str, dict] = {}
    for raw in parsed.get("persons") or []:
        name = normalize_person_name(raw.get("name") or "")
        if not is_valid_person_name(name):
            continue
        index[name] = _merge_profile(index.get(name), raw)

    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        line_body = re.sub(
            r"^(?:第\s*)?[一二三四五六七八九十百千万\d]+\s*[世代]\s*",
            "",
            stripped,
        ).strip() or stripped
        line_profile = extract_line_profile_fields(stripped)

        names_in_line: set[str] = set()
        for name in list(index.keys()):
            if name in stripped:
                names_in_line.add(name)
        for entry in extract_names_from_line(line_body, 1):
            n = normalize_person_name(entry.get("name") or "")
            if is_valid_person_name(n):
                names_in_line.add(n)

        for name in names_in_line:
            patch: dict[str, Any] = {"name": name, **line_profile}
            bio = _line_as_biography(stripped, name)
            if bio:
                patch["biography"] = bio
            index[name] = _merge_profile(index.get(name), patch)

        # 行内仅出现姓名但解析器未收录时，仍保留简介与字/号
        for m in re.finditer(r"([\u4e00-\u9fff]{2,4})", stripped):
            candidate = normalize_person_name(m.group(1))
            if not is_valid_person_name(candidate):
                continue
            bio = _line_as_biography(stripped, candidate)
            if not bio:
                continue
            index[candidate] = _merge_profile(
                index.get(candidate),
                {"name": candidate, "biography": bio, **line_profile},
            )

    return index


def lookup_source_profile(
    name: str,
    index: dict[str, dict],
    norm_to_canonical: dict[str, str],
) -> dict | None:
    from .genealogy_organizer import resolve_genealogy_name

    canonical = resolve_genealogy_name(name, norm_to_canonical) or name
    if canonical in index:
        return index[canonical]
    norm = normalize_person_name(name)
    if norm in index:
        return index[norm]
    for key, profile in index.items():
        if resolve_genealogy_name(key, norm_to_canonical) == canonical:
            return profile
    return None


def compute_person_detail_patches(
    persons: list[dict],
    source_text: str,
) -> list[dict]:
    """计算应对现有成员补全的字段（不覆盖已有非空值）。"""
    from .genealogy_organizer import build_genealogy_name_index, resolve_genealogy_name

    index = build_source_person_index(source_text)
    if not index:
        return []

    _, norm_to_canonical, _ = build_genealogy_name_index(persons)
    patches: list[dict] = []

    for person in persons:
        name = (person.get("name") or "").strip()
        if not name:
            continue
        src = lookup_source_profile(name, index, norm_to_canonical)
        if not src:
            continue

        patch: dict[str, Any] = {"name": name}
        if person.get("id"):
            patch["person_id"] = person["id"]
        changed = False

        for key in PERSON_DETAIL_FIELDS:
            if key == "parent_name":
                continue
            cur = person.get(key)
            val = src.get(key)
            if (cur is None or cur == "" or cur == "unknown") and val not in (None, "", "unknown"):
                patch[key] = val
                changed = True

        if changed:
            patches.append(patch)

    return patches


def apply_person_detail_patches(
    cursor,
    family_id: str,
    persons: list[dict],
    patches: list[dict],
    now: str,
) -> dict[str, int]:
    """将 patches 写入 persons 表（COALESCE 语义）。"""
    from .genealogy_organizer import build_genealogy_name_index, resolve_genealogy_name

    _, norm_to_canonical, _ = build_genealogy_name_index(persons)
    name_to_id = {p["name"]: p["id"] for p in persons if p.get("name") and p.get("id")}

    stats = {"persons_updated": 0, "fields_updated": 0}

    for patch in patches:
        pid = patch.get("person_id")
        name = patch.get("name")
        if not pid and name:
            resolved = resolve_genealogy_name(name, norm_to_canonical)
            pid = name_to_id.get(resolved) or name_to_id.get(name)
        if not pid:
            continue

        cursor.execute(
            """UPDATE persons SET
               generation=COALESCE(?, generation),
               gender=COALESCE(?, gender),
               birth_year=COALESCE(?, birth_year),
               death_year=COALESCE(?, death_year),
               generation_name=COALESCE(?, generation_name),
               generation_prefix=COALESCE(?, generation_prefix),
               courtesy_name=COALESCE(?, courtesy_name),
               art_name=COALESCE(?, art_name),
               county=COALESCE(?, county),
               town=COALESCE(?, town),
               village=COALESCE(?, village),
               biography=COALESCE(?, biography)
               WHERE id=? AND family_id=?""",
            (
                patch.get("generation"),
                patch.get("gender"),
                patch.get("birth_year"),
                patch.get("death_year"),
                patch.get("generation_name"),
                patch.get("generation_prefix"),
                patch.get("courtesy_name"),
                patch.get("art_name"),
                patch.get("county"),
                patch.get("town"),
                patch.get("village"),
                patch.get("biography"),
                pid,
                family_id,
            ),
        )
        if cursor.rowcount:
            stats["persons_updated"] += 1
            stats["fields_updated"] += sum(
                1 for key in PERSON_DETAIL_FIELDS
                if key != "parent_name" and patch.get(key) not in (None, "", "unknown")
            )

    return stats
