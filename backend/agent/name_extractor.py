"""
族谱人名识别与清洗 — 提升 OCR/AI 解析后的人名质量。

族谱常见格式：行首姓名、配/子/女前缀、字辈、公/郎后缀、复姓等。
"""

from __future__ import annotations

import re
from typing import Any

# 常见单姓 + 复姓（按长度降序匹配）
COMPOUND_SURNAMES = (
    "欧阳", "太史", "端木", "上官", "司马", "东方", "独孤", "南宫", "万俟",
    "闻人", "夏侯", "诸葛", "尉迟", "公羊", "赫连", "澹台", "皇甫", "宗政",
    "濮阳", "公冶", "太叔", "申屠", "公孙", "慕容", "仲孙", "钟离", "长孙",
    "宇文", "司徒", "鲜于", "司空", "闾丘", "子车", "亓官", "司寇", "巫马",
    "公西", "颛孙", "壤驷", "公良", "漆雕", "乐正", "宰父", "谷梁", "拓跋",
    "夹谷", "轩辕", "令狐", "段干", "百里", "东郭", "南门", "呼延", "归海",
    "羊舌", "微生", "岳帅", "缑亢", "况後", "有琴", "梁丘", "左丘", "东门",
    "西门", "商牟", "佘佴", "伯赏", "南宫", "墨哈", "谯笪", "年爱", "阳佟",
)

SINGLE_SURNAMES_COMMON = set(
    "王李张刘陈杨黄赵周吴徐孙马朱胡郭何高林罗郑梁谢宋唐许韩冯邓曹彭曾肖田董袁潘于蒋蔡余杜叶程苏魏吕丁任沈姚卢姜崔钟谭陆汪范金石廖贾夏韦付方白邹孟熊秦邱江尹薛闫段雷侯龙史陶黎贺顾毛郝龚邵万钱严覃武戴莫孔向汤"
)

# 绝非人名的词（整词匹配或作为姓名主体）
NAME_BLOCKLIST = frozenset({
    "族谱", "家谱", "宗谱", "世谱", "谱序", "序言", "碑记", "重修", "新增",
    "始祖", "开基", "迁葬", "合葬", "附葬", "生于", "卒于", "享年", "葬于",
    "配氏", "继配", "再配", "侧室", "庶出", "出继", "入继", "嗣子", "祧子",
    "世系", "世次", "世表", "行传", "传略", "简介", "备注", "说明",
    "长子", "次子", "三子", "四子", "五子", "儿子", "女儿", "之子", "之女",
    "男", "女", "未知", "不详", "无考", "失考", "早夭", "未婚",
    "一代", "二代", "三代", "四世", "五世", "六世", "七世", "八世", "九世", "十世",
    "一世", "二世", "三世", "四世", "五世", "六世", "七世", "八世", "九世", "十世",
    "第一代", "第二代", "第三代", "第一", "第二", "第三",
    "民国", "清朝", "明代", "清代", "乾隆", "嘉庆", "道光", "咸丰", "同治", "光绪",
    "康熙", "雍正", "洪武", "永乐", "万历", "天启", "崇祯", "顺治", "康熙",
})

# 姓名中不应单独出现的字（若整名即该字则无效）
NAME_CHAR_BLOCKLIST = frozenset("谱序记碑言世系表传略葬配卒生卒于享年之子女男女公元郎")

# 行首世代标记
_GEN_PREFIX = re.compile(
    r"^(?:第\s*)?[一二三四五六七八九十百千万\d]+\s*[世代]\s*"
)

# 单独一个字时不应标为姓名（族谱行常用字，非名字）
INVALID_STANDALONE_NAME_CHARS = frozenset(
    "谱序记碑言世系表传略葬配卒生卒于享之子男女长次公元郎户人家嗣祧"
)

# 子/女/配 后姓名（含单名：如「子：五」）
_ROLE_NAME_PATTERNS = [
    (re.compile(r"(?:长子|次子|三子|四子|五子|六子|子|儿子|之子|嗣子|祧子)\s*[:：]?\s*([\u4e00-\u9fff]{1,4})"), "child", "male"),
    (re.compile(r"(?:长女|次女|女|女儿|之女)\s*[:：]?\s*([\u4e00-\u9fff]{1,4})"), "child", "female"),
    (re.compile(r"配\s*[:：]?\s*([\u4e00-\u9fff]{1,4})"), "spouse", "female"),
    (re.compile(r"(?:娶|妻|室)\s*[:：]?\s*([\u4e00-\u9fff]{1,4})"), "spouse", "female"),
]

