"""族谱 Agent 运行时 — Phase 1：规则路由 + 工具执行 + UI 指令。"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from agent.agent_tools import (
    execute_find_relationship,
    execute_get_person_detail,
    execute_query_relatives,
    execute_search_persons,
    extract_two_names,
    resolve_person_id,
    ui_focus_person,
    ui_open_classic,
    ui_open_scan,
    ui_open_settings,
    ui_organize_regenerate,
    ui_set_anchor,
    ui_switch_tab,
)
from agent.graph_store import GraphStore


@dataclass
class AgentContext:
    family_id: str
    active_tab: str = "tree"
    anchor_person_id: str | None = None
    selected_person_id: str | None = None


@dataclass
class AgentTurnResult:
    reply: str
    ui_actions: list[dict[str, Any]] = field(default_factory=list)
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    state_patch: dict[str, Any] = field(default_factory=dict)


TAB_ALIASES = {
    "tree": ("树", "树图", "垂丝", "谱图", "世系"),
    "source": ("原文", "文字版", "ocr", "扫描"),
    "person": ("成员", "详情", "人物", "资料"),
    "diff": ("对比", "差异", "入库"),
    "organize": ("整理", "方案", "理谱"),
}


RELATIVE_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"堂兄弟|堂姐妹|堂兄妹|堂姐|堂弟|堂哥"), "cousins"),
    (re.compile(r"表兄弟|表姐妹|表兄妹"), "cousins"),
    (re.compile(r"曾祖|祖父|祖母|外祖|祖先|上\d*代"), "ancestors"),
    (re.compile(r"子孙|后代|下\d*代|后裔"), "descendants"),
    (re.compile(r"兄弟姐妹|兄弟|姐妹|兄妹|姐弟"), "siblings"),
    (re.compile(r"父母|父亲|母亲|双亲"), "parents"),
    (re.compile(r"子女|儿子|女儿|孩子"), "children"),
    (re.compile(r"堂兄弟是谁|谁是我堂"), "cousins"),
]


def _format_people_list(people: list[dict], *, empty_hint: str) -> str:
    if not people:
        return empty_hint
    lines = []
    for p in people[:15]:
        extra = []
        if p.get("courtesy_name"):
            extra.append(f"字{p['courtesy_name']}")
        if p.get("generation"):
            extra.append(f"第{p['generation']}代")
        suffix = f"（{'，'.join(extra)}）" if extra else ""
        lines.append(f"- {p.get('name', '未知')}{suffix}")
    if len(people) > 15:
        lines.append(f"- …共 {len(people)} 人，仅显示前 15")
    return "\n".join(lines)


def _detect_tab(message: str) -> str | None:
    lower = message.lower()
    for tab, keys in TAB_ALIASES.items():
        if any(k in message or k in lower for k in keys):
            if any(v in message for v in ("打开", "去看", "切换", "显示", "转到", "切到")):
                return tab
    return None


def _detect_relative_kind(message: str) -> str | None:
    for pat, kind in RELATIVE_PATTERNS:
        if pat.search(message):
            return kind
    return None


def _extract_search_query(message: str) -> str | None:
    m = re.search(r"(?:搜索|查找|找一下|查一下)\s*[:：]?\s*([\u4e00-\u9fff·]{1,8})", message)
    if m:
        return m.group(1)
    m = re.search(r"([\u4e00-\u9fff]{2,4})\s*(?:在哪|在哪里|的信息|的资料)", message)
    if m:
        return m.group(1)
    return None


def _extract_focus_name(message: str) -> str | None:
    m = re.search(r"(?:定位|高亮|选中|打开)\s*([\u4e00-\u9fff]{2,4})", message)
    if m:
        return m.group(1)
    return None


def _is_version_workflow_question(message: str) -> bool:
    """用户询问三版流水线、关系文字存哪一版等流程问题（非执行整理）。"""
    if not re.search(r"版本[一二三四123]|关系描述|关系文字|OCR\s*原文", message, re.I):
        return False
    if re.search(
        r"整理好的文字|填到|写入|保存到|存到|覆盖|要不要|是不是|是否应该|"
        r"怎么(?:保存|写|填)|之前.*(?:没|未).*(?:整理|写好)",
        message,
    ):
        return True
    if re.search(r"(?:怎么|如何|什么).*(?:版本|流程|区别)", message):
        return True
    return False


def _version_workflow_reply() -> str:
    return (
        "关于「整理好的文字」与版本：\n\n"
        "**三版流水线**\n"
        "- **版本一**：OCR 原文（图转字的原始稿）\n"
        "- **版本二**：关系描述稿（结构化父子/配偶关系，供解析成族谱）\n"
        "- **版本三**：修正稿（可选，校对后的定稿）\n\n"
        "**整理 Tab 中间栏**编辑的就是关系描述。确认无误后：\n"
        "1. 点 **「保存版本二」** → 写入/覆盖版本二（之前乱的可以直接改完再存）\n"
        "2. 右侧预览关系图无误后，点 **「写入主谱」** → 应用到族谱结构\n\n"
        "所以：**关系文字应保存到版本二**（若已有修正稿则用版本三）。"
        "「保存版本」与「写入主谱」是两步——前者存文字稿，后者改族谱。\n\n"
        "**不用手打**：可说「重新识别扫描图」「再次生成完整 OCR」或「重新生成关系描述」，"
        "AI 会自动写入对应版本。\n\n"
        "若版本二从未整理好，可在整理页点 **「AI 重生关系描述」**，或在对话里直接说。\n\n"
        "已为您打开【整理】页，可直接在中间栏编辑并保存。"
    )


def _detect_regenerate_kind(message: str) -> str | None:
    """识别用户要 AI 重生版本一 OCR 还是版本二关系描述。"""
    msg = message.strip()
    mentions_v1 = bool(re.search(r"版本\s*[一1]|OCR|扫描(?:图|识别)?|识别(?:出来)?的?(?:文字|原文)", msg, re.I))
    mentions_v2 = bool(re.search(r"版本\s*[二2三3]|关系(?:描述|文字)|整理.*关系", msg, re.I))

    ocr_action = re.search(
        r"重新(?:识别|OCR|扫描)|再次(?:生成|识别)|重做(?:OCR|识别)?|"
        r"OCR(?:不对|有误|错了|不准)|识别(?:不对|有误|错了|不准)|"
        r"请(?:再|重新).*(?:生成|识别).*(?:完整|全文)?|扫描.*(?:不对|错了)",
        msg,
        re.I,
    )
    rel_action = re.search(
        r"重新(?:生成|整理|做|写)|再次生成|重生|自动(?:再)?(?:生成|填)|"
        r"关系(?:描述|文字)(?:不对|有误|错了|不准)|"
        r"整理(?:关系|文字).*(?:不对|错了)|填进去",
        msg,
        re.I,
    )

    if ocr_action and (mentions_v1 or not mentions_v2):
        return "ocr_raw"
    if rel_action and (mentions_v2 or not mentions_v1):
        return "relation_desc"
    if ocr_action and not rel_action:
        return "ocr_raw"
    if rel_action and not ocr_action:
        return "relation_desc"
    if re.search(r"请再次生成完整|再次生成完整", msg):
        return "ocr_raw"
    return None


def _regenerate_reply(kind: str) -> str:
    if kind == "ocr_raw":
        return (
            "好的，正在用扫描图 **重新识别版本一 OCR** 并自动写入原文库…\n"
            "（需已上传族谱图片且配置 OCR 模型，约需几十秒）"
        )
    return (
        "好的，正在从版本一 OCR **重新生成版本二关系描述** 并自动填入…\n"
        "（需已保存版本一文字且配置关系解析模型，完成后可在整理页预览并写入主谱）"
    )


CLASSIC_PANEL_ALIASES: dict[str, tuple[str, ...]] = {
    "organize": ("整理", "理谱", "方案"),
    "source": ("原文", "文字", "ocr", "导入"),
    "export": ("导出",),
    "search": ("搜索",),
}


def _detect_classic_panel(message: str) -> str:
    for panel, keys in CLASSIC_PANEL_ALIASES.items():
        if any(k in message or k in message.lower() for k in keys):
            return panel
    return ""


def _extract_anchor_name(message: str) -> str | None:
    patterns = [
        r"我在谱中是\s*([\u4e00-\u9fff·]{2,6})",
        r"我在谱中的身份是\s*([\u4e00-\u9fff·]{2,6})",
        r"把我(?:的)?身份(?:设|改)为\s*([\u4e00-\u9fff·]{2,6})",
        r"设(?:置|定).*?我在谱.*?([\u4e00-\u9fff·]{2,6})",
        r"锚点(?:设|改)为\s*([\u4e00-\u9fff·]{2,6})",
    ]
    for pat in patterns:
        m = re.search(pat, message)
        if m:
            return m.group(1).strip()
    return None


def run_agent_turn(
    message: str,
    context: AgentContext,
    persons: list[dict[str, Any]],
    relations: list[dict[str, Any]],
    *,
    source_excerpt_fn=None,
) -> AgentTurnResult:
    """Phase 1：不依赖 LLM 的规则 Agent（可测、本地可用）。"""
    msg = (message or "").strip()
    graph = GraphStore(persons, relations)
    ui_actions: list[dict] = []
    tool_calls: list[dict] = []
    state_patch: dict[str, Any] = {}

    if not msg:
        return AgentTurnResult(
            reply="请输入您想了解或想做的族谱问题，例如：「我的堂兄弟有谁」「打开文字版」「搜索张三」。",
        )

    # 0) 设置 / 扫描 / 经典编辑 / 锚点（对话驱动 UI）
    if re.search(r"打开(?:AI|应用)?设置|AI设置|模型设置", msg):
        ui_actions.append(ui_open_settings())
        return AgentTurnResult(
            reply="已打开设置，您可配置模型与 API。",
            ui_actions=ui_actions,
            tool_calls=[{"tool": "ui_open_settings"}],
        )

    if re.search(r"扫描建谱|打开扫描|OCR建谱|拍照建谱", msg, re.I):
        ui_actions.append(ui_open_scan())
        return AgentTurnResult(
            reply="已打开扫描建谱。",
            ui_actions=ui_actions,
            tool_calls=[{"tool": "ui_open_scan"}],
        )

    if re.search(r"打开导出|去导出|导出族谱", msg):
        ui_actions.append(ui_open_classic("export"))
        return AgentTurnResult(
            reply="已打开经典编辑 · 导出。",
            ui_actions=ui_actions,
            tool_calls=[{"tool": "ui_open_classic", "panel": "export"}],
        )

    if re.search(r"经典编辑|完整编辑|高级编辑|进入经典", msg):
        panel = _detect_classic_panel(msg)
        ui_actions.append(ui_open_classic(panel))
        suffix = f" · {panel}" if panel else ""
        return AgentTurnResult(
            reply=f"已打开经典编辑{suffix}（完整 CRUD/OCR/整理/对比）。",
            ui_actions=ui_actions,
            tool_calls=[{"tool": "ui_open_classic", "panel": panel}],
        )

    anchor_name = _extract_anchor_name(msg)
    if anchor_name:
        pid = resolve_person_id(graph, name=anchor_name)
        if not pid:
            return AgentTurnResult(reply=f"未找到成员「{anchor_name}」，请确认姓名与主谱一致。")
        ui_actions.append(ui_set_anchor(pid, anchor_name))
        state_patch["anchor_person_id"] = pid
        return AgentTurnResult(
            reply=f"已设置「我在谱中是谁」为【{anchor_name}】。",
            ui_actions=ui_actions,
            tool_calls=[{"tool": "ui_set_anchor", "person_name": anchor_name}],
            state_patch=state_patch,
        )

    # 1) 切 Tab
    tab = _detect_tab(msg)
    if tab:
        ui_actions.append(ui_switch_tab(tab))
        state_patch["active_tab"] = tab
        labels = {"tree": "树图", "source": "原文", "person": "成员", "diff": "对比", "organize": "整理"}
        return AgentTurnResult(
            reply=f"已为您切换到【{labels.get(tab, tab)}】页面，您可继续说话或直接在页面上操作。",
            ui_actions=ui_actions,
            tool_calls=[{"tool": "ui_switch_tab", "tab": tab}],
            state_patch=state_patch,
        )

    # 2) 搜索
    search_q = _extract_search_query(msg)
    if search_q:
        result = execute_search_persons(persons, search_q)
        tool_calls.append({"tool": "search_persons", "result": result})
        if not result.get("people"):
            return AgentTurnResult(
                reply=f"未找到与「{search_q}」匹配的成员。可尝试全名或在树图中浏览。",
                tool_calls=tool_calls,
            )
        people = result["people"]
        if len(people) == 1:
            pid = people[0]["id"]
            ui_actions.append(ui_focus_person(pid, people[0].get("name", "")))
            ui_actions.append(ui_switch_tab("person"))
            state_patch["selected_person_id"] = pid
            state_patch["active_tab"] = "person"
        lines = _format_people_list(people, empty_hint="无结果")
        return AgentTurnResult(
            reply=f"找到 {len(people)} 位相关成员：\n{lines}",
            ui_actions=ui_actions,
            tool_calls=tool_calls,
            state_patch=state_patch,
        )

    # 3) 定位成员
    focus_name = _extract_focus_name(msg)
    if focus_name:
        pid = resolve_person_id(graph, name=focus_name)
        if not pid:
            return AgentTurnResult(reply=f"未找到成员「{focus_name}」。")
        excerpt = ""
        if source_excerpt_fn:
            excerpt = source_excerpt_fn(pid) or ""
        detail = execute_get_person_detail(graph, pid, source_excerpt=excerpt)
        tool_calls.append({"tool": "get_person_detail", "result": detail})
        ui_actions.extend([ui_switch_tab("person"), ui_focus_person(pid, focus_name)])
        state_patch.update({"selected_person_id": pid, "active_tab": "person"})
        p = detail.get("person") or {}
        reply = f"已定位到【{p.get('name', focus_name)}】"
        if p.get("courtesy_name") or p.get("art_name"):
            reply += f"，字{p.get('courtesy_name') or '—'}，号{p.get('art_name') or '—'}"
        if p.get("generation"):
            reply += f"，第{p['generation']}代"
        return AgentTurnResult(
            reply=reply,
            ui_actions=ui_actions,
            tool_calls=tool_calls,
            state_patch=state_patch,
        )

    # 4) 两人关系
    name_a, name_b = extract_two_names(msg)
    if name_a and name_b and ("关系" in msg or "是谁" in msg):
        id_a = resolve_person_id(graph, name=name_a)
        id_b = resolve_person_id(graph, name=name_b)
        if not id_a or not id_b:
            missing = name_a if not id_a else name_b
            return AgentTurnResult(reply=f"未找到成员「{missing}」，请确认姓名与主谱一致。")
        result = execute_find_relationship(graph, id_a, id_b)
        tool_calls.append({"tool": "find_relationship", "result": result})
        ui_actions.extend([
            ui_switch_tab("tree"),
            ui_focus_person(id_a, name_a),
        ])
        state_patch.update({"active_tab": "tree", "selected_person_id": id_a})
        return AgentTurnResult(
            reply=result.get("summary", "未能判断关系"),
            ui_actions=ui_actions,
            tool_calls=tool_calls,
            state_patch=state_patch,
        )

    # 5) 亲属查询
    rel_kind = _detect_relative_kind(msg)
    if rel_kind or "是谁" in msg or "有哪些" in msg or "有谁" in msg:
        subject_id = context.anchor_person_id or context.selected_person_id
        if not subject_id and ("我" in msg or "本人" in msg):
            subject_id = context.anchor_person_id
        name_in_msg = re.search(r"([\u4e00-\u9fff]{2,4})的(?:堂|表|兄|弟|姐|妹|父母|子孙)", msg)
        if name_in_msg:
            subject_id = resolve_person_id(graph, name=name_in_msg.group(1)) or subject_id
        if not subject_id:
            return AgentTurnResult(
                reply="请先在顶栏设置「我在谱中是谁」，或在树图/成员页选中一人后再问亲属关系。",
            )
        kind = rel_kind or "siblings"
        result = execute_query_relatives(graph, subject_id, kind)
        tool_calls.append({"tool": "query_relatives", "result": result})
        person = result.get("person") or {}
        kind_labels = {
            "cousins": "堂/表兄弟姐妹",
            "siblings": "兄弟姐妹",
            "parents": "父母",
            "children": "子女",
            "ancestors": "祖先",
            "descendants": "后代",
        }
        label = kind_labels.get(kind, kind)
        people = result.get("people") or []
        lines = _format_people_list(people, empty_hint=f"（暂无记录的{label}）")
        ui_actions.extend([ui_switch_tab("tree"), ui_focus_person(subject_id, person.get("name", ""))])
        state_patch.update({"selected_person_id": subject_id, "active_tab": "tree"})
        return AgentTurnResult(
            reply=f"【{person.get('name', '该成员')}】的{label}：\n{lines}",
            ui_actions=ui_actions,
            tool_calls=tool_calls,
            state_patch=state_patch,
        )

    # 5a) AI 重生版本一 OCR / 版本二关系描述（对话触发，前端或 LLM 工具执行）
    regen_kind = _detect_regenerate_kind(msg)
    if regen_kind:
        ui_actions.extend([ui_switch_tab("organize"), ui_organize_regenerate(regen_kind)])
        state_patch["active_tab"] = "organize"
        return AgentTurnResult(
            reply=_regenerate_reply(regen_kind),
            ui_actions=ui_actions,
            tool_calls=[{"tool": "regenerate_source_version", "params": {"kind": regen_kind}}],
            state_patch=state_patch,
        )

    # 5b) 三版流水线 / 关系文字存哪一版（流程问答，优先于整理执行）
    if _is_version_workflow_question(msg):
        ui_actions.append(ui_switch_tab("organize"))
        state_patch["active_tab"] = "organize"
        return AgentTurnResult(
            reply=_version_workflow_reply(),
            ui_actions=ui_actions,
            tool_calls=[{"tool": "ui_switch_tab", "tab": "organize"}],
            state_patch=state_patch,
        )

    # 5b) 整理族谱（无需说「打开」；排除「整理好的文字」等流程问句）
    if re.search(
        r"整理(?![好完成过得])(?:族谱|全谱|主谱|配偶)?|"
        r"理谱|补全(?:缺失)?关系|智能整理|从原文整理|生成关系预览",
        msg,
    ) and not _is_version_workflow_question(msg):
        ui_actions.append(ui_switch_tab("organize"))
        state_patch["active_tab"] = "organize"
        return AgentTurnResult(
            reply=(
                "已打开【整理】页。请按 图→字→关系文字 核对，右侧会实时预览关系图；"
                "满意后在预览区点「写入主谱」。也可继续在这里说具体整理意图。"
            ),
            ui_actions=ui_actions,
            tool_calls=[{"tool": "ui_switch_tab", "tab": "organize"}],
            state_patch=state_patch,
        )

    # 6) 帮助 / 默认
    return AgentTurnResult(
        reply=(
            "我可以帮您：\n"
            "- 整理族谱：说「整理族谱」「补全关系」→ 打开整理页并实时预览\n"
            "- AI 重生原文：「重新识别扫描图」「再次生成完整 OCR」「重新生成关系描述」\n"
            "- 查亲属：「我的堂兄弟有谁」（需先设置「我在谱中是谁」）\n"
            "- 搜成员：「搜索张三」\n"
            "- 问关系：「张三和李四什么关系」\n"
            "- 切页面：「打开原文」「去看树图」「打开融合」\n"
            "- 定位：「定位到张三」\n"
            "- 设身份：「我在谱中是张三」\n"
            "- 经典编辑/导出/搜索：「打开经典编辑」「打开导出」\n"
            "- 设置/扫描：「打开设置」「扫描建谱」\n\n"
            "也可直接点底部 Tab，再告诉我怎么优化当前页。"
        ),
    )
