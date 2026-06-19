"""谱书世次 ↔ 全谱世次 双轨模型。"""

from __future__ import annotations

import re
from typing import Any

SCHEME_ABSOLUTE = "absolute"
SCHEME_LOCAL_RESTART = "local_restart"
SCHEME_ZIBEI_ASSIST = "zibei_assist"
VALID_SCHEMES = frozenset({SCHEME_ABSOLUTE, SCHEME_LOCAL_RESTART, SCHEME_ZIBEI_ASSIST})

CANONICAL_GEN_TAG_RE = re.compile(r"\[全世\s*(\d+)\]")


def normalize_scheme(scheme: str | None) -> str:
    s = (scheme or SCHEME_ABSOLUTE).strip().lower()
    return s if s in VALID_SCHEMES else SCHEME_ABSOLUTE


def source_to_canonical(source_generation: int | None, epoch_offset: int = 1) -> int | None:
    """谱书世次 → 全谱世次。支谱：谱面一世 + offset15 → 全谱第15世。"""
    if source_generation is None:
        return None
    src = max(1, int(source_generation))
    offset = max(1, int(epoch_offset or 1))
    return src + offset - 1


def strip_canonical_generation_tag(line: str) -> tuple[str, int | None]:
    """从 RDL 行剥离 [全世N]，返回 (净文本, 全谱世次或 None)。"""
    raw = (line or "").strip()
    match = CANONICAL_GEN_TAG_RE.search(raw)
    if not match:
        return raw, None
    canonical = int(match.group(1))
    cleaned = CANONICAL_GEN_TAG_RE.sub("", raw).strip()
    return cleaned, canonical


def apply_generation_model_to_persons(
    persons: list[dict],
    *,
    scheme: str | None = SCHEME_ABSOLUTE,
    epoch_offset: int = 1,
) -> list[dict]:
    """按族谱世代规则写回 generation（全谱）与 source_generation（谱书）。"""
    sch = normalize_scheme(scheme)
    offset = max(1, int(epoch_offset or 1))
    out: list[dict] = []
    for raw in persons:
        p = dict(raw)
        src = p.get("source_generation")
        if src is None:
            src = p.get("generation")
        if src is not None:
            try:
                src = max(1, int(src))
            except (TypeError, ValueError):
                src = None
        p["source_generation"] = src
        gen = p.get("generation")
        if sch == SCHEME_LOCAL_RESTART and src is not None:
            if gen is None or gen == src:
                p["generation"] = source_to_canonical(src, offset)
        elif src is not None and gen is None:
            p["generation"] = src
        out.append(p)
    return out


def family_generation_context(family: dict | None) -> dict[str, Any]:
    if not family:
        return {
            "generation_scheme": SCHEME_ABSOLUTE,
            "generation_epoch_offset": 1,
            "start_generation": 1,
        }
    return {
        "generation_scheme": normalize_scheme(family.get("generation_scheme")),
        "generation_epoch_offset": max(1, int(family.get("generation_epoch_offset") or 1)),
        "start_generation": max(1, int(family.get("start_generation") or 1)),
        "root_person_id": family.get("root_person_id"),
    }
