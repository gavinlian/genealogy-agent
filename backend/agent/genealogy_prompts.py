"""族谱 OCR → 关系描述 → 数字化 两阶段提示词。"""

from agent.pipeline_config import format_forbidden_for_prompt, format_rules_for_prompt, get_relation_format

_fmt = get_relation_format()
_LINE_EXAMPLE = _fmt.get("recommended_line_example") or (
    "一世 张公 男 字德明 生1920 配李氏 子张三,张四"
)
_FORBIDDEN = format_forbidden_for_prompt()
_EXTRA_RULES = format_rules_for_prompt()

OCR_PROMPT = """你是族谱 OCR 专家。这是【版本一：OCR 原文识别】——把图片中的文字忠实转写为可编辑原文。

要求：
1. 保留竖排/横排换行、世代标题（如「一世」「第二代」「谱序」）；
2. **阅读顺序必须与谱页一致**：
   - 竖排传统谱：按列从**右往左**读，每列内**自上而下**；列与列之间用空行分隔；
   - 横排旧谱：若从右往左读，则按**从右到左**的顺序输出（可用行首空格或「·」标记列界）；
   - 现代横排：从左往右、从上到下；
3. 准确识别人名（含复姓、公/郎/氏等称谓），勿把单独的「世」「代」当作姓名；
4. 识别生卒年、字辈、配/子/女及关系用语，按上述阅读顺序输出；
5. 繁简体按原文输出，模糊或难辨字用[]标注存疑；
6. 不要整理关系、不要改写成描述稿、不要 JSON——只输出识别到的原文文字。"""

# 第二阶段：版本一 OCR 原文 → 版本二「关系描述稿」（供数字化组谱）
RELATION_DESCRIBE_PROMPT_TEMPLATE = f"""你是族谱整理与数字化专家。用户已完成【版本一：OCR 原文识别】。你的任务是生成【版本二：关系描述稿】——把 OCR 乱序、缺行的原文整理成「数字族谱系统可直接解析」的结构化文字。

【版本二的目标】
- 每一行对应一个真实人物，或一行写清「某人 + 配偶 + 子女列表」；
- 世代必须明确（如「一世」「二世」「第3代」），同世兄弟分行列出；
- 父子、母子、配偶关系必须在文字中可读（子名跟在父名后，或单独一行注明「父某某」）；
- 保留/补全生年、卒年、字、号、字辈；不确定处用[]标注；
- 不得编造 OCR 原文中没有的人名；可补全关系连接词但不可虚构姓名。

【完整性要求】
- OCR 原文中的每一个人名（含配偶、女儿、侧室）都必须出现在输出中，不可遗漏；
- 每一条可辨认的父子、母子、配偶关系都必须写进输出（行内「配/子/女/父/母」或分行「A 配 B」「A → B」）；
- **若原文含「===== 第 N 页 =====」分隔符，必须按页输出，每页以相同页眉开头，页内按世代整理，不可漏页漏人**；
- 同世兄弟须分行列出，不得合并省略。

【禁止】
- 不要 JSON、不要 markdown 代码块；
- 不要任何前言、后语、分析说明、总结、温馨提示（只输出 RDL 关系描述正文）；
- 不要把 {_FORBIDDEN} 单独当作人名（可作行首世代标记）。

【格式规则（RDL · 见 config/genealogy_pipeline.json）】
{_EXTRA_RULES or "- 每行一人；父子配偶关系必须在文字中可读"}

【推荐行格式】
{{{{世代}}}} {{{{姓名}}}} [男|女] [字xxx] [生YYYY] [卒YYYY] [父{{{{姓名}}}}] [母{{{{姓名}}}}] [配{{{{配偶}}}}] [子:名1,名2] [女:名1]

【多页输出示例】
===== 第 1 页 =====
一世 张公 男 字德明 生1920 配李氏 子张三,张四
一世 李氏 女 配张公

===== 第 2 页 =====
二世 张三 男 父张公 母李氏 生1950 配王氏 子张甲

【版本一 · OCR 原文】
{{raw_text}}

请直接输出【版本二 · RDL 关系描述稿】正文（不要标题、不要解释）："""


RELATION_DESCRIBE_PAGE_PROMPT_TEMPLATE = f"""你是族谱整理专家。下面仅是【版本一 OCR 原文 · 单页】。请只输出这一页对应的【版本二 RDL 关系描述】。

要求：
- 以「===== 第 {{page}} 页 =====」开头（页码与输入一致）；
- 本页 OCR 中的人名与关系全部写出，一行一人，配/子/女/父/母写进行内；
- 不要分析说明、不要 JSON、不要编造人名；
- 格式同 RDL：{{{{世代}}}} {{{{姓名}}}} [男|女] [配{{{{配偶}}}}] [子:…] [父{{{{姓名}}}}] [母{{{{姓名}}}}]

【本页 OCR 原文】
{{raw_text}}

请直接输出本页 RDL 正文："""

