"""AI 对话式族谱整理 — 根据用户自然语言指令调整主谱结构与关系。"""

from __future__ import annotations

import json
import re
from typing import Any, Callable, Awaitable

from .genealogy_builder import auto_build_genealogy, parse_genealogy_text_enhanced
from .name_extractor import is_valid_person_name, normalize_person_name, refine_persons_list
from .parser import extract_json_content

AiFn = Callable[[str], Awaitable[tuple[str, str]]]

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


def _compact_persons(persons: list[dict], limit: int = 120) -> list[dict]:
    out = []
    for p in persons[:limit]:
        out.append({
            "name": p.get("name"),
            "gender": p.get("gender"),
            "generation": p.get("generation"),
            "birth_year": p.get("birth_year"),
            "death_year": p.get("death_year"),
            "parent_id": p.get("parent_id"),
        })
    return out


def _relations_by_name(persons: list[dict], relations: list[dict]) -> list[dict]:
    id_to_name = {str(p.get("id")): p.get("name") for p in persons if p.get("id")}
    rows = []
    for rel in relations:
        fn = rel.get("from") or rel.get("from_name") or id_to_name.get(str(rel.get("from_person_id")))
        tn = rel.get("to") or rel.get("to_name") or id_to_name.get(str(rel.get("to_person_id")))
        if fn and tn:
            rows.append({
                "from": fn,
                "to": tn,
                "type": rel.get("type") or rel.get("relation_type") or "parent_child",
                "status": rel.get("status") or "confirmed",
            })
    return rows


def _format_history(history: list[dict] | None) -> str:
    if not history:
        return "（无）"
    lines = []
    for item in history[-8:]:
        role = item.get("role") or "user"
        content = (item.get("content") or "").strip()
        if content:
            lines.append(f"{role}: {content}")
    return "\n".join(lines) or "（无）"


def build_organize_prompt(
    persons: list[dict],
    relations: list[dict],
    user_message: str,
    *,
    source_text: str = "",
    history: list[dict] | None = None,
    context_mode: str = "full",
    session_summary: str = "",
    last_explanation: str = "",
) -> str:
    rel_rows = _relations_by_name(persons, relations)
    source = (source_text or "").strip()
    source_truncated = len(source) > 12000
    if source_truncated:
        source = source[:12000] + "\n…（原文已截断，请分次整理或精简后重试）"

    bootstrap_hint = ""
    if not persons and source:
        bootstrap_hint = """
## 特别说明
当前主谱尚无成员。请主要依据「族谱 OCR/原文」提取人物与关系，在 new_persons 中列出人物，在 relations_add 中列出全部父子/配偶关系。
用户指令要求从原文建谱时，务必给出完整可应用的整理方案，不要只回答说明文字。
请设置 "clean_slate": true，relations_add 中写出全部正确关系。
"""

    clean_hint = """
## 干净整理
若用户要求按原文重建、去掉错误关系、整理成干净谱系，请设置 "clean_slate": true：
- relations_add 中写出整理后**完整正确**的全部关系（不是只写新增几条）；
- 不要依赖旧主谱中的错误关系，方案应用时会移除未出现在整理结果中的旧关系与多余成员。
"""

    agent_hint = """
## 智能体模式
你正在与用户多轮协作整理主谱。优先理解「用户最新指令」与「近期对话」中的增量修改；
若上下文为摘要模式，不要要求重复提供已讨论过的主谱全量；基于摘要与对话继续调整方案即可。
"""

    if context_mode == "summary" and session_summary:
        genealogy_block = f"""## 主谱摘要（本会话已加载完整主谱，本轮不再重复全量 JSON）
{session_summary}
{f'上轮整理说明：{last_explanation}' if last_explanation else ''}

（若用户要求「刷新上下文」或涉及未列出的具体人名关系，仍请基于摘要尽力推断；用户可在下轮刷新主谱快照。）"""
    else:
        genealogy_block = f"""## 当前成员（JSON）
{json.dumps(_compact_persons(persons), ensure_ascii=False, indent=2)}

## 当前关系 from→to（JSON）
{json.dumps(rel_rows, ensure_ascii=False, indent=2)}"""

    return f"""你是族谱整理智能体。用户正在编辑数字族谱，请根据现有数据和用户指令给出整理方案。
{agent_hint}
{bootstrap_hint}
{clean_hint}
{genealogy_block}

## 族谱 OCR/原文（参考，可为空）
{source or "（无）"}

## 近期对话
{_format_history(history)}

## 用户最新指令
{user_message.strip()}

请只返回一个 JSON 对象，不要 markdown 代码块，不要其它说明文字。格式如下：
{{
  "explanation": "用中文说明你如何理解用户意图、做了哪些调整",
  "relations_add": [
    {{"from": "父或夫名", "to": "子或妻名", "type": "parent_child", "status": "confirmed"}}
  ],
  "relations_remove": [],
  "person_updates": [],
  "new_persons": [],
  "root_person_name": null,
  "start_generation": 1,
  "clean_slate": false
}}

字段说明：
- type 只能是 parent_child 或 spouse
- status 只能是 confirmed 或 inferred
- parent_child：from=父母，to=子女
- 若用户只是提问、无需改谱，relations_add/remove 留空数组，在 explanation 中回答
- 优先使用已有成员姓名；确需新增才写入 new_persons
- 主谱为空且附带了原文时，应从原文提取人物与关系，写入 new_persons 与 relations_add，并设 clean_slate: true
- 用户要「干净/重建/按原文整理」时，设 clean_slate: true，relations_add 写完整关系集
- 不要编造原文和指令中均未提及的人
"""