# 行内主名：支持单姓+单名两字全名（如「王伟」）
_MAIN_NAME_PATTERN = re.compile(
    r"(?:^|[，,、\s])([\u4e00-\u9fff]{1,4})(?:公|郎|子|君)?"
    r"(?=\s|$|[，,、]|\s+生|\s+卒|\s+配|\s+字|\s+男|\s+女|\s*[(（])"
)

# 全文中「A之子B」「A生B」类
_INLINE_RELATION_PATTERNS = [
    re.compile(r"([\u4e00-\u9fff]{1,4})\s*(?:之子|生|育)\s*([\u4e00-\u9fff]{1,4})"),
    re.compile(r"([\u4e00-\u9fff]{1,4})\s*配\s*([\u4e00-\u9fff]{1,4})"),
]


def normalize_person_name(name: str) -> str:
    """清洗姓名：去空白、标点、常见 OCR 误字。"""
    if not name:
        return ""
    s = str(name).strip()
    s = re.sub(r"[\s\u3000\t\r\n]+", "", s)
    s = re.sub(r"[·•．。，,、；;：:\"\"''（）()【】\[\]《》<>]", "", s)
    # 常见 OCR 混淆（族谱竖排易错）
    ocr_fix = {
        "〇": "0", "零": "0",
    }
    for old, new in ocr_fix.items():
        s = s.replace(old, new)
    if len(s) > 4:
        s = s[:4]
    return s


def is_valid_person_name(name: str, *, allow_single_char: bool = True) -> bool:
    """
    判断是否为可信的汉族人名。
    - 全名常见 2 字：单姓 + 单字名（如「王伟」「李华」）
    - 亦支持复姓、双字名，以及行内单独出现的单字名（如「子：五」中的「五」）
    """
    name = normalize_person_name(name)
    if not name:
        return False
    if name in NAME_BLOCKLIST:
        return False
    if any(suffix in name for suffix in ("族谱", "家谱", "宗谱", "世谱", "谱序")):
        return False
    if len(name) < 1 or len(name) > 4:
        return False
    if not re.fullmatch(r"[\u4e00-\u9fff]+", name):
        return False
    if len(name) == 1:
        if not allow_single_char:
            return False
        if name in INVALID_STANDALONE_NAME_CHARS or name in NAME_CHAR_BLOCKLIST:
            return False
        return True
    if all(c in NAME_CHAR_BLOCKLIST for c in name):
        return False
    # 纯数字或纯「第X世」
    if re.fullmatch(r"[第\d一二三四五六七八九十百千万世代]+", name):
        return False
    # 以「世/代」结尾且很短
    if len(name) <= 3 and name.endswith(("世", "代")):
        return False
    return True


def _guess_gender_from_line(line: str, default: str = "unknown") -> str:
    if any(x in line for x in ("女", "妹", "姐", "姑", "姨", "氏", "媳")):
        return "female"
    if any(x in line for x in ("男", "祖", "父", "兄", "弟", "郎", "公", "子")):
        return "male"
    return default


def extract_names_from_line(line: str, generation: int) -> list[dict]:
    """从单行提取人物候选（含角色）。"""
    line = line.strip()
    if not line or len(line) < 2:
        return []

    if any(kw in line for kw in ("族谱", "碑记", "序言", "重修")) and len(line) <= 10:
        return []

    found: list[dict] = []
    seen_names: set[str] = set()

    def add(name: str, role: str, gender: str, gen: int | None = None):
        n = normalize_person_name(name)
        if not is_valid_person_name(n) or n in seen_names:
            return
        seen_names.add(n)
        found.append({
            "name": n,
            "gender": gender,
            "generation": gen if gen is not None else generation,
            "_role": role,
        })

    # 1) 角色前缀名（子/女/配）— 最可靠
    for pat, role, g in _ROLE_NAME_PATTERNS:
        for m in pat.finditer(line):
            add(m.group(1), role, g, generation + 1 if role == "child" else generation)

    # 2) 去世代前缀后的行首主名
    body = _GEN_PREFIX.sub("", line).strip()
    if body:
        # 优先：姓+名 或 复姓+名
        for cs in COMPOUND_SURNAMES:
            if body.startswith(cs) and len(body) > len(cs):
                rest = body[len(cs):]
                m = re.match(r"([\u4e00-\u9fff]{1,2})(?:公|郎)?", rest)
                if m:
                    full = cs + normalize_person_name(m.group(1))
                    if is_valid_person_name(full):
                        add(full, "main", _guess_gender_from_line(line), generation)
                        break

        if not any(e.get("_role") == "main" for e in found):
            m = _MAIN_NAME_PATTERN.search(body)
            if m:
                cand = normalize_person_name(m.group(1))
                # 若候选以常见单姓开头且总长3-4，可保留；2字多为名
                if is_valid_person_name(cand):
                    add(cand, "main", _guess_gender_from_line(line), generation)
            elif len(body) >= 2:
                # 行首 2-3 字作为名（去掉尾部数字年份）
                head = re.sub(r"\d{2,4}.*$", "", body)
                head = re.sub(r"生|卒|配|字.*$", "", head)
                head = normalize_person_name(head[:4])
                if is_valid_person_name(head):
                    add(head, "main", _guess_gender_from_line(line), generation)

    return found


