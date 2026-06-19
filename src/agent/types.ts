/** 跨智能体共享的 UI / 会话类型（领域能力由各 Agent 插件扩展） */

export type AgentMessagePartType =
  | 'text'
  | 'create_family_preview'
  | 'person_card'
  | 'field_diff'
  | 'search_results'

export type AgentMessagePart = {
  type: AgentMessagePartType | string
  content?: string
  data?: Record<string, unknown>
}

export type AgentUiActionType =
  | 'switch_tab'
  | 'focus_person'
  | 'prefill_person'
  | 'set_anchor'
  | 'open_classic'
  | 'open_settings'
  | 'open_scan'
  | 'select_family'
  | 'scan'
  | 'create_family'
  | 'organize_regenerate'
  | 'organize_pipeline'

export type AgentUiAction = {
  type: AgentUiActionType | string
  tab?: string
  panel?: string
  person_id?: string
  name?: string
  draft?: Record<string, unknown>
  family_id?: string
  /** organize_regenerate: ocr_raw | relation_desc | custom */
  target?: string
  synced?: boolean
  full?: boolean
}

export type AgentConfirmation = {
  token: string
  tool: string
  title: string
  summary: string
  details?: Record<string, unknown>
}

export type AgentMessage = {
  role: string
  content: string
  meta?: {
    confirmation?: AgentConfirmation
    parts?: AgentMessagePart[]
  }
}

export type AgentDefinition = {
  id: string
  name: string
  shortName: string
  icon: string
  tagline: string
  placeholderHome: string
  placeholderWorkspace: string
  welcomeHome: string
  welcomeWorkspace: (ctx: { familyName?: string }) => string
}