def _coerce_person_entry(item: Any) -> dict | None:
    """兼容 new_persons 为字符串或对象两种模型输出。"""
    if isinstance(item, str):
        name = normalize_person_name(item.strip())
        if not is_valid_person_name(name):
            return None
        return {"name": name, "gender": "unknown", "generation": None}
    if isinstance(item, dict):
        name = normalize_person_name(
            item.get("name") or item.get("person_name") or item.get("person") or ""
        )
        if not is_valid_person_name(name):
            return None
        out: dict[str, Any] = {
            "name": name,
            "gender": item.get("gender", "unknown"),
            "generation": item.get("generation"),
        }
        for key in PERSON_DETAIL_FIELDS:
            if key in ("parent_name",):
                if item.get(key):
                    out[key] = item[key]
                continue
            if item.get(key) is not None and item.get(key) != "":
                out[key] = item[key]
        if item.get("parent_name"):
            out["parent_name"] = item["parent_name"]
        return out
    return None


def _coerce_relation_entry(item: Any) -> dict | None:
    if not isinstance(item, dict):
        return None
    fn = (item.get("from") or item.get("from_name") or item.get("parent") or "").strip()
    tn = (item.get("to") or item.get("to_name") or item.get("child") or "").strip()
    if not fn or not tn:
        return None
    rtype = item.get("type") or item.get("relation_type") or "parent_child"
    if rtype not in ("parent_child", "spouse"):
        rtype = "parent_child"
    return {
        "from": fn,
        "to": tn,
        "type": rtype,
        "status": item.get("status") or "confirmed",
        "confidence": item.get("confidence"),
    }


def _normalize_plan(raw: dict) -> dict[str, Any]:
    plan = {
        "explanation": str(raw.get("explanation") or "已完成整理分析"),
        "relations_add": [],
        "relations_remove": [],
        "person_updates": [],
        "new_persons": [],
        "root_person_name": raw.get("root_person_name"),
        "start_generation": int(raw.get("start_generation") or 1),
        "clean_slate": bool(raw.get("clean_slate")),
    }
    for rel in raw.get("relations_add") or []:
        coerced = _coerce_relation_entry(rel)
        if coerced:
            plan["relations_add"].append(coerced)
    for rel in raw.get("relations_remove") or []:
        coerced = _coerce_relation_entry(rel)
        if coerced:
            plan["relations_remove"].append(coerced)
    for upd in raw.get("person_updates") or []:
        coerced = _coerce_person_entry(upd)
        if coerced:
            plan["person_updates"].append(coerced)
    for np in raw.get("new_persons") or []:
        coerced = _coerce_person_entry(np)
        if coerced:
            plan["new_persons"].append(coerced)
    return plan


