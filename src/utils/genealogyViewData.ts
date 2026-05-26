/** 族谱查看模式：共享数据与文本解析 */

export interface ViewPerson {
  id: string
  name: string
  gender: 'male' | 'female' | 'unknown'
  generation: number
}

export interface ViewRelation {
  from: string
  to: string
  type: 'parent_child' | 'spouse' | string
}

const GEN_PREFIX = /^(?:第?\s*([0-9一二三四五六七八九十百千万]+)\s*(?:世|代)|([0-9一二三四五六七八九十百千万]+)\s*世)\s*(.*)$/
const CN: Record<string, number> = {
  一: 1, 二: 2, 三: 3, 四: 4, 五: 5, 六: 6, 七: 7, 八: 8, 九: 9, 十: 10,
  十一: 11, 十二: 12, 十三: 13, 十四: 14, 十五: 15, 十六: 16, 十七: 17, 十八: 18,
}

function cnNum(s: string): number {
  if (/^\d+$/.test(s)) return parseInt(s, 10)
  if (CN[s] != null) return CN[s]
  if (s.startsWith('十') && s.length === 2 && CN[s[1]] != null) return 10 + CN[s[1]]
  return 1
}

function pickName(rest: string): string | null {
  const m = (rest || '').trim().match(/^([\u4e00-\u9fff]{1,4}(?:公|郎|氏)?)/)
  return m?.[1] || null
}

function inferGender(snippet: string): ViewPerson['gender'] {
  const s = snippet.slice(0, 16)
  if (/女|配/.test(s)) return 'female'
  if (/男/.test(s)) return 'male'
  return 'unknown'
}

export function parseTextToViewPersons(text: string): ViewPerson[] {
  const lines = (text || '').split(/\r?\n/).map((l) => l.trim()).filter(Boolean)
  const out: ViewPerson[] = []
  const seen = new Set<string>()
  let lastGen = 1

  for (const line of lines) {
    let gen = lastGen
    let rest = line
    const m = line.match(GEN_PREFIX)
    if (m) {
      gen = cnNum(m[1] || m[2] || '1')
      rest = m[3] || ''
      lastGen = gen
    }
    const name = pickName(rest)
    if (!name || seen.has(`${gen}:${name}`)) continue
    seen.add(`${gen}:${name}`)
    out.push({
      id: `t-${gen}-${name}-${out.length}`,
      name,
      gender: inferGender(rest),
      generation: gen,
    })
  }
  return out
}

export function mapApiPersons(raw: any[]): ViewPerson[] {
  return (raw || [])
    .map((p, i) => ({
      id: String(p.id || `p-${i}-${p.name}`),
      name: (p.name || '').trim(),
      gender: (p.gender === 'female' || p.gender === 'male' ? p.gender : 'unknown') as ViewPerson['gender'],
      generation: Number(p.generation) || 1,
    }))
    .filter((p) => p.name)
}

export function mapApiRelations(raw: any[]): ViewRelation[] {
  return (raw || [])
    .map((r) => ({
      from: (r.from || r.from_name || '').trim(),
      to: (r.to || r.to_name || '').trim(),
      type: (r.type || r.relation_type || 'parent_child') as ViewRelation['type'],
    }))
    .filter((r) => r.from && r.to)
}

export function resolveViewData(opts: {
  persons?: any[]
  relations?: any[]
  structuredText?: string
  rawText?: string
}): { persons: ViewPerson[]; relations: ViewRelation[] } {
  const relations = mapApiRelations(opts.relations || [])
  if (opts.persons?.length) {
    return { persons: mapApiPersons(opts.persons), relations }
  }
  const text = (opts.structuredText || opts.rawText || '').trim()
  return { persons: parseTextToViewPersons(text), relations }
}

export function groupByGeneration(persons: ViewPerson[]) {
  const map = new Map<number, ViewPerson[]>()
  for (const p of persons) {
    const g = p.generation || 1
    if (!map.has(g)) map.set(g, [])
    map.get(g)!.push(p)
  }
  return [...map.entries()].sort((a, b) => a[0] - b[0])
}

export function buildChildrenMap(relations: ViewRelation[]) {
  const m = new Map<string, string[]>()
  for (const r of relations) {
    if (r.type !== 'parent_child') continue
    if (!m.has(r.from)) m.set(r.from, [])
    m.get(r.from)!.push(r.to)
  }
  return m
}

export function buildSpouseMap(relations: ViewRelation[]) {
  const m = new Map<string, string>()
  for (const r of relations) {
    if (r.type !== 'spouse') continue
    m.set(r.from, r.to)
    m.set(r.to, r.from)
  }
  return m
}

export function mapFamilyRelations(raw: any[]): ViewRelation[] {
  return (raw || [])
    .map((r) => ({
      from: (r.from_name || r.from || '').trim(),
      to: (r.to_name || r.to || '').trim(),
      type: (r.relation_type === 'spouse' ? 'spouse' : 'parent_child') as ViewRelation['type'],
    }))
    .filter((r) => r.from && r.to)
}

export function findRoots(persons: ViewPerson[], childrenMap: Map<string, string[]>) {
  const allChildren = new Set<string>()
  for (const kids of childrenMap.values()) kids.forEach((k) => allChildren.add(k))
  const roots = persons.filter((p) => !allChildren.has(p.name))
  if (roots.length) return roots.sort((a, b) => a.generation - b.generation)
  return persons.length ? [persons.sort((a, b) => a.generation - b.generation)[0]] : []
}
