/** 关系图布局（Obsidian 风格：力导向 + 世代分层） */

import type { ViewPerson, ViewRelation } from './genealogyViewData'

export interface GraphNodeLayout {
  id: string
  name: string
  gender: ViewPerson['gender']
  generation: number
  x: number
  y: number
  r: number
}

export interface GraphEdgeLayout {
  fromId: string
  toId: string
  type: string
  x1: number
  y1: number
  x2: number
  y2: number
}

export interface RelationGraphLayout {
  width: number
  height: number
  nodes: GraphNodeLayout[]
  edges: GraphEdgeLayout[]
}

const NODE_R = 22

export function layoutRelationGraph(
  persons: ViewPerson[],
  relations: ViewRelation[],
  opts?: { width?: number; height?: number },
): RelationGraphLayout {
  if (!persons.length) {
    return { width: 400, height: 300, nodes: [], edges: [] }
  }

  const byName = new Map(persons.map((p) => [p.name, p]))
  const nodes: GraphNodeLayout[] = persons.map((p, i) => {
    const col = i % 6
    const row = Math.floor(i / 6)
    return {
      id: p.id,
      name: p.name,
      gender: p.gender,
      generation: p.generation || 1,
      x: 80 + col * 100,
      y: 60 + (p.generation - 1) * 90 + row * 8,
      r: NODE_R,
    }
  })
  const byId = new Map(nodes.map((n) => [n.id, n]))
  const nameToId = new Map(nodes.map((n) => [n.name, n.id]))

  const edgePairs: { fromId: string; toId: string; type: string }[] = []
  for (const r of relations) {
    const fromId = nameToId.get(r.from)
    const toId = nameToId.get(r.to)
    if (!fromId || !toId || fromId === toId) continue
    edgePairs.push({ fromId, toId, type: r.type || 'parent_child' })
  }

  // 力导向迭代：斥力 + 边拉力 + 世代纵向约束
  for (let iter = 0; iter < 100; iter++) {
    const damp = 0.85 - iter * 0.004
    for (let i = 0; i < nodes.length; i++) {
      for (let j = i + 1; j < nodes.length; j++) {
        const a = nodes[i]
        const b = nodes[j]
        let dx = b.x - a.x
        let dy = b.y - a.y
        let dist = Math.hypot(dx, dy) || 1
        const minDist = 70
        if (dist < minDist) {
          const push = ((minDist - dist) / dist) * 8 * damp
          dx *= push
          dy *= push
          a.x -= dx
          a.y -= dy
          b.x += dx
          b.y += dy
        }
      }
    }
    for (const e of edgePairs) {
      const a = byId.get(e.fromId)
      const b = byId.get(e.toId)
      if (!a || !b) continue
      let dx = b.x - a.x
      let dy = b.y - a.y
      let dist = Math.hypot(dx, dy) || 1
      const target = e.type === 'spouse' ? 90 : 120
      const pull = (dist - target) * 0.04 * damp
      dx = (dx / dist) * pull
      dy = (dy / dist) * pull
      a.x += dx
      a.y += dy
      b.x -= dx
      b.y -= dy
    }
    for (const n of nodes) {
      const targetY = 50 + (n.generation - 1) * 88
      n.y += (targetY - n.y) * 0.08
    }
  }

  let minX = Infinity
  let minY = Infinity
  let maxX = -Infinity
  let maxY = -Infinity
  for (const n of nodes) {
    minX = Math.min(minX, n.x - NODE_R)
    minY = Math.min(minY, n.y - NODE_R)
    maxX = Math.max(maxX, n.x + NODE_R)
    maxY = Math.max(maxY, n.y + NODE_R)
  }
  const pad = 48
  for (const n of nodes) {
    n.x = n.x - minX + pad
    n.y = n.y - minY + pad
  }

  const edges: GraphEdgeLayout[] = edgePairs.map((e) => {
    const a = byId.get(e.fromId)!
    const b = byId.get(e.toId)!
    return {
      ...e,
      x1: a.x,
      y1: a.y,
      x2: b.x,
      y2: b.y,
    }
  })

  const width = Math.max(opts?.width || 0, maxX - minX + pad * 2, 360)
  const height = Math.max(opts?.height || 0, maxY - minY + pad * 2, 280)

  return { width, height, nodes, edges }
}