def enrich_plan_persons_from_source(
    plan: dict[str, Any],
    source_text: str,
    existing_persons: list[dict] | None = None,
) -> dict[str, Any]:
    """从族谱原文/文字版解析结果，补全方案中人物的生卒、字辈、简介等字段。"""
    text = (source_text or "").strip()
    if not text or not plan:
        return plan

    parsed = parse_genealogy_text_enhanced(text)
    by_name: dict[str, dict] = {}
    for p in parsed.get("persons") or []:
        name = (p.get("name") or "").strip()
        if name:
            by_name[name] = p

    def _merge_fields(target: dict) -> None:
        name = (target.get("name") or "").strip()
        src = by_name.get(name)
        if not src:
            return
        for key in PERSON_DETAIL_FIELDS:
            if key == "parent_name":
                continue
            if (target.get(key) is None or target.get(key) == "" or target.get(key) == "unknown") and src.get(key) not in (None, "", "unknown"):
                target[key] = src[key]
        if not target.get("biography"):
            line_hits = [ln.strip() for ln in text.splitlines() if name in ln and ln.strip()]
            if line_hits:
                target["biography"] = "；".join(line_hits[:3])[:500]

    for np in plan.get("new_persons") or []:
        _merge_fields(np)
    for upd in plan.get("person_updates") or []:
        _merge_fields(upd)

    if existing_persons:
        updates_by_name = {
            (u.get("name") or "").strip(): u
            for u in plan.get("person_updates") or []
            if (u.get("name") or "").strip()
        }
        new_names = {
            (np.get("name") or "").strip()
            for np in plan.get("new_persons") or []
            if (np.get("name") or "").strip()
        }
        for person in existing_persons:
            name = (person.get("name") or "").strip()
            if not name or name in new_names or name not in by_name:
                continue
            patch = updates_by_name.get(name) or {"name": name}
            if name not in updates_by_name:
                plan.setdefault("person_updates", []).append(patch)
                updates_by_name[name] = patch
            for key in PERSON_DETAIL_FIELDS:
                if key == "parent_name":
                    continue
                cur = person.get(key)
                src_val = by_name[name].get(key)
                if (cur is None or cur == "" or cur == "unknown") and src_val not in (None, "", "unknown"):
                    if patch.get(key) in (None, "", "unknown"):
                        patch[key] = src_val
            if not person.get("biography") and not patch.get("biography"):
                line_hits = [ln.strip() for ln in text.splitlines() if name in ln and ln.strip()]
                if line_hits:
                    patch["biography"] = "；".join(line_hits[:3])[:500]

    return plan


def extract_person_source_excerpt(source_text: str, name: str, *, max_chars: int = 1200) -> str:
    """从原文中提取包含该姓名的段落，供详情页展示。"""
    text = (source_text or "").strip()
    person_name = (name or "").strip()
    if not text or not person_name:
        return ""
    blocks: list[str] = []
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if person_name not in line:
            continue
        start = max(0, i - 1)
        end = min(len(lines), i + 2)
        block = "\n".join(ln.strip() for ln in lines[start:end] if ln.strip())
        if block and block not in blocks:
            blocks.append(block)
    out = "\n\n".join(blocks)
    return out[:max_chars] if len(out) > max_chars else out


