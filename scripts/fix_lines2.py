# -*- coding: utf-8 -*-
from pathlib import Path
lines = Path("src/App.vue").read_text(encoding="utf-8").splitlines(keepends=True)
lines[1129] = "  if (!confirm(`确定删除「${editingPerson.value.name}」？相关关系将一并删除`)) return\n"
lines[1460] = "          message: '请先填写 Group ID（MiniMax 控制台 → 基础信息）',\n"
lines[1478] = "      message: e?.message || '请求失败，请确认后端已启动（端口 8080）',\n"
Path("src/App.vue").write_text("".join(lines), encoding="utf-8")
print("ok")
