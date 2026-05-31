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

export function parseTextToViewRelations(text: string): ViewRelation[] {
  const rels: ViewRelation[] = []
  const seen = new Set<string>()
  for (const line of (text || '').split(/\r?\n/)) {
    const s = line.trim()
    if (!s) continue
    const spouse = s.match(/([\u4e00-\u9fff]{1,4})\s*配\s*([\u4e00-\u9fff]{1,4})/)
    if (spouse) {
      const key = `spouse:${spouse[1]}:${spouse[2]}`
      if (!seen.has(key)) {
        seen.add(key)
        rels.push({ from: spouse[1], to: spouse[2], type: 'spouse' })
      }
      continue
    }
    const pc = s.match(/([\u4e00-\u9fff]{1,4})\s*(?:→|->|—|-)\s*([\u4e00-\u9fff]{1,4})/)
    if (pc) {
      const key = `pc:${pc[1]}:${pc[2]}`
      if (!seen.has(key)) {
        seen.add(key)
        rels.push({ from: pc[1], to: pc[2], type: 'parent_child' })
      }
    }
  }
  return rels
}

export function mapApiRelations(raw: any[], personSource?: any[]): ViewRelation[] {
  const idToName = new Map<string, string>()
  for (const p of personSource || []) {
    const id = p?.id != null ? String(p.id) : ''
    const name = (p?.name || '').trim()
    if (id && name) idToName.set(id, name)
  }

  const rels: ViewRelation[] = []
  const seen = new Set<string>()

  for (const r of raw || []) {
    let from = (r.from || r.from_name || '').trim()
    let to = (r.to || r.to_name || '').trim()
    const fid = r.from_person_id != null ? String(r.from_person_id) : ''
    const tid = r.to_person_id != null ? String(r.to_person_id) : ''
    if (!from && fid) from = idToName.get(fid) || ''
    if (!to && tid) to = idToName.get(tid) || ''
    if (!from || !to) continue
    const type = (r.type || r.relation_type || 'parent_child') as ViewRelation['type']
    const key = `${type}:${from}:${to}`
    if (seen.has(key)) continue
    seen.add(key)
    rels.push({ from, to, type })
  }
  return rels
}

/** 从 parent_id / spouse_ids 补全缺失的关系边 */
export function enrichRelationsFromPersons(rawPersons: any[], relations: ViewRelation[]): ViewRelation[] {
  const rels = [...relations]
  const seen = new Set(rels.map((r) => `${r.type}:${r.from}:${r.to}`))
  const byId = new Map<string, any>()
  for (const p of rawPersons || []) {
    if (p?.id) byId.set(String(p.id), p)
  }

  for (const p of rawPersons || []) {
    const name = (p.name || '').trim()
    if (!name) continue
    const parentId = p.parent_id != null ? String(p.parent_id) : ''
    if (parentId) {
      const parent = byId.get(parentId)
      const parentName = (parent?.name || '').trim()
      if (parentName) {
        const key = `parent_child:${parentName}:${name}`
        if (!seen.has(key)) {
          seen.add(key)
          rels.push({ from: parentName, to: name, type: 'parent_child' })
        }
      }
    }
    let spouseIds: string[] = []
    try {
      const raw = p.spouse_ids
      if (typeof raw === 'string' && raw.trim()) spouseIds = JSON.parse(raw)
      else if (Array.isArray(raw)) spouseIds = raw
    } catch {
      spouseIds = []
    }
    for (const sid of spouseIds) {
      const sp = byId.get(String(sid))
      const spName = (sp?.name || '').trim()
      if (!spName) continue
      const a = name < spName ? name : spName
      const b = name < spName ? spName : name
      const key = `spouse:${a}:${b}`
      if (!seen.has(key)) {
        seen.add(key)
        rels.push({ from: a, to: b, type: 'spouse' })
      }
    }
  }
  return rels
}

export function mapApiRelationsLegacy(raw: any[]): ViewRelation[] {
  return mapApiRelations(raw, [])
}

export function resolveViewData(opts: {
  persons?: any[]
  relations?: any[]
  structuredText?: string
  rawText?: string
}): { persons: ViewPerson[]; relations: ViewRelation[] } {
  const rawPersons = opts.persons || []
  const text = (opts.structuredText || opts.rawText || '').trim()

  let persons: ViewPerson[] = rawPersons.length ? mapApiPersons(rawPersons) : parseTextToViewPersons(text)
  let relations = mapApiRelations(opts.relations || [], rawPersons.length ? rawPersons : persons)
  relations = enrichRelationsFromPersons(rawPersons, relations)

  if (!relations.length && text) {
    relations = parseTextToViewRelations(text)
  }
  if (!persons.length && text) {
    persons = parseTextToViewPersons(text)
  }
  return { persons, relations }
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

export function mapFamilyRelations(raw: any[], personSource?: any[]): ViewRelation[] {
  return mapApiRelations(raw, personSource)
}

export function findRoots(persons: ViewPerson[], childrenMap: Map<string, string[]>) {
  const allChildren = new Set<string>()
  for (const kids of childrenMap.values()) kids.forEach((k) => allChildren.add(k))
  const roots = persons.filter((p) => !allChildren.has(p.name))
  if (roots.length) return roots.sort((a, b) => a.generation - b.generation)
  return persons.length ? [persons.sort((a, b) => a.generation - b.generation)[0]] : []
}