def _plan_from_parse_shape(raw: dict) -> dict[str, Any]:
    """兼容模型返回 OCR 解析同款 persons/relations 结构。"""
    plan = _normalize_plan(raw)
    for p in raw.get("persons") or []:
        if not isinstance(p, dict):
            continue
        name = normalize_person_name(p.get("name") or "")
        if not is_valid_person_name(name):
            continue
        plan["new_persons"].append({
            "name": name,
            "gender": p.get("gender", "unknown"),
            "generation": p.get("generation"),
        })
    for r in raw.get("relations") or []:
        if not isinstance(r, dict):
            continue
        fn, tn = r.get("from"), r.get("to")
        if not fn or not tn:
            continue
        rtype = r.get("type") or "parent_child"
        if rtype not in ("parent_child", "spouse"):
            rtype = "parent_child"
        plan["relations_add"].append({
            "from": fn,
            "to": tn,
            "type": rtype,
            "status": r.get("status") or "confirmed",
        })
    plan["clean_slate"] = True
    return plan


def parse_organize_plan_from_text(content: str) -> dict[str, Any] | None:
    """从模型输出解析整理方案，兼容多种 JSON 结构与纯文本问答。"""
    if not content:
        return None

    parsed = extract_json_content(content)
    if isinstance(parsed, dict):
        nested = parsed.get("plan")
        if isinstance(nested, dict):
            parsed = nested
        if "persons" in parsed or "relations" in parsed:
            return _plan_from_parse_shape(parsed)
        return _normalize_plan(parsed)

    cleaned = re.sub(r"\x3cthink\x3e[\s\S]*?\x3c/think\x3e", "", content, flags=re.IGNORECASE).strip()
    cleaned = re.sub(r"```(?:json)?\s*|```", "", cleaned).strip()
    if cleaned and "{" not in cleaned and "}" not in cleaned and len(cleaned) >= 4:
        return _normalize_plan({"explanation": cleaned})

    return None


def _rule_parse_instruction(message: str, persons: list[dict]) -> dict[str, Any]:
    """本地规则：从指令中提取明确的父子/配偶关系。"""
    names = {p.get("name") for p in persons if p.get("name")}
    relations_add: list[dict] = []
    explanation_parts: list[str] = []

    patterns = [
        (re.compile(r"([\u4e00-\u9fff]{1,4})\s*(?:是|为)\s*([\u4e00-\u9fff]{1,4})的(?:子|儿子|女儿|女)"), "parent_child", False),
        (re.compile(r"([\u4e00-\u9fff]{1,4})的(?:子|儿子|女儿|女)\s*(?:叫|名|是|为)\s*([\u4e00-\u9fff]{1,4})"), "parent_child", True),
        (re.compile(r"([\u4e00-\u9fff]{1,4})\s*配\s*([\u4e00-\u9fff]{1,4})"), "spouse", True),
        (re.compile(r"([\u4e00-\u9fff]{1,4})\s*(?:娶|妻|室)\s*([\u4e00-\u9fff]{1,4})"), "spouse", True),
    ]

    for pat, rtype, parent_first in patterns:
        for m in pat.finditer(message):
            a, b = m.group(1), m.group(2)
            if parent_first:
                parent, child = a, b
            else:
                parent, child = b, a
            if rtype == "parent_child":
                if parent in names and child in names:
                    relations_add.append({"from": parent, "to": child, "type": "parent_child", "status": "confirmed"})
                    explanation_parts.append(f"{parent}→{child}（父子）")
            else:
                if a in names and b in names:
                    relations_add.append({"from": a, "to": b, "type": "spouse", "status": "confirmed"})
                    explanation_parts.append(f"{a}↔{b}（配偶）")

    return {
        "explanation": "；".join(explanation_parts) if explanation_parts else "",
        "relations_add": relations_add,
        "relations_remove": [],
        "person_updates": [],
        "new_persons": [],
        "root_person_name": None,
        "start_generation": 1,
    }


def _collect_plan_names(plan: dict[str, Any]) -> set[str]:
    names: set[str] = set()
    for np in plan.get("new_persons") or []:
        coerced = _coerce_person_entry(np)
        if coerced and coerced.get("name"):
            names.add(coerced["name"])
    for upd in plan.get("person_updates") or []:
        coerced = _coerce_person_entry(upd)
        if coerced and coerced.get("name"):
            names.add(coerced["name"])
    for rel in (plan.get("relations_add") or []) + (plan.get("relations_remove") or []):
        coerced = _coerce_relation_entry(rel)
        if not coerced:
            continue
        names.add(coerced["from"])
        names.add(coerced["to"])
    return names


