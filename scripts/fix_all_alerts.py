# -*- coding: utf-8 -*-
import re
from pathlib import Path

path = Path("src/App.vue")
lines = path.read_text(encoding="utf-8").splitlines(keepends=True)

for i, line in enumerate(lines):
    if "alert(`" in line and line.count("`") < 2:
        print("broken alert line", i + 1, line[:80])
    if "message:" in line and line.count("'") % 2 == 1:
        print("broken message", i + 1, line[:80])

# fix known indices (0-based)
fixes = {
    1222: "      alert(res.error || '扫描建谱失败')\n",
    1269: "    alert('识别失败，请确认后端已启动且 API Key 正确')\n",
    1302: "      alert(`已补全 ${res.rebuild.relations_added} 条关系`)\n",
    1308: "    alert('整理失败，请确认后端已启动')\n",
    1324: "    alert(`已保存 ${res.count} 人，${res.relation_count ?? 0} 条关系`)\n",
}
for idx, content in fixes.items():
    if idx < len(lines):
        lines[idx] = content

path.write_text("".join(lines), encoding="utf-8")
print("fixed alerts")
