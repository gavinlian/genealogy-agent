# -*- coding: utf-8 -*-
from pathlib import Path

path = Path(__file__).resolve().parents[1] / "src" / "App.vue"
text = path.read_text(encoding="utf-8")

pairs = [
    ("if (!confirm('纭\uE1D4畾鍒犻櫎锛?)) return", "if (!confirm('确定删除？')) return"),
    ("if (!confirm('纭畾鍒犻櫎锛?)) return", "if (!confirm('确定删除？')) return"),
    ("alert('璇峰～鍐欏鍚?)", "alert('请填写姓名')"),
    ("if (!confirm(`纭畾鍒犻櫎銆?{editingPerson.value.name}銆嶏紵鐩稿叧鍏崇郴灏嗕竴骞跺垹闄)) return",
     "if (!confirm(`确定删除「${editingPerson.value.name}」？相关关系将一并删除`)) return"),
    ("alert(res.error || '鎵弿寤鸿氨澶辫触')", "alert(res.error || '扫描建谱失败')"),
    ("alert('璇嗗埆澶辫触锛岃纭鍚庣宸插惎鍔ㄤ笖 API Key 姝ｇ')", "alert('识别失败，请确认后端已启动且 API Key 正确')"),
    ("alert(`宸茶ˉ鍏?${res.rebuild.relations_added} 鏉″叧绯`)", "alert(`已补全 ${res.rebuild.relations_added} 条关系`)"),
    ("alert('鏁寸悊澶辫触锛岃纭鍚庣宸插惎鍔?)", "alert('整理失败，请确认后端已启动')"),
    ("alert(`宸蹭繚瀛?${res.count} 浜猴紝${res.relation_count ?? 0} 鏉″叧绯`)", "alert(`已保存 ${res.count} 人，${res.relation_count ?? 0} 条关系`)"),
    ("message: '璇峰厛濉 Group ID锛圡iniMax 鎺у埗鍙?鈫?鍩虹淇℃伅锛?,",
     "message: '请先填写 Group ID（MiniMax 控制台 → 基础信息）',"),
    ("message: e?.message || '璇锋眰澶辫触锛岃纭鍚庣宸插惎鍔紙绔彛 8080锛?,",
     "message: e?.message || '请求失败，请确认后端已启动（端口 8080）',"),
]

for old, new in pairs:
    if old in text:
        text = text.replace(old, new)
        print("fixed:", old[:40])

# regex fix remaining confirm with broken quote
import re
text = re.sub(
    r"if \(!confirm\('纭[^']*?\?\)\) return",
    "if (!confirm('确定删除？')) return",
    text,
)
text = re.sub(
    r"alert\('璇[^']*?\?\)",
    "alert('请填写姓名')",
    text,
)
text = re.sub(
    r"alert\(`宸[^`]*?\$\{res\.rebuild\.relations_added\}[^`]*?`\)",
    "alert(`已补全 ${res.rebuild.relations_added} 条关系`)",
    text,
)
text = re.sub(
    r"alert\(`宸[^`]*?\$\{res\.count\}[^`]*?`\)",
    "alert(`已保存 ${res.count} 人，${res.relation_count ?? 0} 条关系`)",
    text,
)

path.write_text(text, encoding="utf-8")
print("done")