def build_genealogy_name_index(
    persons: list[dict],
) -> tuple[set[str], dict[str, str], dict[str, str]]:
    """返回 (canonical_names, norm_to_canonical, canonical_to_id)。"""
    canonical_names: set[str] = set()
    norm_to_canonical: dict[str, str] = {}
    canonical_to_id: dict[str, str] = {}
    for p in persons:
        name = (p.get("name") or "").strip()
        if not name:
            continue
        canonical_names.add(name)
        norm = normalize_person_name(name)
        if norm:
            norm_to_canonical[norm] = name
        pid = p.get("id")
        if pid:
            canonical_to_id[name] = str(pid)
    return canonical_names, norm_to_canonical, canonical_to_id


def resolve_genealogy_name(name: str, norm_to_canonical: dict[str, str]) -> str:
    raw = (name or "").strip()
    if not raw:
        return ""
    norm = normalize_person_name(raw)
    return norm_to_canonical.get(norm, norm or raw)


def reconcile_plan_with_genealogy(plan: dict[str, Any], persons: list[dict]) -> dict[str, Any]:
    """去掉主谱已有成员、统一姓名，避免重复入库与预览人数虚高。"""
    plan = _normalize_plan(plan)
    if not persons:
        return plan

    _, norm_to_canonical, _ = build_genealogy_name_index(persons)

    filtered_new: list[dict] = []
    for np in plan.get("new_persons") or []:
        name = np.get("name") or ""
        if normalize_person_name(name) in norm_to_canonical:
            continue
        filtered_new.append(np)
    plan["new_persons"] = filtered_new

    def _fix_rel(rel: dict) -> dict | None:
        coerced = _coerce_relation_entry(rel)
        if not coerced:
            return None
        fn = resolve_genealogy_name(coerced["from"], norm_to_canonical)
        tn = resolve_genealogy_name(coerced["to"], norm_to_canonical)
        if not fn or not tn:
            return None
        coerced["from"] = fn
        coerced["to"] = tn
        return coerced

    plan["relations_add"] = [
        fixed for rel in plan.get("relations_add") or [] if (fixed := _fix_rel(rel))
    ]
    plan["relations_remove"] = [
        fixed for rel in plan.get("relations_remove") or [] if (fixed := _fix_rel(rel))
    ]

    for upd in plan.get("person_updates") or []:
        resolved = resolve_genealogy_name(upd.get("name") or "", norm_to_canonical)
        if resolved:
            upd["name"] = resolved
        if upd.get("parent_name"):
            upd["parent_name"] = resolve_genealogy_name(upd["parent_name"], norm_to_canonical)

    return plan


def should_use_clean_slate(
    user_message: str,
    *,
    clean_slate_flag: bool = False,
    plan: dict[str, Any] | None = None,
    persons: list[dict] | None = None,
    source_text: str = "",
) -> bool:
    if clean_slate_flag:
        return True
    if plan and plan.get("clean_slate"):
        return True
    msg = (user_message or "").strip()
    keywords = (
        "重新整理", "干净", "按原文", "重建", "清空", "重来", "从头", "去掉错",
        "错误关系", "整理成", "重新建谱", "从原文", "整谱",
    )
    if any(k in msg for k in keywords):
        return True
    if not persons and (source_text or "").strip():
        return True
    return False


def _rel_key(rel: dict) -> tuple[str, str, str] | None:
    fn = (rel.get("from") or rel.get("from_name") or "").strip()
    tn = (rel.get("to") or rel.get("to_name") or "").strip()
    if not fn or not tn:
        return None
    rtype = rel.get("type") or rel.get("relation_type") or "parent_child"
    return fn, tn, rtype


def _type_label(rtype: str) -> str:
    return "配偶" if rtype == "spouse" else "父子"


