/** 与后端 name_extractor 一致的姓名长度与校验（前端标注用） */

export const PERSON_NAME_MIN_LEN = 1
export const PERSON_NAME_MAX_LEN = 4

const INVALID_STANDALONE = new Set(
  '谱序记碑言世系表传略葬配卒生卒于享之子男女长次公元郎户人家嗣祧',
)

export function normalizeSelectedName(raw: string): string {
  return (raw || '').trim().replace(/\s+/g, '').slice(0, PERSON_NAME_MAX_LEN)
}

export function isValidPersonNameForMark(name: string): boolean {
  const n = normalizeSelectedName(name)
  if (!n || n.length < PERSON_NAME_MIN_LEN || n.length > PERSON_NAME_MAX_LEN) return false
  if (!/^[\u4e00-\u9fff]+$/.test(n)) return false
  if (n.length === 1 && INVALID_STANDALONE.has(n)) return false
  const blocklist = new Set(['谱序', '长子', '次子', '一世', '二世', '族谱', '男', '女'])
  if (blocklist.has(n)) return false
  return true
}

export function personNameHint(name: string): string {
  const n = normalizeSelectedName(name)
  if (!n) return ''
  if (n.length === 1) return `单字名「${n}」（可与姓组合为两字全名）`
  if (n.length === 2) return `两字姓名「${n}」（常见：单姓+单字名）`
  return `已选「${n}」`
}
