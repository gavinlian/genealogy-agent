"""GEDCOM 5.5 导入/导出（国际族谱交换格式）。"""

from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import Any


def _escape_gedcom(value: str) -> str:
    return (value or "").replace("@", "@@").replace("\n", " ")


def _sex_code(gender: str | None) -> str:
    g = (gender or "").lower()
    if g in ("male", "m", "男"):
        return "M"
    if g in ("female", "f", "女"):
        return "F"
    return "U"


def export_family_to_gedcom(
    family: dict,
    persons: list[dict],
    relations: list[dict],
) -> str:
    """导出为 GEDCOM 文本。"""
    lines = [
        "0 HEAD",
        "1 SOUR genealogy-agent",
        "2 NAME 族见 Resee",
        "1 GEDC",
        "2 VERS 5.5",
        "2 FORM LINEAGE-LINKED",
        "1 CHAR UTF-8",
        "0 @F1@ SUBM",
        "1 NAME 族见",
    ]

    indi_map: dict[str, str] = {}
    for p in persons:
        pid = p.get("id")
        if not pid:
            continue
        xref = f"@I{pid}@"
        indi_map[pid] = xref
        name = _escape_gedcom(p.get("name") or "Unknown")
        lines.append(f"0 {xref} INDI")
        lines.append(f"1 NAME {name}")
        if p.get("courtesy_name"):
            lines.append(f"1 _CN字 {_escape_gedcom(p['courtesy_name'])}")
        if p.get("art_name"):
            lines.append(f"1 _CN号 {_escape_gedcom(p['art_name'])}")
        if p.get("generation_name"):
            lines.append(f"1 _CN辈 {_escape_gedcom(p['generation_name'])}")
        lines.append(f"1 SEX {_sex_code(p.get('gender'))}")
        if p.get("birth_year"):
            lines.append(f"1 BIRT")
            lines.append(f"2 DATE ABT {int(p['birth_year'])}")
        if p.get("death_year"):
            lines.append(f"1 DEAT")
            lines.append(f"2 DATE ABT {int(p['death_year'])}")
        loc = " ".join(x for x in [p.get("county"), p.get("town"), p.get("village")] if x)
        if loc:
            lines.append(f"1 RESI")
            lines.append(f"2 PLAC {_escape_gedcom(loc)}")
        if p.get("biography"):
            lines.append(f"1 NOTE {_escape_gedcom(p['biography'][:500])}")

    fam_counter = 0
    spouse_pairs: set[tuple[str, str]] = set()
    for r in relations:
        rtype = (r.get("relation_type") or "").lower()
        if rtype != "spouse":
            continue
        a, b = r.get("from_person_id"), r.get("to_person_id")
        if not a or not b:
            continue
        key = tuple(sorted([a, b]))
        if key in spouse_pairs:
            continue
        spouse_pairs.add(key)
        fam_counter += 1
        fam_xref = f"@F{fam_counter}@"
        lines.append(f"0 {fam_xref} FAM")
        lines.append(f"1 HUSB {indi_map.get(a, '@VOID@')}")
        lines.append(f"1 WIFE {indi_map.get(b, '@VOID@')}")

    parent_child: list[tuple[str, str]] = []
    for r in relations:
        if (r.get("relation_type") or "parent_child") == "spouse":
            continue
        parent_child.append((r.get("from_person_id"), r.get("to_person_id")))

    by_parent: dict[str, list[str]] = {}
    for parent_id, child_id in parent_child:
        if parent_id and child_id:
            by_parent.setdefault(parent_id, []).append(child_id)

    for parent_id, children in by_parent.items():
        fam_counter += 1
        fam_xref = f"@F{fam_counter}@"
        lines.append(f"0 {fam_xref} FAM")
        lines.append(f"1 HUSB {indi_map.get(parent_id, '@VOID@')}")
        for cid in children:
            lines.append(f"1 CHIL {indi_map.get(cid, '@VOID@')}")

    lines.append("0 TRLR")
    title = _escape_gedcom(family.get("name") or "Family")
    lines.insert(6, f"0 @F1@ SUBM")
    return "\n".join(lines) + "\n"