def compute_organize_diff(
    persons: list[dict],
    relations: list[dict],
    plan: dict[str, Any],
    preview: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """对比当前主谱与整理方案/预览结果，供前端展示差异与应用模式说明。"""
    _, norm_to_canonical, _ = build_genealogy_name_index(persons)
    current_names_set = set(norm_to_canonical.values())
    current_names = sorted(current_names_set)
    current_rels = _relations_by_name(persons, relations)
    current_rel_set = {k for r in current_rels if (k := _rel_key(r))}

    persons_to_add: list[str] = []
    for np in plan.get("new_persons") or []:
        coerced = _coerce_person_entry(np)
        if not coerced:
            continue
        name = coerced["name"]
        if normalize_person_name(name) in norm_to_canonical:
            continue
        persons_to_add.append(name)

    persons_to_update: list[dict] = []
    for upd in plan.get("person_updates") or []:
        coerced = _coerce_person_entry(upd)
        if not coerced:
            continue
        name = coerced["name"]
        if name not in current_names_set:
            continue
        fields: list[str] = []
        if upd.get("generation") is not None:
            fields.append("世代")
        if upd.get("gender"):
            fields.append("性别")
        if upd.get("parent_name"):
            fields.append("父亲")
        if fields:
            persons_to_update.append({"name": name, "fields": fields})

    relations_to_add: list[dict] = []
    existing = set(current_rel_set)
    for rel in plan.get("relations_add") or []:
        key = _rel_key(rel)
        if key and key not in existing:
            relations_to_add.append({
                "from": key[0],
                "to": key[1],
                "type": key[2],
                "status": rel.get("status") or "confirmed",
            })
            existing.add(key)

    relations_to_remove: list[dict] = []
    for rel in plan.get("relations_remove") or []:
        key = _rel_key(rel)
        if key and key in current_rel_set:
            relations_to_remove.append({"from": key[0], "to": key[1], "type": key[2]})

    preview_names = set(current_names_set) | set(persons_to_add)
    preview_rel_set = set(current_rel_set)
    for rel in relations_to_add:
        key = (rel["from"], rel["to"], rel.get("type") or "parent_child")
        preview_rel_set.add(key)
    for rel in relations_to_remove:
        key = (rel["from"], rel["to"], rel.get("type") or "parent_child")
        preview_rel_set.discard(key)

    if preview:
        built_persons = preview.get("persons") or []
        built_rels = preview.get("relations") or []
        if built_persons:
            preview_names = {p.get("name") for p in built_persons if p.get("name")}
        if built_rels:
            preview_rel_set = {
                k for r in built_rels if (k := _rel_key(r))
            }
        # 预览人数不应高于「现有 + 方案新增」；避免原文二次解析虚增
        plan_cap = current_names_set | set(persons_to_add)
        if len(preview_names) > len(plan_cap) + len(persons_to_update):
            preview_names = plan_cap
            preview_rel_set = set(current_rel_set)
            for rel in relations_to_add:
                key = (rel["from"], rel["to"], rel.get("type") or "parent_child")
                preview_rel_set.add(key)
            for rel in relations_to_remove:
                key = (rel["from"], rel["to"], rel.get("type") or "parent_child")
                preview_rel_set.discard(key)

    extra_persons = sorted(current_names_set - preview_names)
    extra_relations = [
        {"from": k[0], "to": k[1], "type": k[2]}
        for k in sorted(current_rel_set - preview_rel_set)
    ]

    before = {
        "person_count": len(current_names),
        "relation_count": len(current_rel_set),
    }
    after = {
        "person_count": len(preview_names),
        "relation_count": len(preview_rel_set),
    }

    merge_change_count = (
        len(persons_to_add) + len(persons_to_update)
        + len(relations_to_add) + len(relations_to_remove)
    )
    replace_extra_count = len(extra_persons) + len(extra_relations)

    hints: list[str] = []
    if plan.get("clean_slate"):
        hints.append(
            "干净整理：主谱将按下方整理结果重建，未出现在结果中的旧关系与多余成员会被移除。"
        )
    else:
        hints.append(
            "增量合并：仅应用下方「将新增/修改/删除」项，保留主谱中其余成员与关系。"
        )
    if extra_persons or extra_relations:
        hints.append(
            f"完全按方案替换：在合并基础上，还会移除 {len(extra_relations)} 条多余关系"
            + (f"、{len(extra_persons)} 名未出现在整理结果中的成员" if extra_persons else "")
            + "，使主谱与 AI 预览一致。"
        )
    elif plan.get("clean_slate"):
        hints.append("当前为干净整理模式，应用后将与整理预览一致。")
    else:
        hints.append("当前整理结果与主谱结构一致，两种模式效果相同。")

    return {
        "before": before,
        "after": after,
        "persons_to_add": persons_to_add,
        "persons_to_update": persons_to_update,
        "relations_to_add": relations_to_add,
        "relations_to_remove": relations_to_remove,
        "extra_persons": extra_persons,
        "extra_relations": extra_relations,
        "merge_change_count": merge_change_count,
        "replace_extra_count": replace_extra_count,
        "has_replace_impact": replace_extra_count > 0 or bool(plan.get("clean_slate")),
        "clean_slate": bool(plan.get("clean_slate")),
        "hints": hints,
    }


def merge_plan_into_genealogy(
    persons: list[dict],
    relations: list[dict],
    plan: dict[str, Any],
    *,
    source_text: str = "",
    style: str = "su",
    clean_slate: bool = False,
) -> dict[str, Any]:
    """将整理方案合并进成员/关系并生成树预览。clean_slate 时不继承旧关系，按方案重建。"""
    orig_by_name = {p.get("name"): dict(p) for p in persons if p.get("name")}
    if clean_slate:
        name_to_person: dict[str, dict] = {}
        for name in _collect_plan_names(plan):
            if name in orig_by_name:
                name_to_person[name] = dict(orig_by_name[name])
            else:
                name_to_person[name] = {
                    "name": name,
                    "gender": "unknown",
                    "generation": 1,
                    "review_status": "pending_review",
                }
        rel_rows: list[dict] = []
    else:
        name_to_person = dict(orig_by_name)
        rel_rows = _relations_by_name(persons, relations)

    for np in plan.get("new_persons") or []:
        coerced = _coerce_person_entry(np)
        if not coerced:
            continue
        name = coerced["name"]
        if name not in name_to_person:
            name_to_person[name] = {
                "name": name,
                "gender": coerced.get("gender", "unknown"),
                "generation": coerced.get("generation") or 1,
                "review_status": "pending_review",
            }

    for upd in plan.get("person_updates") or []:
        name = upd.get("name")
        if not name or name not in name_to_person:
            continue
        p = name_to_person[name]
        if upd.get("generation") is not None:
            p["generation"] = upd["generation"]
        if upd.get("gender"):
            p["gender"] = upd["gender"]
        if upd.get("parent_name"):
            p["_parent_name"] = upd["parent_name"]

    merged_persons = list(name_to_person.values())

    remove_keys = {
        (r.get("from"), r.get("to"), r.get("type") or "parent_child")
        for r in plan.get("relations_remove") or []
    }
    rel_rows = [
        r for r in rel_rows
        if (r["from"], r["to"], r.get("type") or "parent_child") not in remove_keys
    ]

    existing = {(r["from"], r["to"], r.get("type") or "parent_child") for r in rel_rows}
    for rel in plan.get("relations_add") or []:
        fn, tn = rel.get("from"), rel.get("to")
        rtype = rel.get("type") or "parent_child"
        if not fn or not tn:
            continue
        key = (fn, tn, rtype)
        if key not in existing:
            rel_rows.append({
                "from": fn,
                "to": tn,
                "type": rtype,
                "status": rel.get("status") or "confirmed",
            })
            existing.add(key)

    # 应用 parent_name 到 relations
    for p in merged_persons:
        parent_name = p.pop("_parent_name", None)
        if parent_name:
            rel_rows.append({
                "from": parent_name,
                "to": p["name"],
                "type": "parent_child",
                "status": "confirmed",
            })

    merged_persons = list(name_to_person.values())

    if source_text and (clean_slate or not orig_by_name):
        merged_persons = refine_persons_list(merged_persons, source_text)
        built = auto_build_genealogy(source_text, merged_persons, rel_rows, style=style)
    else:
        built = auto_build_genealogy("", merged_persons, rel_rows, style=style)
    built["plan"] = plan
    return built


async def organize_genealogy_with_chat(
    persons: list[dict],
    relations: list[dict],
    user_message: str,
    ai_fn: AiFn,
    *,
    source_text: str = "",
    history: list[dict] | None = None,
    style: str = "su",
    ai_configured: bool = True,
    context_mode: str = "full",
    session_summary: str = "",
    last_explanation: str = "",
    clean_slate: bool = False,
) -> dict[str, Any]:
    """对话式整理：优先使用关系解析模型（AI），未配置时才降级本地规则。"""
    message = (user_message or "").strip()
    if not message:
        return {"success": False, "error": "请输入整理指令"}

    source_truncated = len((source_text or "").strip()) > 12000

    prompt_kwargs = {
        "source_text": source_text,
        "history": history,
        "context_mode": context_mode,
        "session_summary": session_summary,
        "last_explanation": last_explanation,
    }

    prompt = build_organize_prompt(persons, relations, message, **prompt_kwargs)
    content, err = await ai_fn(prompt)
    plan = None
    used_ai = False

    if content:
        plan = parse_organize_plan_from_text(content)
        if plan:
            used_ai = True
        elif ai_configured:
            fix_prompt = (
                build_organize_prompt(persons, relations, message, **prompt_kwargs)
                + "\n\n【重要】上次输出无法解析。请严格只输出一个合法 JSON 对象，"
                "以 { 开头、以 } 结尾，字段名与类型必须与上文格式一致，不要 markdown。"
            )
            content2, err2 = await ai_fn(fix_prompt)
            if content2:
                plan = parse_organize_plan_from_text(content2)
                if plan:
                    used_ai = True
                    err = err2 or ""

    if not plan:
        rule_plan = _rule_parse_instruction(message, persons)
        if rule_plan.get("relations_add"):
            plan = rule_plan
            plan["explanation"] = rule_plan["explanation"] or "已按本地规则理解您的关系描述"
        elif ai_configured:
            detail = err or ("模型返回格式无法解析" if content else "模型未返回有效内容")
            preview = (content or "")[:240].replace("\n", " ")
            return {
                "success": False,
                "used_ai": False,
                "error": detail,
                "explanation": (
                    f"关系解析模型已响应，但整理方案 JSON 解析失败：{detail}。"
                    "请简化指令后重试，或换用设置里已测试通过的「关系解析」模型。"
                    + (f"\n\n模型原始回复片段：{preview}" if preview else "")
                ),
                "warning": err or detail,
                "raw_preview": preview,
            }
        else:
            combined = ((source_text or "") + "\n" + message).strip()
            built = auto_build_genealogy(combined, persons, relations, style=style)
            return {
                "success": built.get("success", False),
                "used_ai": False,
                "fallback": "local",
                "explanation": "未配置关系解析模型，已用本地规则合并原文与指令",
                "plan": _normalize_plan({}),
                "preview": built,
                "warning": err,
            }

    plan = _normalize_plan(plan)
    plan = reconcile_plan_with_genealogy(plan, persons)
    use_clean = should_use_clean_slate(
        message,
        clean_slate_flag=clean_slate,
        plan=plan,
        persons=persons,
        source_text=source_text,
    )
    if use_clean:
        plan["clean_slate"] = True

    built = merge_plan_into_genealogy(
        persons, relations, plan,
        source_text=source_text, style=style,
        clean_slate=use_clean,
    )
    diff = compute_organize_diff(persons, relations, plan, built)
    return {
        "success": built.get("success", True),
        "used_ai": used_ai,
        "explanation": plan.get("explanation", ""),
        "plan": plan,
        "preview": built,
        "diff": diff,
        "context_mode": context_mode,
        "source_truncated": source_truncated,
        "warning": err if not used_ai and err else "",
    }
