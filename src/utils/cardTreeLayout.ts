/** 参考图 1：卡片世代树布局 */

import type { ViewPerson, ViewRelation } from './genealogyViewData'
import { buildSpouseMap, groupByGeneration } from './genealogyViewData'

export const CARD_W = 72
export const CARD_H = 108
export const CARD_GAP = 14
export const ROW_GAP = 36
export const SIDEBAR_W = 52
export const PAD = 16

export interface CardUnitLayout {
  persons: ViewPerson[]
  x: number
  width: number
  centerX: number
  y: number
}

export interface CardRowLayout {
  generation: number
  y: number
  height: number
  units: CardUnitLayout[]
}

export interface CardEdge {
  x1: number
  y1: number
  x2: number
  y2: number
  kind: 'spouse' | 'parent' | 'bus'
}

export interface CardTreeLayout {
  width: number
  height: number
  rows: CardRowLayout[]
  edges: CardEdge[]
}

function packRowUnits(row: ViewPerson[], spouseMap: Map<string, string>): Omit<CardUnitLayout, 'x' | 'y'>[] {
  const placed = new Set<string>()
  const units: Omit<CardUnitLayout, 'x' | 'y'>[] = []

  for (const p of row) {
    if (placed.has(p.name)) continue
    const sp = spouseMap.get(p.name)
    const spouse = sp && row.find((q) => q.name === sp && !placed.has(q.name))
    if (spouse) {
      placed.add(p.name)
      placed.add(spouse.name)
      units.push({ persons: [p, spouse], width: CARD_W * 2 + CARD_GAP, centerX: 0 })
    } else {
      placed.add(p.name)
      units.push({ persons: [p], width: CARD_W, centerX: 0 })
    }
  }
  return units
}

export function layoutCardTree(persons: ViewPerson[], relations: ViewRelation[]): CardTreeLayout {
  const spouseMap = buildSpouseMap(relations)
  const genRows = groupByGeneration(persons)
  const rows: CardRowLayout[] = []
  const edges: CardEdge[] = []

  let y = PAD
  let maxW = SIDEBAR_W + PAD * 2

  for (const [generation, rowPersons] of genRows) {
    const rawUnits = packRowUnits(rowPersons, spouseMap)
    let x = SIDEBAR_W + PAD
    const units: CardUnitLayout[] = rawUnits.map((u) => {
      const centerX = x + u.width / 2
      const unit: CardUnitLayout = { ...u, x, y, centerX }
      x += u.width + CARD_GAP
      return unit
    })
    maxW = Math.max(maxW, x + PAD)

    for (const u of units) {
      if (u.persons.length === 2) {
        const midY = y + CARD_H * 0.42
        edges.push({
          x1: u.x + CARD_W,
          y1: midY,
          x2: u.x + CARD_W + CARD_GAP,
          y2: midY,
          kind: 'spouse',
        })
      }
    }

    rows.push({ generation, y, height: CARD_H + ROW_GAP, units })
    y += CARD_H + ROW_GAP
  }

  const parentRels = relations.filter((r) => r.type === 'parent_child')
  const nameToUnit = new Map<string, CardUnitLayout>()
  for (const row of rows) {
    for (const u of row.units) {
      for (const p of u.persons) nameToUnit.set(p.name, u)
    }
  }

  function unitKey(u: CardUnitLayout): string {
    return u.persons.map((p) => p.name).sort().join('|')
  }

  const childrenByUnit = new Map<string, { unit: CardUnitLayout; childNames: Set<string> }>()
  for (const rel of parentRels) {
    const parentUnit = nameToUnit.get(rel.from)
    if (!parentUnit) continue
    const key = unitKey(parentUnit)
    if (!childrenByUnit.has(key)) childrenByUnit.set(key, { unit: parentUnit, childNames: new Set() })
    childrenByUnit.get(key)!.childNames.add(rel.to)
  }

  for (const { unit: parentUnit, childNames } of childrenByUnit.values()) {
    const childUnits = [...childNames]
      .map((n) => nameToUnit.get(n))
      .filter((u): u is CardUnitLayout => !!u && u.y > parentUnit.y)
    if (!childUnits.length) continue

    const busY = parentUnit.y + CARD_H + ROW_GAP / 2
    edges.push({
      x1: parentUnit.centerX,
      y1: parentUnit.y + CARD_H,
      x2: parentUnit.centerX,
      y2: busY,
      kind: 'parent',
    })

    const xs = childUnits.map((u) => u.centerX)
    const minX = Math.min(...xs, parentUnit.centerX)
    const maxX = Math.max(...xs, parentUnit.centerX)
    if (childUnits.length > 1 || minX !== maxX) {
      edges.push({ x1: minX, y1: busY, x2: maxX, y2: busY, kind: 'bus' })
    }

    for (const cu of childUnits) {
      edges.push({ x1: cu.centerX, y1: busY, x2: cu.centerX, y2: cu.y, kind: 'parent' })
    }
  }

  return { width: maxW, height: y + PAD, rows, edges }
}