# 版本三：在版本二基础上润色定稿（对照 OCR 查漏）
CUSTOM_REFINE_PROMPT_TEMPLATE = """你是族谱数字化专家。用户已完成【版本二 · RDL 关系描述】。请生成【版本三 · 修正定稿】——供系统解析为完整族谱。

【目标】
- 以版本二为主体，对照版本一 OCR 查漏人名与关系（不可漏人、不可漏配/子/女）；
- 保持 RDL 格式：一行一人，配/子/女/父/母写进行内；多页保留「===== 第 N 页 =====」；
- 修正 OCR 错字导致的人名错误，但不编造原文没有的人；
- 不要 JSON、不要分析说明、不要前言后语，只输出修正稿正文。

【版本二 · 关系描述（待修正）】
{relation_text}

【版本一 · OCR 原文（对照参考）】
{ocr_text}
{extra}

请直接输出【版本三 · 修正定稿】正文："""

# 第二阶段：关系描述稿 → 数字化 JSON（人物 + 关系）
DIGITIZE_PROMPT_TEMPLATE = f"""你是族谱数字化专家。这是族谱组谱的【第二步】：根据「关系描述稿」提取人物与关系，输出 JSON，供系统自动生成主谱。

【姓名规则】
- name 必须是 2–4 个汉字的人名（可含公/郎，如「张公」）；
- 禁止把 {_FORBIDDEN} 当作 name；
- generation_name 是字/号/辈分用字，不是姓名；
- 配偶单独列入 persons，并在 relations 中用 type=spouse 连接。

【关系规则】
- parent_child：from=父母，to=子女；
- spouse：from=丈夫，to=妻子；
- 以「关系描述稿」为主；若与 OCR 原文冲突，以关系描述稿为准；
- 描述稿中出现的每一个人都必须出现在 persons 中；
- 描述稿中暗示的每一条父子/配偶都必须出现在 relations 中。

【JSON 格式】
{{{{"persons": [
  {{{{"name": "张公", "gender": "male", "birth_year": 1920, "death_year": null, "generation": 1, "generation_name": "德明"}}}},
  {{{{"name": "张子", "gender": "male", "birth_year": null, "death_year": null, "generation": 2, "generation_name": ""}}}}
], "relations": [
  {{{{"from": "张公", "to": "张子", "type": "parent_child"}}}},
  {{{{"from": "张子", "to": "李氏", "type": "spouse"}}}}
]}}}}

【关系描述稿】
{{relation_text}}

【OCR 原文（参考，可为空）】
{{raw_text}}

只返回 JSON，无 markdown。"""

# 兼容旧单阶段：直接用同一段文字作关系描述稿
def build_legacy_parse_prompt(text: str) -> str:
    return build_digitize_prompt(text, text)


PARSE_PROMPT_TEMPLATE = RELATION_DESCRIBE_PROMPT_TEMPLATE  # 旧 import 名保留，实际 scan 已走两阶段


def build_relation_describe_prompt(
    raw_text: str,
    *,
    context_notes: str = "",
    previous_draft: str = "",
    page: int | None = None,
) -> str:
    if page is not None and page > 0:
        from source_pages import get_page_text

        page_text = get_page_text(raw_text, page) or raw_text.strip()
        return RELATION_DESCRIBE_PAGE_PROMPT_TEMPLATE.format(
            page=page,
            raw_text=page_text,
        )
    extra = ""
    if (context_notes or "").strip():
        extra += f"\n\n【用户对话与整理上下文（请优先采纳其中明确修正意见）】\n{context_notes.strip()}"
    if (previous_draft or "").strip():
        extra += (
            f"\n\n【上一版关系描述稿（可改进，勿无脑复制；以 OCR 原文为准）】\n"
            f"{previous_draft.strip()[:8000]}"
        )
    body = RELATION_DESCRIBE_PROMPT_TEMPLATE.format(raw_text=(raw_text or "").strip())
    if extra:
        # 插在 OCR 原文块之前
        marker = "【版本一 · OCR 原文】"
        if marker in body:
            return body.replace(marker, extra + "\n\n" + marker)
        return body + extra
    return body


def build_custom_refine_prompt(
    relation_text: str,
    ocr_text: str = "",
    *,
    context_notes: str = "",
    previous_draft: str = "",
) -> str:
    extra = ""
    if (context_notes or "").strip():
        extra += f"\n\n【用户对话与修正意见（优先采纳）】\n{context_notes.strip()}"
    if (previous_draft or "").strip() and previous_draft.strip() != (relation_text or "").strip():
        extra += f"\n\n【上一版修正稿（可改进）】\n{previous_draft.strip()[:8000]}"
    return CUSTOM_REFINE_PROMPT_TEMPLATE.format(
        relation_text=(relation_text or "").strip() or "（暂无版本二）",
        ocr_text=(ocr_text or "").strip() or "（无）",
        extra=extra,
    )


def build_digitize_prompt(relation_text: str, raw_text: str = "") -> str:
    return DIGITIZE_PROMPT_TEMPLATE.format(
        relation_text=(relation_text or "").strip(),
        raw_text=(raw_text or "").strip() or "（无）",
    )
