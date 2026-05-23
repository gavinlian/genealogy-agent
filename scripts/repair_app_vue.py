# -*- coding: utf-8 -*-
"""Repair corrupted Chinese strings and quotes in App.vue."""
from pathlib import Path
import re

path = Path(__file__).resolve().parents[1] / "src" / "App.vue"
text = path.read_text(encoding="utf-8")

# Script string literal repairs (broken closing quotes)
script_fixes = [
    ("const s = (f.surname || f.name || '鏃?).trim()", "const s = (f.surname || f.name || '族').trim()"),
    ("if (g === 'male') return '鐢?", "if (g === 'male') return '男'"),
    ("if (g === 'female') return '濂?", "if (g === 'female') return '女'"),
    ("if (t === 'spouse') return '閰嶅伓'", "if (t === 'spouse') return '配偶'"),
    ("if (t === 'parent_child') return '鐖跺瓙'", "if (t === 'parent_child') return '父子'"),
    ("if (!confirm('纭畾鍒犻櫎锛?)) return", "if (!confirm('确定删除？')) return"),
    ("if (!confirm('纭畾鍒犻櫎锛?)) return", "if (!confirm('确定删除？')) return"),
    ("alert('璇峰～鍐欏鍚?)", "alert('请填写姓名')"),
    ("alert(res.message || res.detail || '淇濆瓨澶辫触')", "alert(res.message || res.detail || '保存失败')"),
    ("if (!confirm(`纭畾鍒犻櫎銆?{editingPerson.value.name}銆嶏紵鐩稿叧鍏崇郴灏嗕竴骞跺垹闄)) return",
     "if (!confirm(`确定删除「${editingPerson.value.name}」？相关关系将一并删除`)) return"),
    ("alert('璇烽夋嫨鍏崇郴鐨勫弻鏂规垚鍛?)", "alert('请选择关系的双方成员')"),
    ("alert(res.detail || res.message || '娣诲姞澶辫触')", "alert(res.detail || res.message || '添加失败')"),
    ("if (!confirm('鍒犻櫎杩欐潯鍏崇郴锛?)) return", "if (!confirm('删除这条关系？')) return"),
    ("alert(res.error || '鎵弿寤鸿氨澶辫触')", "alert(res.error || '扫描建谱失败')"),
    ("alert('璇嗗埆澶辫触锛岃纭鍚庣宸插惎鍔ㄤ笖 API Key 姝ｇ')", "alert('识别失败，请确认后端已启动且 API Key 正确')"),
    ("alert(res.error || '鏁寸悊澶辫触')", "alert(res.error || '整理失败')"),
    ("alert(`宸茶ˉ鍏?${res.rebuild.relations_added} 鏉″叧绯`)", "alert(`已补全 ${res.rebuild.relations_added} 条关系`)"),
    ("alert('鏁寸悊澶辫触锛岃纭鍚庣宸插惎鍔?)", "alert('整理失败，请确认后端已启动')"),
    ("alert(`宸蹭繚瀛?${res.count} 浜猴紝${res.relation_count ?? 0} 鏉″叧绯`)", "alert(`已保存 ${res.count} 人，${res.relation_count ?? 0} 条关系`)"),
    ("alert('瀵煎叆澶辫触')", "alert('导入失败')"),
    ("alert('AI 閰嶇疆宸蹭繚瀛?)", "alert('AI 配置已保存')"),
    ("{ id: 'custom', name: 'Custom', label: '鑷畾涔?, vision_model:", "{ id: 'custom', name: 'Custom', label: '自定义', vision_model:"),
    ("message: '璇峰厛濉 Group ID锛圡iniMax 鎺у埗鍙?鈫?鍩虹淇℃伅锛?,", "message: '请先填写 Group ID（MiniMax 控制台 → 基础信息）',"),
    ("message: e?.message || '璇锋眰澶辫触锛岃纭鍚庣宸插惎鍔紙绔彛 8080锛?,", "message: e?.message || '请求失败，请确认后端已启动（端口 8080）',"),
    ("testStatus.value[task] = { ...emptyTest(), loading: true, message: '杩炴帴涓…' }", "testStatus.value[task] = { ...emptyTest(), loading: true, message: '连接中…' }"),
    ("message: res.message || res.error || (res.success ? '杩炴帴鎴愬姛锛屾ā鍨嬫湁鍥炲簲' : '娴嬭瘯澶辫触'),", "message: res.message || res.error || (res.success ? '连接成功，模型有回应' : '测试失败'),"),
    ("return { success: false, message: res.ok ? '鍝嶅簲瑙ｆ瀽澶辫触' :", "return { success: false, message: res.ok ? '响应解析失败' :"),
    ("a.download = `${currentFamily.value.name || '鏃忚氨'}.json`", "a.download = `${currentFamily.value.name || '族谱'}.json`"),
]

for old, new in script_fixes:
    text = text.replace(old, new)

# Fix triple braces
text = text.replace("：{{{", "：{{")

# Fix remaining broken mustache
text = text.replace("锛坽{", "（{{")

path.write_text(text, encoding="utf-8")
print("repaired", path)