def extract_names_from_full_text(text: str) -> list[str]:
    """从全文补充扫描可能遗漏的人名。"""
    names: list[str] = []
    seen: set[str] = set()

    def collect(raw: str):
        n = normalize_person_name(raw)
        if is_valid_person_name(n) and n not in seen:
            seen.add(n)
            names.append(n)

    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue
        for pat, _, _ in _ROLE_NAME_PATTERNS:
            for m in pat.finditer(line):
                collect(m.group(1))
        body = _GEN_PREFIX.sub("", line)
        for m in _MAIN_NAME_PATTERN.finditer(body):
            collect(m.group(1))

    for pat in _INLINE_RELATION_PATTERNS:
        for m in pat.finditer(text):
            collect(m.group(1))
            collect(m.group(2))

    return names


def find_name_occurrences(
    text: str,
    names: list[str] | None = None,
) -> list[dict[str, Any]]:
    """在原文中定位人名出现位置（用于 OCR 文字标注）。"""
    if not text:
        return []
    if names is None:
        names = extract_names_from_full_text(text)

    occurrences: list[dict[str, Any]] = []
    seen_spans: set[tuple[int, int]] = set()

    for raw in names:
        name = normalize_person_name(raw)
        if not is_valid_person_name(name):
            continue
        for m in re.finditer(re.escape(name), text):
            span = (m.start(), m.end())
            if span in seen_spans:
                continue
            seen_spans.add(span)
            occurrences.append({
                "name": name,
                "start": m.start(),
                "end": m.end(),
            })

    occurrences.sort(key=lambda x: (x["start"], x["end"]))
    return occurrences


def post_process_person(person: dict) -> dict | None:
    """清洗单条人物；无效则返回 None。"""
    if not person:
        return None
    p = dict(person)
    raw_name = p.get("name") or ""
    name = normalize_person_name(raw_name)
    if not is_valid_person_name(name):
        return None
    p["name"] = name
    # generation_name 是字辈不是姓名
    if p.get("generation_name") == name:
        p["generation_name"] = ""
    gn = normalize_person_name(p.get("generation_name") or "")
    if gn == name:
        p["generation_name"] = ""
    return p


def refine_persons_list(
    persons: list[dict],
    raw_text: str,
    *,
    supplement_from_text: bool = True,
) -> list[dict]:
    """
    合并清洗 AI/规则结果，并从原文补漏。
    优先保留信息更全的条目。
    """
    by_name: dict[str, dict] = {}

    def merge_one(src: dict, source: str) -> None:
        cleaned = post_process_person(src)
        if not cleaned:
            return
        name = cleaned["name"]
        if name not in by_name:
            cleaned["_name_source"] = source
            by_name[name] = cleaned
            return
        old = by_name[name]
        for key in (
            "gender", "birth_year", "death_year", "generation",
            "generation_name", "courtesy_name", "art_name",
        ):
            if cleaned.get(key) is not None and old.get(key) in (None, "", "unknown"):
                old[key] = cleaned[key]
        if source == "ai" and old.get("_name_source") == "rule":
            old["_name_source"] = "ai+rule"

    for p in persons:
        merge_one(p, "ai")

    if supplement_from_text:
        for name in extract_names_from_full_text(raw_text):
            merge_one({"name": name, "gender": "unknown"}, "text_scan")

    result = []
    for p in by_name.values():
        p.pop("_name_source", None)
        p.pop("_role", None)
        result.append(p)
    return result


def score_name_confidence(person: dict, raw_text: str) -> float:
    """为人名打置信度，供校正页高亮。"""
    name = person.get("name") or ""
    if not is_valid_person_name(name):
        return 0.2
    score = 0.65
    if name in raw_text or name + "公" in raw_text or name + "郎" in raw_text:
        score += 0.15
    if person.get("birth_year") or person.get("death_year"):
        score += 0.1
    if person.get("generation"):
        score += 0.05
    # 复姓或常见姓
    for cs in COMPOUND_SURNAMES:
        if name.startswith(cs):
            score += 0.05
            break
    else:
        if name and name[0] in SINGLE_SURNAMES_COMMON:
            score += 0.05
    return min(score, 1.0)
