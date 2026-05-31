/** 选中一人时，计算应高亮的成员与关系（本人、父母、子女、配偶、兄弟姐妹）。 */

export type FocusPerson = { id: string; name: string; parent_id?: string | null }
export type FocusRelation = {
  from?: string
  to?: string
  from_person_id?: string
  to_person_id?: string
  type?: string
  relation_type?: string
}

function relKey(fromId: string, toId: string, type: string) {
  return `${fromId}|${toId}|${type}`
}

export function buildFocusNeighborhood(
  persons: FocusPerson[],
  relations: FocusRelation[],
  focusIdOrName: string | null | undefined,
): { personIds: Set<string>; relationKeys: Set<string> } {
  const empty = { personIds: new Set<string>(), relationKeys: new Set<string>() }
  if (!focusIdOrName || !persons.length) return empty

  const byId = new Map(persons.map((p) => [p.id, p]))
  const byName = new Map(persons.map((p) => [p.name, p]))
  const focus = byId.get(focusIdOrName) || byName.get(focusIdOrName)
  if (!focus) return empty

  const personIds = new Set<string>([focus.id])
  const relationKeys = new Set<string>()

  const parentEdges: Array<{ parentId: string; childId: string; type: string }> = []
  const spouseEdges: Array<{ a: string; b: string; type: string }> = []

  for (const r of relations) {
    const type = r.type || r.relation_type || 'parent_child'
    let fromId = r.from_person_id || ''
    let toId = r.to_person_id || ''
    if (!fromId && r.from) fromId = byName.get(r.from)?.id || ''
    if (!toId && r.to) toId = byName.get(r.to)?.id || ''
    if (!fromId || !toId) continue

    if (type === 'spouse') {
      spouseEdges.push({ a: fromId, b: toId, type })
    } else {
      parentEdges.push({ parentId: fromId, childId: toId, type })
    }
  }

  for (const e of parentEdges) {
    if (e.childId === focus.id) {
      personIds.add(e.parentId)
      relationKeys.add(relKey(e.parentId, e.childId, e.type))
    }
    if (e.parentId === focus.id) {
      personIds.add(e.childId)
      relationKeys.add(relKey(e.parentId, e.childId, e.type))
    }
  }

  for (const e of spouseEdges) {
    if (e.a === focus.id || e.b === focus.id) {
      personIds.add(e.a)
      personIds.add(e.b)
      relationKeys.add(relKey(e.a, e.b, e.type))
      relationKeys.add(relKey(e.b, e.a, e.type))
    }
  }

  const parentIds = new Set<string>()
  for (const e of parentEdges) {
    if (e.childId === focus.id) parentIds.add(e.parentId)
  }
  for (const e of parentEdges) {
    if (parentIds.has(e.parentId) && e.childId !== focus.id) {
      personIds.add(e.childId)
      relationKeys.add(relKey(e.parentId, e.childId, e.type))
    }
  }

  return { personIds, relationKeys }
}

export function isPersonFocused(
  personId: string,
  focus: { personIds: Set<string> },
  hasFocus: boolean,
): boolean {
  if (!hasFocus) return true
  return focus.personIds.has(personId)
}

export function isEdgeFocused(
  fromId: string,
  toId: string,
  type: string,
  focus: { relationKeys: Set<string> },
  hasFocus: boolean,
): boolean {
  if (!hasFocus) return true
  return focus.relationKeys.has(relKey(fromId, toId, type))
}
