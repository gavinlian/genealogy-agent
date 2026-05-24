"""首页：从 natural language 提取「新建族谱」字段。"""

from __future__ import annotations

import re
from typing import Any

_BAD_NAME_PREFIX = re.compile(r"^(?:帮我|我要|咱们|给|为|想|请|怎么|如何|一个|一本|这个|那个|建|做|弄|创|新|建立|创建|新建)")


def _clean_token(s: str) -> str:
    return (s or "").strip().strip("「」\"'""''")


def _is_valid_genealogy_name(name: str) -> bool:
    n = _clean_token(name)
    if len(n) < 2 or len(n) > 40:
        return False
    if _BAD_NAME_PREFIX.search(n):
        return False
    if n in ("族谱", "家谱", "宗谱"):
        return False
    return True


def finalize_create_fields(fields: dict[str, Any]) -> dict[str, Any]:
    """补全族谱名/姓氏，便于自动创建或预填表单。"""
    out = {k: v for k, v in (fields or {}).items() if v not in (None, "")}
    name = _clean_token(str(out.get("name") or ""))
    surname = _clean_token(str(out.get("surname") or ""))

    if name and not _is_valid_genealogy_name(name):
        name = ""

    if name:
        out["name"] = name
        if not surname:
            sm = re.match(r"([\u4e00-\u9fff]{1,4})氏", name)
            if sm:
                out["surname"] = sm.group(1)
    elif surname:
        out["name"] = f"{surname}氏族谱"
        out["surname"] = surname

    return {k: v for k, v in out.items() if v not in (None, "")}


def _extract_surname(raw: str) -> str:
    surname_m = re.search(
        r"(?:姓氏|姓)\s*[：:为]?\s*[\"']?([\u4e00-\u9fff]{1,4})(?=[，,。；;\s]|$|描述|简介)",
        raw,
    )
    if surname_m:
        return _clean_token(surname_m.group(1))
    for pat in (
        r"我们姓([\u4e00-\u9fff]{1,4})",
        r"姓([\u4e00-\u9fff]{1,4})(?:的|人家|家族|氏族)?",
        r"([\u4e00-\u9fff]{1,4})姓(?:人家|的)?",
    ):
        sm = re.search(pat, raw)
        if sm:
            return _clean_token(sm.group(1))
    return ""


def _extract_name(raw: str) -> str:
    # 1) 显式标签（谱名叫 优先，避免被泛化规则截胡）
    explicit = re.search(r"谱名叫\s*[\"']?([^\s，,。；;\n\"']{2,40})", raw)
    if explicit:
        candidate = _clean_token(explicit.group(1))
        if _is_valid_genealogy_name(candidate):
            return candidate

    for pat in (
        r"(?:名称|族谱名|谱名|名字叫|叫做|名为|名称是)\s*[：:为]?\s*[\"']?([^\s，,。；;\n\"']{2,40})",
        r"[「『\"']([^」』\"']{2,40})[」』\"']",
    ):
        m = re.search(pat, raw)
        if m:
            candidate = _clean_token(m.group(1))
            if _is_valid_genealogy_name(candidate):
                return candidate

    # 2) 建/做 + 张氏(族谱)
    m = re.search(
        r"(?:创建|新建|建立|建|做|弄)(?:一?本|一个|个)?\s*([\u4e00-\u9fff]{1,4})氏(?:族谱|家谱|宗谱)?",
        raw,
    )
    if m:
        clan = m.group(1)
        return f"{clan}氏族谱"

    # 3) 创建 + XXX族谱
    m = re.search(
        r"(?:创建|新建|建立)\s*[\"']?([^\s，,。；;\n\"']{2,30}?)(?:族谱|家谱|宗谱)",
        raw,
    )
    if m:
        candidate = _clean_token(m.group(1))
        if _is_valid_genealogy_name(candidate):
            return candidate

    # 4) 句中出现的规范谱名
    for m in re.finditer(r"([\u4e00-\u9fff]{1,8}(?:族谱|家谱|宗谱))", raw):
        candidate = _clean_token(m.group(1))
        if candidate.startswith(("一个", "一本", "这个", "那个")):
            continue
        if _is_valid_genealogy_name(candidate):
            return candidate

    return ""


def _extract_description(raw: str) -> str:
    for pat in (
        r"(?:简介|描述|说明)\s*[：:为]\s*(.+?)(?=\s*(?:名称|姓氏|姓|创建|新建)|$)",
        r"(?:祖籍|来自|籍贯)\s*[：:为]?\s*(.+?)(?=\s*(?:名称|姓氏|姓|创建|新建)|$)",
        r"(?:简介|描述|说明)[，,]\s*(.+?)$",
    ):
        desc_m = re.search(pat, raw, re.S)
        if desc_m:
            return desc_m.group(1).strip().strip("，,。")[:500]
    return ""


def extract_family_create_from_text(text: str) -> dict[str, Any]:
    """从自然语言提取族谱名称、姓氏、简介。"""
    raw = (text or "").strip()
    if not raw:
        return {}

    fields: dict[str, Any] = {}
    name = _extract_name(raw)
    if name:
        fields["name"] = name

    surname = _extract_surname(raw)
    if surname:
        fields["surname"] = surname

    description = _extract_description(raw)
    if description:
        fields["description"] = description

    return finalize_create_fields(fields)


_CREATE_INTENT_RE = re.compile(
    r"创建|新建|建立|做一?本|弄一?本|建一?本|建一个|弄一个|做一个|"
    r"(?<![创])建(?![立])族谱|"
    r"做族谱|弄族谱|"
    r"帮我.*(?:族谱|家谱|宗谱)|我要.*(?:族谱|家谱|宗谱)|"
    r"记录.*(?:家族|家史|家谱)",
)


def looks_like_create_family(text: str) -> bool:
    raw = (text or "").strip()
    if len(raw) < 3:
        return False
    if re.search(r"(?:怎么|如何|能不能|可以吗)", raw):
        return bool(extract_family_create_from_text(raw).get("name"))
    return bool(_CREATE_INTENT_RE.search(raw))


def build_create_family_action(message: str) -> dict[str, Any] | None:
    """从用户消息构建可自动创建的 home action。"""
    if not looks_like_create_family(message):
        return None
    fields = extract_family_create_from_text(message)
    if not fields.get("name"):
        return None
    return {"type": "create_family", **fields, "auto_create": True}
