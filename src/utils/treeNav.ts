/** 从成员列表构建左侧树状导航 */

export interface NavNode {
  id: string
  name: string
  generation?: number
  gender?: string
  children: NavNode[]
}

export interface FlatNavItem {
  id: string
  name: string
  generation?: number
  depth: number
  hasChildren: boolean
  expanded: boolean
}

export function buildPersonTree(
  persons: Array<{ id: string; name: string; parent_id?: string | null; generation?: number; gender?: string }>,
): NavNode[] {
  const byParent: Record<string, typeof persons> = {}
  const ids = new Set(persons.map((p) => p.id))

  for (const p of persons) {
    const pid = p.parent_id && ids.has(p.parent_id) ? p.parent_id : '__root__'
    if (!byParent[pid]) byParent[pid] = []
    byParent[pid].push(p)
  }

  const sortFn = (a: (typeof persons)[0], b: (typeof persons)[0]) =>
    (a.generation || 0) - (b.generation || 0) || (a.name || '').localeCompare(b.name || '', 'zh')

  function walk(parentKey: string): NavNode[] {
    return (byParent[parentKey] || []).sort(sortFn).map((p) => ({
      id: p.id,
      name: p.name,
      generation: p.generation,
      gender: p.gender,
      children: walk(p.id),
    }))
  }

  return walk('__root__')
}

export function flattenNavTree(
  nodes: NavNode[],
  expanded: Set<string>,
  depth = 0,
): FlatNavItem[] {
  const out: FlatNavItem[] = []
  for (const n of nodes) {
    const hasChildren = n.children.length > 0
    const isExpanded = expanded.has(n.id)
    out.push({
      id: n.id,
      name: n.name,
      generation: n.generation,
      depth,
      hasChildren,
      expanded: isExpanded,
    })
    if (hasChildren && isExpanded) {
      out.push(...flattenNavTree(n.children, expanded, depth + 1))
    }
  }
  return out
}

export function collectAllNavIds(nodes: NavNode[]): string[] {
  const ids: string[] = []
  function walk(list: NavNode[]) {
    for (const n of list) {
      ids.push(n.id)
      if (n.children.length) walk(n.children)
    }
  }
  walk(nodes)
  return ids
}
