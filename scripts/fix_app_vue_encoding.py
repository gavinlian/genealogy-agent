"""Repair App.vue after encoding corruption."""
import re
from pathlib import Path

path = Path(__file__).resolve().parents[1] / "src" / "App.vue"
text = path.read_text(encoding="utf-8-sig")

# Fix broken closing tags
text = re.sub(
    r"\?/(div|p|button|span|h3|option|template|strong|input|h2|h4|li|ul|section|main|header|article|a)>",
    r"</\1>",
    text,
)
text = re.sub(r"\?/>", "/>", text)

# Fix broken mustache openers
text = text.replace("锛坽{", "（{{")
text = text.replace("锛歿", "：{{")
text = text.replace("€?", "…'")
text = text.replace("€", "")

# Known broken lines (explicit)
fixes = [
    (
        "{{ buildLoading ? '鏁寸悊涓…' : '鏅鸿兘鏁寸悊鏃忚氨' }}",
        "{{ buildLoading ? '整理中…' : '智能整理族谱' }}",
    ),
    (
        "placeholder=\"绛涢夊鍚嶁€/>",
        "placeholder=\"筛选姓名…\"",
    ),
    (
        "{{ p.generation ? '绗? + p.generation + '浠? : '' }}",
        "{{ p.generation ? '第' + p.generation + '代' : '' }}",
    ),
    (
        "{{ testStatus.key.ok ? '鉁? : '鉁? }}",
        "{{ testStatus.key.ok ? '✓' : '✗' }}",
    ),
    (
        "{{ testStatus.ocr.ok ? '鉁? : '鉁? }}",
        "{{ testStatus.ocr.ok ? '✓' : '✗' }}",
    ),
    (
        "{{ testStatus.parse.ok ? '鉁? : '鉁? }}",
        "{{ testStatus.parse.ok ? '✓' : '✗' }}",
    ),
    (
        "{{ testStatus.key.loading ? '娴嬭瘯涓…' : '娴嬭瘯 API Key' }}",
        "{{ testStatus.key.loading ? '测试中…' : '测试 API Key' }}",
    ),
    (
        "{{ testStatus.ocr.loading ? '娴嬭瘯涓…' : '娴嬭瘯' }}",
        "{{ testStatus.ocr.loading ? '测试中…' : '测试' }}",
    ),
    (
        "{{ testStatus.parse.loading ? '娴嬭瘯涓…' : '娴嬭瘯' }}",
        "{{ testStatus.parse.loading ? '测试中…' : '测试' }}",
    ),
]

for old, new in fixes:
    text = text.replace(old, new)

# Try mojibake recovery: UTF-8 interpreted as Latin-1 then re-read as UTF-8
try:
    recovered = text.encode("cp1252").decode("utf-8")
    if "族见" in recovered and "app-shell" in recovered:
        text = recovered
except (UnicodeDecodeError, UnicodeEncodeError):
    pass

path.write_text(text, encoding="utf-8")
print("Wrote", path, "族见" in text, "lines", text.count("\n"))
