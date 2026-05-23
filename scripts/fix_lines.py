# -*- coding: utf-8 -*-
from pathlib import Path

path = Path(__file__).resolve().parents[1] / "src" / "App.vue"
lines = path.read_text(encoding="utf-8").splitlines(keepends=True)

replacements = {
    89: "              {{ buildLoading ? '整理中…' : '智能整理族谱' }}\n",
    228: "              :placeholder=\"searchMode === 'nl' ? '如：张三的弟弟、第3代' : '姓名 / 世代 / 字号'\"\n",
    302: "            :placeholder=\"providerKeys[keyTab]?.configured ? '已保存，输入新 Key 可覆盖' : '输入 API Key'\"\n",
    443: "                  {{ issue.person ? issue.person + '：' : '' }}{{ issue.message }}\n",
    480: "                  <span>{{ p.gender === 'male' ? '男' : p.gender === 'female' ? '女' : '未知' }}</span>\n",
    481: "                  <span v-if=\"p.birth_year\">{{ p.birth_year }}年{{ p.death_year ? '-' + p.death_year + '年' : '' }}</span>\n",
    466: "                <span class=\"rel-status\" :class=\"r.status || 'inferred'\">{{ r.status || '待确认' }}</span>\n",
}

for idx, content in replacements.items():
    if idx < len(lines):
        lines[idx] = content

path.write_text("".join(lines), encoding="utf-8")
print("fixed", len(replacements), "lines")
