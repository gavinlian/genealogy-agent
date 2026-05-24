"""Agent 可驱动的 UI 动作清单（对话即操作）。"""

from __future__ import annotations

# type -> 中文说明（供 prompt / 日志）
UI_ACTION_LABELS: dict[str, str] = {
    "switch_tab": "切换 Tab（tree/source/person/diff/organize）",
    "focus_person": "定位并打开成员",
    "prefill_person": "预填成员表单",
    "set_anchor": "设置「我在谱中是谁」",
    "open_classic": "进入经典编辑（可选 panel: organize/source/export/search）",
    "open_settings": "打开 AI/应用设置",
    "open_scan": "打开扫描/OCR 建谱",
    "select_family": "打开族谱",
    "create_family": "新建族谱（可带 name/surname/description）",
    "scan": "扫描建谱（首页）",
}

READ_UI_TOOLS = frozenset({
    "ui_switch_tab",
    "ui_focus_person",
    "ui_set_anchor",
    "ui_open_classic",
    "ui_open_settings",
    "ui_open_scan",
})
