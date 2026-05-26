/** 参考图 2：谱页世系（右主左支）布局 */

import type { ViewPerson, ViewRelation } from './genealogyViewData'
import { buildChildrenMap, findRoots, groupByGeneration } from './genealogyViewData'

export const NODE_W = 36
export const NODE_H = 72
export const ROW_H = 96
export const GUTTER_W = 48
export const PAD = 20

export interface SilkwormNodeLayout {
  person: ViewPerson
  x: number
  y: number
  cx: number
  cy: number
}

export interface SilkwormEdge {
  x1: number
  y1: number
  x2: number
  y2: number
}

export interface SilkwormPageLayout {
  width: number
  height: number
  nodes: SilkwormNodeLayout[]
  edges: SilkwormEdge[]
  generations: number[]
}

interface TreeNode {
  person: ViewPerson
  children: TreeNode[]
  width: number
  x: number
}

function buildTree(
  name: string,
  byName: Map<string, ViewPerson>,
  childrenMap: Map<string, string[]>,
  visiting: Set<string>,
): TreeNode | null {
  const person = byName.get(name)
  if (!person || visiting.has(name)) return null
  visiting.add(name)
  const childNames = childrenMap.get(name) || []
  const children: TreeNode[] = []
  for (const cn of childNames) {
    const c = buildTree(cn, byName, childrenMap, visiting)
    if (c) children.push(c)
  }
  visiting.delete(name)
  children.sort((a, b) => a.person.name.localeCompare(b.person.name, 'zh'))
  const width = Math.max(1, children.reduce((s, c) => s + c.width, 0))
  return { person, children, width, x: 0 }
}

function assignX(node: TreeNode, left: number): number {
  if (!node.children.length) {
    node.x = left
    return left + 1
  }
  let cursor = left
  for (const c of node.children) cursor = assignX(c, cursor)
  const first = node.children[0]
  const last = node.children[node.children.length - 1]
  node.x = (first.x + last.x) / 2
  return cursor
}

export function layoutSilkwormPage(persons: ViewPerson[], relations: ViewRelation[]): SilkwormPageLayout {
  if (!persons.length) {
    return { width: 320, height: 240, nodes: [], edges: [], generations: [] }
  }

  const genRows = groupByGeneration(persons)
  const generations = genRows.map(([g]) => g)
  const minGen = generations[0] ?? 1

  if (!relations.some((r) => r.type === 'parent_child')) {
    const nodes: SilkwormNodeLayout[] = []
    const gutterReserve = GUTTER_W + 16
    let contentMax = PAD
    for (const [gen, row] of genRows) {
      const y = PAD + (gen - minGen) * ROW_H
      let x = PAD
      for (const p of [...row].reverse()) {
        nodes.push({
          person: p,
          x,
          y,
          cx: x + NODE_W / 2,
          cy: y + NODE_H / 2,
        })
        x += NODE_W + 12
      }
      contentMax = Math.max(contentMax, x)
    }
    return {
      width: contentMax + gutterReserve + PAD,
      height: PAD * 2 + generations.length * ROW_H,
      nodes,
      edges: [],
      generations,
    }
  }

  const byName = new Map(persons.map((p) => [p.name, p]))
  const childrenMap = buildChildrenMap(relations)
  const roots = findRoots(persons, childrenMap)
  const forest: TreeNode[] = []
  for (const root of roots) {
    const t = buildTree(root.name, byName, childrenMap, new Set())
    if (t) forest.push(t)
  }

  let offset = 0
  for (const t of forest) {
    assignX(t, offset)
    offset += t.width + 1
  }

  const nodes: SilkwormNodeLayout[] = []
  const edges: SilkwormEdge[] = []

  function walk(n: TreeNode) {
    const y = PAD + (n.person.generation - minGen) * ROW_H
    const x = PAD + n.x * (NODE_W + 12)
    const cx = x + NODE_W / 2
    nodes.push({ person: n.person, x, y, cx, cy: y + NODE_H / 2 })
    for (const c of n.children) walk(c)
  }

  for (const t of forest) walk(t)

  // 右主左支：镜像到内容区，右侧预留世系栏
  const gutterReserve = GUTTER_W + 16
  let minX = Math.min(...nodes.map((n) => n.x), PAD)
  let maxX = Math.max(...nodes.map((n) => n.x + NODE_W), PAD + 80)
  const contentSpan = maxX - minX + PAD
  const mirrorRight = PAD + contentSpan
  for (const n of nodes) {
    n.x = mirrorRight - (n.x + NODE_W) + PAD
    n.cx = n.x + NODE_W / 2
  }
  maxX = Math.max(...nodes.map((n) => n.x + NODE_W), PAD + 80)
  minX = Math.min(...nodes.map((n) => n.x), PAD)

  const contentWidth = maxX + PAD
  const totalWidth = contentWidth + gutterReserve + PAD

  const nodeByName = new Map(nodes.map((n) => [n.person.name, n]))

  function addForkEdges(n: TreeNode) {
    const parent = nodeByName.get(n.person.name)
    if (!parent || !n.children.length) {
      for (const c of n.children) addForkEdges(c)
      return
    }
    const childLayouts = n.children
      .map((c) => nodeByName.get(c.person.name))
      .filter((c): c is SilkwormNodeLayout => !!c)
    if (!childLayouts.length) return

    const branchY = parent.y + NODE_H + (childLayouts[0].y - parent.y - NODE_H) * 0.42
    edges.push({ x1: parent.cx, y1: parent.y + NODE_H, x2: parent.cx, y2: branchY })
    const xs = [parent.cx, ...childLayouts.map((c) => c.cx)]
    const minX = Math.min(...xs)
    const maxX = Math.max(...xs)
    if (minX !== maxX) {
      edges.push({ x1: minX, y1: branchY, x2: maxX, y2: branchY })
    }
    for (const c of childLayouts) {
      edges.push({ x1: c.cx, y1: branchY, x2: c.cx, y2: c.y })
    }
    for (const c of n.children) addForkEdges(c)
  }

  for (const t of forest) addForkEdges(t)

  const maxY = Math.max(...nodes.map((n) => n.y + NODE_H), 200) + PAD

  return { width: totalWidth, height: maxY, nodes, edges, generations }
}
