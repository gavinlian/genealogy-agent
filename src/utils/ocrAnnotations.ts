export interface NameAnnotation {
  id: string
  name: string
  start: number
  end: number
  source: 'manual' | 'ai'
}

export interface TextSegment {
  key: string
  text: string
  type: 'plain' | 'name'
  annotationId?: string
}

export const NAME_DRAG_MIME = 'application/x-genealogy-name'

export function makeAnnotationId(name: string, start: number, end: number): string {
  return `${start}-${end}-${name}`
}

/** 将原文切分为普通文字与姓名标注段，用于高亮展示 */
export function buildTextSegments(text: string, annotations: NameAnnotation[]): TextSegment[] {
  if (!text) return []
  const sorted = [...annotations]
    .filter((a) => a.start >= 0 && a.end > a.start && a.end <= text.length)
    .sort((a, b) => a.start - b.start)

  const segments: TextSegment[] = []
  let cursor = 0

  for (const ann of sorted) {
    if (ann.start < cursor) continue
    if (ann.start > cursor) {
      segments.push({
        key: `p-${cursor}`,
        text: text.slice(cursor, ann.start),
        type: 'plain',
      })
    }
    segments.push({
      key: ann.id,
      text: text.slice(ann.start, ann.end),
      type: 'name',
      annotationId: ann.id,
    })
    cursor = ann.end
  }

  if (cursor < text.length) {
    segments.push({ key: `p-${cursor}`, text: text.slice(cursor), type: 'plain' })
  }

  return segments
}

/** 文字编辑后，按姓名重新定位标注（尽量保留原顺序） */
export function remapAnnotations(text: string, annotations: NameAnnotation[]): NameAnnotation[] {
  if (!text) return []
  const result: NameAnnotation[] = []
  const used: Array<[number, number]> = []

  for (const ann of annotations) {
    let idx = text.indexOf(ann.name, Math.min(ann.start, text.length))
    while (idx !== -1) {
      const end = idx + ann.name.length
      const overlap = used.some(([s, e]) => !(end <= s || idx >= e))
      if (!overlap) {
        used.push([idx, end])
        result.push({
          ...ann,
          id: makeAnnotationId(ann.name, idx, end),
          start: idx,
          end,
        })
        break
      }
      idx = text.indexOf(ann.name, idx + 1)
    }
  }

  return result.sort((a, b) => a.start - b.start)
}

export function mergeAnnotations(
  existing: NameAnnotation[],
  incoming: NameAnnotation[],
): NameAnnotation[] {
  const map = new Map<string, NameAnnotation>()
  for (const a of [...existing, ...incoming]) {
    const key = `${a.start}-${a.end}-${a.name}`
    map.set(key, a)
  }
  return [...map.values()].sort((a, b) => a.start - b.start)
}

export function annotationPayload(ann: NameAnnotation) {
  return JSON.stringify({
    name: ann.name,
    start: ann.start,
    end: ann.end,
    source: ann.source,
  })
}

/** 修正标注姓名：同步替换原文对应片段并重算标注位置 */
export function renameAnnotationInText(
  text: string,
  annotations: NameAnnotation[],
  annotationId: string,
  newName: string,
): { text: string; annotations: NameAnnotation[] } {
  const trimmed = newName.trim()
  if (!trimmed) return { text, annotations }
  const ann = annotations.find((a) => a.id === annotationId)
  if (!ann || ann.start < 0 || ann.end > text.length) {
    return { text, annotations }
  }
  const nextText = text.slice(0, ann.start) + trimmed + text.slice(ann.end)
  const delta = trimmed.length - (ann.end - ann.start)
  const nextAnnotations = annotations
    .map((a) => {
      if (a.id === annotationId) {
        const end = ann.start + trimmed.length
        return {
          ...a,
          name: trimmed,
          start: ann.start,
          end,
          id: makeAnnotationId(trimmed, ann.start, end),
        }
      }
      if (a.start >= ann.end) {
        return {
          ...a,
          start: a.start + delta,
          end: a.end + delta,
          id: makeAnnotationId(a.name, a.start + delta, a.end + delta),
        }
      }
      return a
    })
    .filter((a) => a.start >= 0 && a.end <= nextText.length)
  return { text: nextText, annotations: nextAnnotations.sort((a, b) => a.start - b.start) }
}
