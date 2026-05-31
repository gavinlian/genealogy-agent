/** 版本二 · 关系描述稿格式说明与样板（与后端 genealogy_prompts 一致） */

export const RELATION_TEXT_FORMAT_HINT =
  '每行一人，或一行写清「姓名 + 配偶 + 子女」；世代用「一世 / 第2世」标在行首。'

export const RELATION_TEXT_FORMAT_TEMPLATE = `一世 张公 男 字德明 生1920 配李氏 子张三,张四
二世 张三 男 生1950 配王氏 子张甲
二世 张四 男
一世 李氏 女 配张公
二世 王氏 女 配张三

【关系】（可选，系统也能从上行字段推断）
张公 → 张三（父子）
张公 → 张四（父子）
张公 配 李氏`

export const RELATION_TEXT_FORMAT_RULES = [
  '每行对应一个真实人物，或一行写清配偶与子女列表',
  '父子：子名跟在父名后，或单独一行「父名 → 子名」',
  '配偶：用「配某某」或「A 配 B」',
  '不要把「一世」「谱序」「长子」当作人名',
]
