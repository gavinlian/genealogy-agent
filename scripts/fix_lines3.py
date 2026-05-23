# -*- coding: utf-8 -*-
from pathlib import Path
lines = Path("src/App.vue").read_text(encoding="utf-8").splitlines(keepends=True)
fixes = {
    28: "          <p>扫描老族谱照片，或手动创建一本新族谱</p>\n",
    29: "          <button class=\"btn-scan\" @click=\"goOCR\">开始扫描</button>\n",
    30: "          <button class=\"btn-secondary\" style=\"margin-left:10px\" @click=\"showCreateModal = true\">手动创建</button>\n",
    60: "              <button class=\"btn-ghost btn-sm\" @click=\"openFamilyEdit\">编辑</button>\n",
    61: "              <button class=\"btn-scan btn-sm\" @click=\"goOCR\">扫描</button>\n",
}
for k, v in fixes.items():
    lines[k] = v
Path("src/App.vue").write_text("".join(lines), encoding="utf-8")
