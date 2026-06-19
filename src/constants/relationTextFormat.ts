/** 版本二 · RDL 关系描述稿（与 docs/PRD/族谱关系描述规范.md 一致） */

export const RELATION_TEXT_FORMAT_HINT =
  '按页分页（===== 第 N 页 =====）；每行一人；世代+姓名+配/子/女/父/母；禁止分析段落。'

export const RELATION_TEXT_FORMAT_TEMPLATE = `===== 第 1 页 =====
一世 张公 男 字德明 生1920 配李氏 子张三,张四
一世 李氏 女 配张公

===== 第 2 页 =====
二世 张三 男 父张公 母李氏 生1950 配王氏 子张甲
二世 张四 男 父张公 母李氏

【关系】（可选，复杂谱面追加）
张公 → 张三（父子）
张公 配 李氏`

export const RELATION_TEXT_FORMAT_RULES = [
  '多页时必须用「===== 第 N 页 =====」与版本一 OCR 页码对齐',
  '每行一个真实人物：世代 + 姓名 + 男/女 + 配/子/女/父/母',
  '配偶单独成行或在【关系】块写「A 配 B」',
  '不要把「一世」「谱序」「长子」当作人名',
  '禁止前言、分析、总结；只写 RDL 正文',
]

export const RELATION_FORMAT_DOC_PATH = 'docs/PRD/族谱关系描述规范.md'
