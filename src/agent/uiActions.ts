import type { AgentUiAction } from './types'

const TAB_LABELS: Record<string, string> = {
  tree: '树图',
  source: '原文',
  person: '成员',
  diff: '对比',
  organize: '整理',
}

const CLASSIC_PANEL_LABELS: Record<string, string> = {
  organize: '整理',
  source: '原文导入',
  export: '导出',
  search: '搜索',
}

export type GenealogyUiHandlers = {
  switchTab: (tab: string) => void
  focusPerson: (personId: string, name?: string) => void
  prefillPerson: (personId: string, draft: Record<string, unknown>, name?: string) => void
  setAnchor?: (personId: string, name?: string) => void
  openClassic?: (panel?: string) => void
  openSettings?: () => void
  openScan?: () => void
  selectFamily?: (familyId: string) => void
  scan?: () => void
  createFamily?: () => void
}

export function describeUiAction(action: AgentUiAction): string | null {
  if (action.type === 'switch_tab' && action.tab) {
    return `已切到【${TAB_LABELS[action.tab] || action.tab}】`
  }
  if (action.type === 'focus_person') {
    return action.name ? `已定位【${action.name}】` : '已定位成员'
  }
  if (action.type === 'prefill_person') {
    const n = Object.keys(action.draft || {}).length
    return n ? `已从对话提取 ${n} 项并预填成员页` : '已预填成员页'
  }
  if (action.type === 'set_anchor') {
    return action.name ? `已设「我在谱中」为【${action.name}】` : '已设置我在谱中的身份'
  }
  if (action.type === 'open_classic') {
    const p = action.panel ? CLASSIC_PANEL_LABELS[action.panel] || action.panel : ''
    return p ? `已打开经典编辑 · ${p}` : '已打开经典编辑'
  }
  if (action.type === 'open_settings') return '已打开设置'
  if (action.type === 'open_scan') return '已打开扫描建谱'
  if (action.type === 'select_family') return '已打开族谱'
  if (action.type === 'scan') return '打开扫描建谱'
  if (action.type === 'create_family') return '新建族谱'
  return null
}

export function applyGenealogyUiActions(
  actions: AgentUiAction[] | undefined,
  handlers: GenealogyUiHandlers,
): string[] {
  const hints: string[] = []
  for (const a of actions || []) {
    const hint = describeUiAction(a)
    if (hint) hints.push(hint)

    if (a.type === 'switch_tab' && a.tab) handlers.switchTab(a.tab)
    if (a.type === 'focus_person' && a.person_id) {
      handlers.focusPerson(a.person_id, a.name)
    }
    if (a.type === 'prefill_person' && a.person_id) {
      handlers.prefillPerson(a.person_id, a.draft || {}, a.name)
    }
    if (a.type === 'set_anchor' && a.person_id) handlers.setAnchor?.(a.person_id, a.name)
    if (a.type === 'open_classic') handlers.openClassic?.(a.panel)
    if (a.type === 'open_settings') handlers.openSettings?.()
    if (a.type === 'open_scan') handlers.openScan?.()
    if (a.type === 'select_family' && a.family_id) handlers.selectFamily?.(a.family_id)
    if (a.type === 'scan') handlers.scan?.()
    if (a.type === 'create_family') handlers.createFamily?.()
  }
  return hints
}

export function extractSourceExcerpt(sourceText: string, personName: string, maxLen = 320): string {
  const text = (sourceText || '').trim()
  const name = (personName || '').trim()
  if (!text || !name) return ''
  const idx = text.indexOf(name)
  if (idx < 0) return ''
  const half = Math.floor((maxLen - name.length) / 2)
  const start = Math.max(0, idx - half)
  const end = Math.min(text.length, idx + name.length + half)
  const prefix = start > 0 ? '…' : ''
  const suffix = end < text.length ? '…' : ''
  return prefix + text.slice(start, end) + suffix
}
