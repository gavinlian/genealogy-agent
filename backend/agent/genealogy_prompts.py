"""族谱 OCR → 关系描述 → 数字化 两阶段提示词。"""

OCR_PROMPT = """你是族谱 OCR 专家。请逐行识别图片中的全部文字，要求：
1. 保留竖排/横排换行与世代标题（如「一世」「第二代」）；
2. 准确识别人名（含复姓、公/郎/氏等称谓），勿把「世」「代」「谱序」当作姓名；
3. 识别生卒年、字辈、配/子/女及关系用语；
4. 繁简体按原文输出，模糊字用[]标注存疑。
只输出识别文字，不要解释。"""

# 第一阶段：OCR 乱序/原始文字 → 结构化关系描述稿
RELATION_DESCRIBE_PROMPT_TEMPLATE = """你是族谱整理专家。这是族谱数字化组谱的【第一步】：把 OCR 识别的原文整理成「关系描述稿」，供第二步自动提取人物与关系。

【你的任务】
- 读懂 OCR 原文，整理成按世代分行、关系清晰的描述稿；
- 补全缺失的世代标记（如「一世」「二世」「第3代」），但不得编造原文没有的人名；
- 把父子、配偶、生卒、字辈写进行内；
- 同辈兄弟/姊妹每人一行，并能在行内或上一行看出共同父亲；
- 不确定的字用[]标注；繁简体与原文保持一致。

【禁止】
- 不要输出 JSON、不要 markdown 代码块、不要解释过程；
- 不要把「一世」「谱序」「碑记」「长子」等当作人名。

【推荐行格式（每行一人，或一行写清配偶与子女）】
{{世代}} {{姓名}} [男|女] [字xxx] [生YYYY] [卒YYYY] [配配偶名] [子子女名...]

【示例 OCR 输入】
张氏族谱
张公 德明 一九二零
张子 配李氏 孙张甲

【示例关系描述稿输出】
一世 张公 字德明 生1920
二世 张子 男 配李氏 子张甲

【OCR 原文】
{raw_text}

请直接输出关系描述稿："""

# 第二阶段：关系描述稿 → 数字化 JSON（人物 + 关系）
DIGITIZE_PROMPT_TEMPLATE = """你是族谱数字化专家。这是族谱组谱的【第二步】：根据「关系描述稿」提取人物与关系，输出 JSON，供系统自动生成主谱。

【姓名规则】
- name 必须是 2–4 个汉字的人名（可含公/郎，如「张公」）；
- 禁止把「一世」「二世」「谱序」「碑记」「长子」等当作 name；
- generation_name 是字/号/辈分用字，不是姓名；
- 配偶单独列入 persons，并在 relations 中用 type=spouse 连接。

【关系规则】
- parent_child：from=父母，to=子女；
- spouse：from=丈夫，to=妻子；
- 以「关系描述稿」为主；若与 OCR 原文冲突，以关系描述稿为准；
- 描述稿中出现的每一个人都必须出现在 persons 中；
- 描述稿中暗示的每一条父子/配偶都必须出现在 relations 中。

【JSON 格式】
{{"persons": [
  {{"name": "张公", "gender": "male", "birth_year": 1920, "death_year": null, "generation": 1, "generation_name": "德明"}},
  {{"name": "张子", "gender": "male", "birth_year": null, "death_year": null, "generation": 2, "generation_name": ""}}
], "relations": [
  {{"from": "张公", "to": "张子", "type": "parent_child"}},
  {{"from": "张子", "to": "李氏", "type": "spouse"}}
]}}

【关系描述稿】
{relation_text}

【OCR 原文（参考，可为空）】
{raw_text}

只返回 JSON，无 markdown。"""

# 兼容旧单阶段：直接用同一段文字作关系描述稿
def build_legacy_parse_prompt(text: str) -> str:
    return build_digitize_prompt(text, text)


PARSE_PROMPT_TEMPLATE = RELATION_DESCRIBE_PROMPT_TEMPLATE  # 旧 import 名保留，实际 scan 已走两阶段


def build_relation_describe_prompt(raw_text: str) -> str:
    return RELATION_DESCRIBE_PROMPT_TEMPLATE.format(raw_text=(raw_text or "").strip())


def build_digitize_prompt(relation_text: str, raw_text: str = "") -> str:
    return DIGITIZE_PROMPT_TEMPLATE.format(
        relation_text=(relation_text or "").strip(),
        raw_text=(raw_text or "").strip() or "（无）",
    )