def _parse_gedcom_lines(text: str) -> list[tuple[int, str, str, str]]:
    """解析为 (level, xref, tag, value) 列表。"""
    rows: list[tuple[int, str, str, str]] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        m = re.match(r"^(\d+)\s+(@[^@]+@\s+)?(\S+)(?:\s+(.*))?$", line)
        if not m:
            continue
        level = int(m.group(1))
        xref = (m.group(2) or "").strip()
        tag = m.group(3)
        value = (m.group(4) or "").strip()
        rows.append((level, xref, tag, value))
    return rows


def import_gedcom_text(text: str, *, default_surname: str = "") -> dict[str, Any]:
    """解析 GEDCOM 为族见内部结构（persons + relations）。"""
    rows = _parse_gedcom_lines(text)
    indis: dict[str, dict] = {}
    fams: dict[str, dict] = {}
    current_xref = ""
    current_fam = ""
    stack: list[str] = []

    for level, xref, tag, value in rows:
        if level == 0 and xref and tag == "INDI":
            current_xref = xref
            pid = str(uuid.uuid4())[:8]
            indis[current_xref] = {
                "id": pid,
                "xref": current_xref,
                "name": "",
                "gender": "unknown",
                "courtesy_name": "",
                "art_name": "",
                "birth_year": None,
                "death_year": None,
            }
            stack = ["INDI"]
            continue
        if level == 0 and xref and tag == "FAM":
            current_fam = xref
            fams[current_fam] = {"husb": "", "wife": "", "children": []}
            stack = ["FAM"]
            continue
        if not current_xref and tag not in ("HEAD", "TRLR", "SUBM"):
            continue

        if stack and stack[0] == "INDI" and current_xref in indis:
            p = indis[current_xref]
            if level == 1 and tag == "NAME":
                p["name"] = value.replace("/", " ").strip() or value
            elif level == 1 and tag == "SEX":
                p["gender"] = "male" if value == "M" else "female" if value == "F" else "unknown"
            elif level == 1 and tag == "_CN字":
                p["courtesy_name"] = value
            elif level == 1 and tag == "_CN号":
                p["art_name"] = value
            elif level == 1 and tag == "BIRT" and level == 2:
                pass
            elif level == 2 and tag == "DATE" and "BIRT" in stack:
                yr = re.search(r"\d{3,4}", value)
                if yr:
                    p["birth_year"] = int(yr.group())
            elif level == 1 and tag == "DEAT":
                stack.append("DEAT")
            elif level == 2 and tag == "DATE" and stack and stack[-1] == "DEAT":
                yr = re.search(r"\d{3,4}", value)
                if yr:
                    p["death_year"] = int(yr.group())
                if stack and stack[-1] == "DEAT":
                    stack.pop()

        if stack and stack[0] == "FAM" and current_fam in fams:
            fam = fams[current_fam]
            if level == 1 and tag == "HUSB":
                fam["husb"] = value
            elif level == 1 and tag == "WIFE":
                fam["wife"] = value
            elif level == 1 and tag == "CHIL":
                fam["children"].append(value)

    persons = list(indis.values())
    relations: list[dict] = []
    xref_to_id = {xref: p["id"] for xref, p in indis.items()}

    for fam in fams.values():
        h = xref_to_id.get(fam.get("husb", ""))
        w = xref_to_id.get(fam.get("wife", ""))
        if h and w:
            relations.append({
                "from_person_id": h,
                "to_person_id": w,
                "relation_type": "spouse",
            })
        parent = h or w
        if parent:
            for cx in fam.get("children") or []:
                cid = xref_to_id.get(cx)
                if cid:
                    relations.append({
                        "from_person_id": parent,
                        "to_person_id": cid,
                        "relation_type": "parent_child",
                    })

    surname = default_surname
    if not surname and persons:
        surname = (persons[0].get("name") or "")[:1]

    return {
        "family": {
            "name": f"{surname or '导入'}氏家谱",
            "surname": surname,
            "description": f"GEDCOM 导入 {datetime.now().strftime('%Y-%m-%d')}",
        },
        "persons": persons,
        "relations": relations,
    }
