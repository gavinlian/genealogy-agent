/** 首页（全局）多会话 — localStorage 持久化 */
import type { AgentMessage } from './types'

export type HomeChatSession = {
  id: string
  title: string
  messages: AgentMessage[]
  updatedAt: number
}

const STORAGE_KEY = 'genealogy-agent-home-sessions'

type HomeSessionsStore = {
  activeId: string
  sessions: HomeChatSession[]
}

function newSessionId(): string {
  try {
    if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
      return crypto.randomUUID().slice(0, 10)
    }
  } catch {
    /* 手机 http://局域网IP 非安全上下文，randomUUID 不可用 */
  }
  return `s${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`
}

function emptyStore(): HomeSessionsStore {
  const id = newSessionId()
  return {
    activeId: id,
    sessions: [{ id, title: '默认会话', messages: [], updatedAt: Date.now() }],
  }
}

export function loadHomeSessionsStore(): HomeSessionsStore {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return emptyStore()
    const data = JSON.parse(raw) as HomeSessionsStore
    if (!data.sessions?.length) return emptyStore()
    if (!data.activeId || !data.sessions.some((s) => s.id === data.activeId)) {
      data.activeId = data.sessions[0].id
    }
    return data
  } catch {
    return emptyStore()
  }
}

export function saveHomeSessionsStore(store: HomeSessionsStore) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(store))
  } catch {
    /* quota */
  }
}

export function getActiveHomeSession(store: HomeSessionsStore): HomeChatSession {
  return store.sessions.find((s) => s.id === store.activeId) || store.sessions[0]
}

export function deriveSessionTitle(messages: AgentMessage[]): string {
  const firstUser = messages.find((m) => m.role === 'user' && m.content?.trim())
  if (!firstUser) return '新会话'
  const text = firstUser.content.trim()
  return text.length > 18 ? `${text.slice(0, 18)}…` : text
}

export function upsertActiveHomeSession(
  store: HomeSessionsStore,
  messages: AgentMessage[],
): HomeSessionsStore {
  const active = getActiveHomeSession(store)
  const title = deriveSessionTitle(messages) || active.title
  const nextSessions = store.sessions.map((s) =>
    s.id === active.id
      ? {
          ...s,
          messages,
          title: s.title === '默认会话' || s.title === '新会话' ? title : s.title,
          updatedAt: Date.now(),
        }
      : s,
  )
  return { ...store, sessions: nextSessions }
}

export function createHomeSession(store: HomeSessionsStore): HomeSessionsStore {
  const id = newSessionId()
  const session: HomeChatSession = { id, title: '新会话', messages: [], updatedAt: Date.now() }
  return {
    activeId: id,
    sessions: [session, ...store.sessions].slice(0, 12),
  }
}

export function switchHomeSession(store: HomeSessionsStore, sessionId: string): HomeSessionsStore | null {
  if (!store.sessions.some((s) => s.id === sessionId)) return null
  return { ...store, activeId: sessionId }
}

export function deleteHomeSession(store: HomeSessionsStore, sessionId: string): HomeSessionsStore {
  const rest = store.sessions.filter((s) => s.id !== sessionId)
  if (!rest.length) return emptyStore()
  const activeId = store.activeId === sessionId ? rest[0].id : store.activeId
  return { activeId, sessions: rest }
}

const ENTRY_CTX_PREFIX = 'genealogy-agent-entry-context:'

export function stashFamilyEntryContext(familyId: string, userMessage: string) {
  if (!familyId || !userMessage.trim()) return
  try {
    sessionStorage.setItem(`${ENTRY_CTX_PREFIX}${familyId}`, userMessage.trim())
  } catch {
    /* ignore */
  }
}

export function popFamilyEntryContext(familyId: string): string {
  if (!familyId) return ''
  try {
    const key = `${ENTRY_CTX_PREFIX}${familyId}`
    const val = sessionStorage.getItem(key) || ''
    sessionStorage.removeItem(key)
    return val
  } catch {
    return ''
  }
}

export function migrateLegacyHomeChat(): HomeSessionsStore | null {
  try {
    const raw = localStorage.getItem('genealogy-agent-home-chat')
    if (!raw) return null
    const data = JSON.parse(raw)
    const messages = Array.isArray(data.messages) ? data.messages : []
    if (!messages.length) return null
    const store = emptyStore()
    store.sessions[0] = {
      id: data.sessionId || store.sessions[0].id,
      title: deriveSessionTitle(messages),
      messages,
      updatedAt: data.updatedAt || Date.now(),
    }
    store.activeId = store.sessions[0].id
    saveHomeSessionsStore(store)
    localStorage.removeItem('genealogy-agent-home-chat')
    return store
  } catch {
    return null
  }
}
