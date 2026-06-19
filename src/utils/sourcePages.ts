/** 族谱原文按页拆分/合并（与 backend/source_pages.py 规则一致） */

export type SourcePageSlice = {
  page: number
  text: string
}

const PAGE_HEADER_RE = /^===== 第\s*(\d+)\s*(?:页|张)(?:\s*·.*?)?\s*=====\s*$/gm

export function splitPagedText(text: string): SourcePageSlice[] {
  const raw = (text || '').trim()
  if (!raw) return []

  const headers: { page: number; start: number; end: number }[] = []
  let match: RegExpExecArray | null
  const re = new RegExp(PAGE_HEADER_RE.source, 'gm')
  while ((match = re.exec(raw)) !== null) {
    headers.push({
      page: Number(match[1]),
      start: match.index,
      end: match.index + match[0].length,
    })
  }

  if (!headers.length) return [{ page: 1, text: raw }]

  const out: SourcePageSlice[] = []
  for (let i = 0; i < headers.length; i += 1) {
    const h = headers[i]
    const chunkStart = h.end
    const chunkEnd = i + 1 < headers.length ? headers[i + 1].start : raw.length
    out.push({
      page: h.page,
      text: raw.slice(chunkStart, chunkEnd).trim(),
    })
  }
  return out
}

export function mergePagedText(pages: SourcePageSlice[], unit: '页' | '张' = '页'): string {
  const parts: string[] = []
  for (const item of pages) {
    const text = (item.text || '').trim()
    if (!text) continue
    parts.push(`===== 第 ${item.page} ${unit} =====\n${text}`)
  }
  return parts.join('\n\n')
}

export function getPageText(text: string, page: number): string {
  return splitPagedText(text).find((p) => p.page === page)?.text || ''
}

export function setPageText(text: string, page: number, newText: string): string {
  let pages = splitPagedText(text)
  if (!pages.length) pages = [{ page: 1, text: '' }]
  const idx = pages.findIndex((p) => p.page === page)
  const next = (newText || '').trim()
  if (idx >= 0) pages[idx] = { ...pages[idx], text: next }
  else {
    pages = [...pages, { page, text: next }].sort((a, b) => a.page - b.page)
  }
  return mergePagedText(pages)
}

export function resolvePageCount(ocrText: string, imageCount: number): number {
  const fromText = splitPagedText(ocrText).length
  return Math.max(fromText, imageCount, 1)
}

export function buildPageList(
  ocrText: string,
  relationText: string,
  imagePaths: string[] = [],
  imagePreviews: string[] = [],
): Array<{
  page: number
  ocrText: string
  relationText: string
  imagePath?: string
  imagePreview?: string
}> {
  const count = resolvePageCount(ocrText, Math.max(imagePaths.length, imagePreviews.length))
  const ocrPages = splitPagedText(ocrText)
  const relPages = splitPagedText(relationText)
  const ocrMap = new Map(ocrPages.map((p) => [p.page, p.text]))
  const relMap = new Map(relPages.map((p) => [p.page, p.text]))

  const pages: Array<{
    page: number
    ocrText: string
    relationText: string
    imagePath?: string
    imagePreview?: string
  }> = []

  for (let i = 0; i < count; i += 1) {
    const page = ocrPages[i]?.page ?? relPages[i]?.page ?? i + 1
    pages.push({
      page,
      ocrText: ocrMap.get(page) || ocrPages[i]?.text || '',
      relationText: relMap.get(page) || relPages[i]?.text || '',
      imagePath: imagePaths[i],
      imagePreview: imagePreviews[i],
    })
  }
  return pages
}
