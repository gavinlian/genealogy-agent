<script setup lang="ts">
import { ref, computed, watch, nextTick } from 'vue'
import { api } from '../utils/api'
import { getAgent } from '../agent/registry'
import { applyGenealogyUiActions, extractSourceExcerpt } from '../agent/uiActions'
import {
  createHomeSession,
  getActiveHomeSession,
  loadHomeSessionsStore,
  migrateLegacyHomeChat,
  popFamilyEntryContext,
  saveHomeSessionsStore,
  stashFamilyEntryContext,
  switchHomeSession,
  upsertActiveHomeSession,
  type HomeChatSession,
} from '../agent/homeSessions'
import type { AgentMessage, AgentUiAction } from '../agent/types'
import AgentChatPane from './agent/AgentChatPane.vue'
import GenealogyReferenceView, { type ReferenceViewMode } from './view/GenealogyReferenceView.vue'
import GenealogyOrganizeWorkspace from './GenealogyOrganizeWorkspace.vue'
import SourceFusionPanel from './SourceFusionPanel.vue'
import FamilyMergePanel from './FamilyMergePanel.vue'
import AgentDiscoveryPanel from './AgentDiscoveryPanel.vue'
import SourceImageZoom from './SourceImageZoom.vue'
import { uploadImageUrl } from '../utils/uploadImageUrl'
import { useChatSidebar } from '../composables/useChatSidebar'
import { useToast } from '../composables/useToast'
import { useFamilyOrganize } from '../composables/useFamilyOrganize'

type FamilySummary = {
  id: string
  name?: string
  surname?: string
  description?: string
  person_count?: number
  source_text?: string
}

type TabId = 'tree' | 'source' | 'fusion' | 'organize' | 'discoveries'

const props = defineProps<{
  family: FamilySummary | null
  families: FamilySummary[]
  familiesLoading?: boolean
  sourceText?: string
  sourceVersionId?: string
  sourceVersionLabel?: string
  requestedTab?: TabId | null
  agentPendingCount?: number
  agentReport?: string
}>()

const discoveryOpen = defineModel<boolean>('discoveryOpen', { default: false })

const emit = defineEmits<{
  selectFamily: [id: string]
  leaveFamily: []
  switchClassic: [panel?: string]
  refresh: [pendingCount?: number]
  createFamily: [payload?: { name?: string; surname?: string; description?: string }]
  scan: []
  settings: []
  deleteFamily: [family: FamilySummary]
  openDiscoveries: []
  openAgentSettings: []
  applyDiscoveryPlan: [payload: { familyId: string; plan: unknown }]
}>()

const TABS: { id: TabId; label: string; icon: string }[] = [
  { id: 'tree', label: '族谱', icon: '🌳' },
  { id: 'discoveries', label: '发现', icon: '🔔' },
  { id: 'organize', label: '整理', icon: '✨' },
  { id: 'source', label: '原文', icon: '📜' },
  { id: 'fusion', label: '合并整理', icon: '🔗' },
]

const WORKSPACE_QUICK_PROMPTS = ['整理族谱', '补全缺失关系', '整理配偶关系']

const ORGANIZE_INTENT = /整理(?:族谱|全谱|主谱)?|理谱|补全(?:缺失)?关系|整理配偶|智能整理|从原文整理|生成关系预览/

const MUTATING_TOOLS = new Set([
  'propose_person_patch',
  'propose_sync_person_details',
  'propose_organize_plan',
  'propose_save_fusion',
  'propose_merge_family',
])

const organizeWorkspaceRef = ref<InstanceType<typeof GenealogyOrganizeWorkspace> | null>(null)
const fusionSeedText = ref('')
const sourceVersions = ref<any[]>([])
const activeSourcePreview = ref('')
const showDiscoveryDrawer = ref(false)
const dashboard = ref<{ owned: FamilySummary[]; followed: FamilySummary[]; discoverable: FamilySummary[] }>({
  owned: [],
  followed: [],
  discoverable: [],
})
const dashboardLoading = ref(false)

const { show: showToast } = useToast()

const familyIdRef = computed(() => props.family?.id || null)
const memberCountRef = computed(() => persons.value.length)
const organize = useFamilyOrganize(familyIdRef, memberCountRef, {
  onNotify: (msg, type) => showToast(msg, type || 'info'),
})
const {
  plan: organizePlan,
  diff: organizeDiff,
  applyMode: organizeApplyMode,
  cleanSlate: organizeCleanSlate,
  hasPendingPlan,
} = organize

const agentPendingCount = computed(() => props.agentPendingCount || 0)
const agentReport = computed(() => props.agentReport || '')

const displayOwnedFamilies = computed(() => {
  if (dashboard.value.owned.length) return dashboard.value.owned
  return props.families || []
})

function openDiscoveriesUi() {
  if (hasFamily.value) {
    switchTab('discoveries')
  } else {
    showDiscoveryDrawer.value = true
  }
}

watch(discoveryOpen, (open) => {
  if (!open) return
  openDiscoveriesUi()
  discoveryOpen.value = false
})

const organizeSourceText = computed(() => {
  const fromVersions = activeSourcePreview.value.trim()
  return fromVersions || (props.sourceText || sourceText.value || props.family?.source_text || '').trim()
})

const sourceV1Version = computed(() =>
  sourceVersions.value.find((v) => v.version_kind === 'ocr_raw') || null,
)

const sourceImageUrl = computed(() => uploadImageUrl(sourceV1Version.value?.image_path))

const sourceV1Text = computed(() => (sourceV1Version.value?.source_text || '').trim())

async function loadSourcePreview() {
  if (!props.family?.id) {
    sourceVersions.value = []
    activeSourcePreview.value = ''
    return
  }
  try {
    const res = await api('GET', `/families/${props.family.id}/source-versions`)
    sourceVersions.value = res.versions || []
    const activeId = res.active_version_id
    const active = sourceVersions.value.find((v) => v.id === activeId)
      || sourceVersions.value.find((v) => v.version_kind === 'custom')
      || sourceVersions.value.find((v) => v.version_kind === 'relation_desc')
      || sourceVersions.value.find((v) => v.version_kind === 'ocr_raw')
    activeSourcePreview.value = (active?.source_text || '').trim()
    if (activeSourcePreview.value) sourceText.value = activeSourcePreview.value
  } catch {
    /* ignore */
  }
}

function stashPersonDraft(personId: string, draft: Record<string, unknown>) {
  if (!props.family?.id || !Object.keys(draft).length) return
  sessionStorage.setItem(
    `genealogy_person_draft_${props.family.id}`,
    JSON.stringify({ personId, draft }),
  )
}

async function triggerOrganizeFromChat(message: string) {
  activeTab.value = 'organize'
  triggerAgentPulse('organize')
  await organize.loadState()
  await nextTick()
  await organizeWorkspaceRef.value?.runFromAgent(message)
}

function applyToolCallSideEffects(toolCalls: any[]) {
  for (const tc of toolCalls || []) {
    if (tc.tool === 'fuse_source_versions' && tc.result?.stepped_text) {
      fusionSeedText.value = tc.result.stepped_text
      activeTab.value = 'fusion'
      triggerAgentPulse('fusion')
    }
    if (tc.tool === 'propose_organize_plan') {
      activeTab.value = 'organize'
      triggerAgentPulse('organize')
      void organize.loadState().then(async () => {
        await nextTick()
        organizeWorkspaceRef.value?.focusStep('preview')
      })
    }
  }
}

function syncStateFromAgentResponse(res: {
  state?: { active_tab?: string; anchor_person_id?: string | null; selected_person_id?: string | null }
  tool_calls?: any[]
}) {
  if (res.state?.anchor_person_id !== undefined) {
    anchorPersonId.value = res.state.anchor_person_id
  }
  if (res.state?.selected_person_id) {
    selectedPersonId.value = res.state.selected_person_id
  }
  const tab = res.state?.active_tab
  if (tab === 'organize' || tab === 'source' || tab === 'fusion' || tab === 'tree') {
    activeTab.value = tab as TabId
  }
  applyToolCallSideEffects(res.tool_calls)
}

const agent = getAgent()

const activeTab = ref<TabId>('tree')
const genealogyViewMode = ref<ReferenceViewMode>('page')
const persons = ref<any[]>([])
const relations = ref<any[]>([])
const selectedPersonId = ref<string | null>(null)
const anchorPersonId = ref<string | null>(null)
const messages = ref<AgentMessage[]>([])
const chatLoading = ref(false)
const {
  isCompact,
  chatOpen: chatExpanded,
  openChat: openChatSidebar,
  toggleChat: toggleChatExpanded,
} = useChatSidebar()
const confirmationLoading = ref<string | null>(null)
const sessionId = ref<string | null>(null)
const loading = ref(false)
const sourceText = ref('')
const agentLinkHint = ref('')
const pulseTab = ref<TabId | null>(null)

const chatPlaceholder = computed(() =>
  hasFamily.value ? agent.placeholderWorkspace : agent.placeholderHome,
)

const chatPaneLayout = computed(() => (isCompact.value ? 'drawer' : 'sidebar'))

const activeTabMeta = computed(() => TABS.find((t) => t.id === activeTab.value) || TABS[0])

const sourceExcerpt = computed(() => {
  const name = selectedPerson.value?.name
  if (!name) return ''
  return extractSourceExcerpt(organizeSourceText.value || sourceText.value, name)
})

const homeSessionsStore = ref(loadHomeSessionsStore())
const homeSessionsList = computed<HomeChatSession[]>(() =>
  hasFamily.value ? [] : homeSessionsStore.value.sessions,
)

const chatContextLabel = computed(() =>
  hasFamily.value ? (props.family?.name || '族谱') : '全局',
)

const sessionTitle = computed(() => {
  if (hasFamily.value) {
    const first = messages.value.find((m) => m.role === 'user' && m.content?.trim())
    if (first) {
      const t = first.content.trim()
      return t.length > 18 ? `${t.slice(0, 18)}…` : t
    }
    return props.family?.name ? `${props.family.name} · 族谱对话` : '族谱对话'
  }
  const active = getActiveHomeSession(homeSessionsStore.value)
  return active.title || '默认会话'
})

const sessionLabel = computed(() => {
  if (hasFamily.value) {
    if (!sessionId.value) return '默认'
    return sessionId.value.slice(0, 6)
  }
  return homeSessionsStore.value.activeId.slice(0, 6)
})

const messageCount = computed(() => messages.value.length)
const hasFamily = computed(() => Boolean(props.family?.id))

const selectedPerson = computed(() =>
  persons.value.find((p) => p.id === selectedPersonId.value) || null,
)

const visibleMessages = computed(() => messages.value)

function triggerAgentPulse(tab?: TabId) {
  if (!tab) return
  pulseTab.value = tab
  window.setTimeout(() => { pulseTab.value = null }, 1800)
}

function setAgentLinkHint(hints: string[]) {
  if (!hints.length) return
  agentLinkHint.value = hints[hints.length - 1]
  window.setTimeout(() => {
    if (agentLinkHint.value === hints[hints.length - 1]) agentLinkHint.value = ''
  }, 5000)
}

async function newChatSession() {
  if (hasFamily.value && props.family?.id) {
    const res = await api('POST', `/families/${props.family.id}/agent/session/reset`, { mode: 'new' })
    if (res.success) {
      messages.value = res.messages || []
      sessionId.value = res.session_id || null
      chatExpanded.value = true
    }
    return
  }
  homeSessionsStore.value = createHomeSession(homeSessionsStore.value)
  sessionId.value = homeSessionsStore.value.activeId
  messages.value = []
  ensureWelcome()
  saveHomeSessionsStore(homeSessionsStore.value)
  chatExpanded.value = true
}

async function clearChatHistory() {
  if (!confirm('确定清空当前对话历史？')) return
  if (hasFamily.value && props.family?.id) {
    const res = await api('POST', `/families/${props.family.id}/agent/session/reset`, { mode: 'clear' })
    if (res.success) {
      messages.value = []
      sessionId.value = res.session_id || null
    }
    return
  }
  messages.value = []
  homeSessionsStore.value = upsertActiveHomeSession(homeSessionsStore.value, messages.value)
  saveHomeSessionsStore(homeSessionsStore.value)
}

function switchHomeChatSession(id: string) {
  homeSessionsStore.value = upsertActiveHomeSession(homeSessionsStore.value, messages.value)
  const next = switchHomeSession(homeSessionsStore.value, id)
  if (!next) return
  homeSessionsStore.value = next
  sessionId.value = next.activeId
  messages.value = getActiveHomeSession(next).messages
  ensureWelcome()
  saveHomeSessionsStore(homeSessionsStore.value)
  chatExpanded.value = true
}

function persistHomeChat() {
  if (hasFamily.value) return
  homeSessionsStore.value = upsertActiveHomeSession(homeSessionsStore.value, messages.value)
  saveHomeSessionsStore(homeSessionsStore.value)
}

function loadHomeChat() {
  migrateLegacyHomeChat()
  homeSessionsStore.value = loadHomeSessionsStore()
  sessionId.value = homeSessionsStore.value.activeId
  messages.value = getActiveHomeSession(homeSessionsStore.value).messages
  ensureWelcome()
  persistHomeChat()
}

function appendFamilyEntryBridge(entryCtx: string) {
  const snippet = entryCtx.length > 48 ? `${entryCtx.slice(0, 48)}…` : entryCtx
  const bridge = `已从首页进入「${props.family?.name || '族谱'}」。您刚才说：「${snippet}」\n\n在这里可以继续操作，对话与族谱数据已衔接。`
  if (messages.value.some((m) => m.content?.includes(snippet.slice(0, 12)))) return
  messages.value = [...messages.value, { role: 'assistant', content: bridge }]
}

function familyInitial(f: FamilySummary) {
  const s = (f.surname || f.name || '族').trim()
  return s.charAt(0)
}

function ensureWelcome() {
  if (messages.value.length) return
  if (hasFamily.value) {
    messages.value = [{
      role: 'assistant',
      content: agent.welcomeWorkspace({ familyName: props.family?.name }),
    }]
  } else {
    messages.value = [{
      role: 'assistant',
      content: agent.welcomeHome,
    }]
  }
}

async function loadFamilyData() {
  if (!props.family?.id) {
    persons.value = []
    relations.value = []
    sourceText.value = ''
    selectedPersonId.value = null
    anchorPersonId.value = null
    loadHomeChat()
    return
  }
  loading.value = true
  try {
    const [pRes, relRes, stateRes] = await Promise.all([
      api('GET', `/families/${props.family.id}/persons`),
      api('GET', `/families/${props.family.id}/relations`),
      api('GET', `/families/${props.family.id}/agent/state`),
    ])
    persons.value = Array.isArray(pRes) ? pRes : []
    relations.value = Array.isArray(relRes) ? relRes : []
    sourceText.value = props.family.source_text || ''
    if (stateRes.success) {
      const tab = stateRes.active_tab as string
      activeTab.value =
        tab === 'organize' ? 'organize' :
        tab === 'source' ? 'source' :
        tab === 'fusion' ? 'fusion' :
        'tree'
      anchorPersonId.value = stateRes.anchor_person_id || null
      selectedPersonId.value = stateRes.selected_person_id || null
      sessionId.value = stateRes.session_id || null
      messages.value = stateRes.messages || []
    }
    ensureWelcome()
    const entryCtx = popFamilyEntryContext(props.family.id)
    if (entryCtx) appendFamilyEntryBridge(entryCtx)
    await organize.loadState(props.family.id)
    await loadSourcePreview()
  } finally {
    loading.value = false
  }
}

function switchTab(tab: TabId) {
  if (!hasFamily.value) return
  activeTab.value = tab
  if (tab === 'organize') {
    void organize.loadState()
    if (organize.hasPendingPlan()) void organize.refreshDiff()
  }
  if (tab === 'source') void loadSourcePreview()
  persistUiState()
}

function selectPersonFromTree(id: string) {
  selectedPersonId.value = id
  persistUiState()
}

async function persistUiState() {
  if (!props.family?.id) return
  await api('PUT', `/families/${props.family.id}/agent/state`, {
    active_tab: activeTab.value,
    anchor_person_id: anchorPersonId.value,
    selected_person_id: selectedPersonId.value,
  })
}

function applyUiActions(actions: AgentUiAction[]) {
  const hints = applyGenealogyUiActions(actions, {
    switchTab: (tab) => {
      if (tab === 'organize') {
        activeTab.value = 'organize'
        triggerAgentPulse('organize')
        void organize.loadState()
        return
      }
      if (tab === 'diff') {
        emit('switchClassic', 'diff')
        return
      }
      if (tab === 'person') {
        selectedPersonId.value = selectedPersonId.value || anchorPersonId.value
        activeTab.value = 'tree'
        triggerAgentPulse('tree')
        return
      }
      if (tab === 'source' || tab === 'tree' || tab === 'fusion') {
        activeTab.value = tab as TabId
        triggerAgentPulse(tab as TabId)
      }
    },
    focusPerson: (personId, name) => {
      selectedPersonId.value = personId
      activeTab.value = 'tree'
      triggerAgentPulse('tree')
      if (name) agentLinkHint.value = `已选中【${name}】· 编辑请用经典模式`
    },
    prefillPerson: (personId, draft, name) => {
      selectedPersonId.value = personId
      stashPersonDraft(personId, draft || {})
      agentLinkHint.value = name
        ? `已提取【${name}】资料 · 正在打开成员编辑`
        : '对话已提取资料 · 正在打开成员编辑'
      emit('switchClassic', 'person')
    },
    setAnchor: (personId, name) => {
      anchorPersonId.value = personId
      void persistUiState()
      if (name) agentLinkHint.value = `我在谱中：${name}`
    },
    openClassic: (panel) => {
      if (panel === 'organize') {
        activeTab.value = 'organize'
        triggerAgentPulse('organize')
        void organize.loadState()
        return
      }
      if (panel === 'source') {
        activeTab.value = 'source'
        void loadSourcePreview()
        triggerAgentPulse('source')
        return
      }
      emit('switchClassic', panel)
    },
    openSettings: () => emit('settings'),
    openScan: () => emit('scan'),
    organizeRegenerate: (target, synced) => handleOrganizeRegenerate(target, synced),
  })
  setAgentLinkHint(hints)
}

async function handleOrganizeRegenerate(target: string, synced?: boolean) {
  activeTab.value = 'organize'
  triggerAgentPulse('organize')
  await organize.loadState()
  await nextTick()
  if (synced) {
    await organizeWorkspaceRef.value?.reloadFromServer?.()
    emit('refresh')
    return
  }
  if (target === 'ocr_raw') {
    await organizeWorkspaceRef.value?.regenerateOcr?.()
  } else {
    await organizeWorkspaceRef.value?.regenerateRelation?.()
  }
  emit('refresh')
}

function applyHomeActions(actions: any[]) {
  for (const a of actions || []) {
    if (a.type === 'select_family' && a.family_id) {
      const lastUser = [...messages.value].reverse().find((m) => m.role === 'user')
      if (lastUser?.content) stashFamilyEntryContext(a.family_id, lastUser.content)
      emit('refresh')
      emit('selectFamily', a.family_id)
    }
    if (a.type === 'scan') emit('scan')
    if (a.type === 'create_family') {
      const payload = {
        name: a.name,
        surname: a.surname,
        description: a.description,
      }
      if (payload.name || payload.surname || payload.description) {
        emit('createFamily', payload)
      } else {
        emit('createFamily')
      }
    }
  }
}

async function onOrganizeApplied(stats?: Record<string, number>) {
  await organize.onApplied(stats)
  await loadFamilyData()
  emit('refresh')
}

async function onOrganizePlanEdited() {
  await organize.refreshDiff()
}

watch(
  () => props.requestedTab,
  (tab) => {
    if (tab === 'organize' && hasFamily.value) {
      activeTab.value = 'organize'
      void organize.loadState()
      if (organize.hasPendingPlan()) void organize.refreshDiff()
    }
  },
  { immediate: true },
)

async function onOrganizeCleared() {
  await organize.onCleared()
  await loadFamilyData()
  emit('refresh')
}

async function respondConfirmation(token: string, approved: boolean) {
  if (!props.family?.id || confirmationLoading.value) return
  confirmationLoading.value = token
  try {
    const res = await api('POST', `/families/${props.family.id}/agent/confirm`, {
      token,
      approved,
    })
    if (res.state) {
      messages.value = res.state.messages || messages.value
    } else {
      const stateRes = await api('GET', `/families/${props.family.id}/agent/state`)
      if (stateRes.success) {
        messages.value = stateRes.messages || messages.value
      } else if (res.message) {
        messages.value.push({ role: 'assistant', content: res.message })
      }
    }
    if (approved) {
      await loadFamilyData()
      emit('refresh')
    }
  } finally {
    confirmationLoading.value = null
  }
}

async function sendChat(text: string) {
  const msg = text.trim()
  if (!msg || chatLoading.value) return
  if (isCompact.value) openChatSidebar()
  chatLoading.value = true
  messages.value = [...messages.value, { role: 'user', content: msg }]
  try {
    if (!props.family?.id) {
      const res = await api('POST', '/agent/home/chat', {
        message: msg,
        families: props.families.map((f) => ({
          id: f.id,
          name: f.name,
          person_count: f.person_count,
        })),
        history: messages.value.slice(-14),
      })
      if (!res.success) {
        messages.value.push({ role: 'assistant', content: res.message || res.detail || '发送失败' })
        return
      }
      messages.value.push({
        role: 'assistant',
        content: res.reply || '',
        meta: { parts: res.message_parts || [] },
      })
      applyHomeActions(res.home_actions)
      persistHomeChat()
      return
    }
    const res = await api('POST', `/families/${props.family.id}/agent/chat`, {
      message: msg,
      active_tab: activeTab.value,
      anchor_person_id: anchorPersonId.value,
      selected_person_id: selectedPersonId.value,
    })
    if (!res.success) {
      messages.value.push({ role: 'assistant', content: res.message || res.detail || '发送失败' })
      return
    }
    applyUiActions(res.ui_actions || [])
    syncStateFromAgentResponse(res)
    if (res.state?.messages) {
      messages.value = res.state.messages
    } else if (res.reply) {
      messages.value.push({ role: 'assistant', content: res.reply })
    }

    const hasRegenTool = (res.tool_calls || []).some(
      (tc: { tool?: string }) => tc.tool === 'regenerate_source_version',
    )
    if (hasRegenTool) {
      await loadSourcePreview()
      emit('refresh')
    }

    const hasOrganizeTool = (res.tool_calls || []).some(
      (tc: { tool?: string }) => tc.tool === 'propose_organize_plan',
    )
    const wantsOrganize =
      ORGANIZE_INTENT.test(msg)
      || (res.ui_actions || []).some((a: AgentUiAction) => a.type === 'switch_tab' && a.tab === 'organize')
    if (wantsOrganize && !hasOrganizeTool) {
      await triggerOrganizeFromChat(msg)
    }

    await persistUiState()
    const mutated =
      Boolean(res.confirmation)
      || (res.tool_calls || []).some((tc: { tool?: string }) => tc.tool && MUTATING_TOOLS.has(tc.tool))
    if (mutated) {
      await loadFamilyData()
      emit('refresh')
    }
  } finally {
    chatLoading.value = false
  }
}

async function onAnchorChange() {
  await persistUiState()
}

function onFamilyPickerChange(e: Event) {
  const id = (e.target as HTMLSelectElement).value
  if (id) emit('selectFamily', id)
  else emit('leaveFamily')
}

async function loadDashboard() {
  dashboardLoading.value = true
  try {
    const res = await api('GET', '/families/dashboard')
    if (res.success) {
      dashboard.value = {
        owned: res.owned || [],
        followed: res.followed || [],
        discoverable: res.discoverable || [],
      }
    }
  } finally {
    dashboardLoading.value = false
  }
}

async function followFamilyId(id: string) {
  const res = await api('POST', `/families/${id}/follow`)
  if (res.success) {
    showToast('已关注族谱', 'success')
    await loadDashboard()
    emit('refresh')
  } else {
    showToast(res.message || res.detail || '关注失败', 'error')
  }
}

async function unfollowFamilyId(id: string) {
  const res = await api('DELETE', `/families/${id}/follow`)
  if (res.success) {
    showToast('已取消关注', 'success')
    await loadDashboard()
    emit('refresh')
  } else {
    showToast(res.message || res.detail || '操作失败', 'error')
  }
}

function onDiscoveryApply(payload: { familyId: string; plan: unknown }) {
  emit('applyDiscoveryPlan', payload)
  switchTab('organize')
}

async function applyDiscoveryPlanLocal(payload: { familyId: string; plan: unknown }) {
  const plan = payload.plan as import('../types/organize').OrganizePlan
  organize.onLoadPlan({ plan, diff: null })
  await organize.refreshDiff()
  switchTab('organize')
}

watch(() => props.family?.id, (id) => {
  loadFamilyData()
  if (!id) void loadDashboard()
}, { immediate: true })
</script>

<template>
  <section
    class="agent-chat-shell section main--workspace"
    :class="{
      'agent-chat-shell--compact': isCompact,
      'agent-chat-shell--chat-open': isCompact && chatExpanded,
    }"
  >
    <header class="agent-top-bar">
      <div class="agent-top-bar-start">
        <template v-if="hasFamily">
          <button type="button" class="btn-back btn-back--inline" @click="emit('leaveFamily')">←</button>
          <h2 class="agent-top-bar-title">{{ family!.name }}</h2>
          <span v-if="family!.surname" class="surname-tag">{{ family!.surname }}氏</span>
        </template>
        <template v-else>
          <span class="logo-mark logo-mark--sm">{{ agent.icon }}</span>
          <div class="agent-top-bar-brand-block">
            <strong class="agent-top-bar-brand">族见</strong>
            <span class="agent-top-bar-slogan">见家族，见自己</span>
          </div>
          <span class="agent-top-bar-resee">ReSee</span>
        </template>
      </div>
      <div class="agent-top-bar-end">
        <label v-if="hasFamily" class="agent-anchor-label">
          我在谱中
          <select v-model="anchorPersonId" class="input input-inline" @change="onAnchorChange">
            <option :value="null">未设置</option>
            <option v-for="p in persons" :key="p.id" :value="p.id">{{ p.name }}</option>
          </select>
        </label>
        <select
          v-if="hasFamily && families.length > 1"
          class="input input-inline agent-family-picker"
          :value="family!.id"
          @change="onFamilyPickerChange"
        >
          <option v-for="f in families" :key="f.id" :value="f.id">{{ f.name }}</option>
        </select>
        <button
          v-if="hasFamily"
          type="button"
          class="btn-secondary btn-sm agent-classic-btn"
          @click="emit('switchClassic')"
        >
          经典编辑
        </button>
        <button
          type="button"
          class="btn-secondary btn-sm"
          title="智能体发现"
          @click="openDiscoveriesUi()"
        >
          🔔<span v-if="agentPendingCount" class="toolbar-badge">{{ agentPendingCount > 9 ? '9+' : agentPendingCount }}</span>
        </button>
        <button type="button" class="btn-ghost btn-sm" title="智能体设置" @click="emit('openAgentSettings')">智能体</button>
        <button
          v-if="hasFamily"
          type="button"
          class="btn-ghost btn-sm btn-danger-text"
          title="删除当前族谱"
          @click="emit('deleteFamily', family!)"
        >
          删除
        </button>
        <button
          v-if="isCompact"
          type="button"
          class="btn-secondary btn-sm agent-topbar-chat-btn"
          @click="toggleChatExpanded"
        >
          {{ chatExpanded ? '收起对话' : '展开对话' }}
        </button>
        <button type="button" class="btn-icon" title="设置" @click="emit('settings')">⚙</button>
      </div>
    </header>

    <div v-if="agentReport && !hasFamily" class="agent-report-banner">
      <span>{{ agentReport }}</span>
      <button type="button" class="btn-xs btn-primary" @click="openDiscoveriesUi">查看发现</button>
    </div>

    <div class="agent-shell-body">
      <div class="agent-shell-main">
        <div class="agent-page-area">
          <div v-if="!hasFamily" class="agent-page agent-page--home">
            <div class="agent-home-toolbar">
              <h2 class="page-title">我的族谱</h2>
              <div class="agent-home-toolbar-actions">
                <button type="button" class="btn-secondary btn-sm" @click="openDiscoveriesUi">
                  发现<span v-if="agentPendingCount" class="toolbar-badge">{{ agentPendingCount }}</span>
                </button>
                <button type="button" class="btn-primary btn-sm" @click="emit('createFamily')">+ 新建</button>
              </div>
            </div>
            <div v-if="familiesLoading || dashboardLoading" class="loading">加载中…</div>
            <template v-else>
              <section v-if="displayOwnedFamilies.length" class="agent-home-section">
                <h3 class="agent-home-section-title">本人族谱</h3>
                <div class="family-grid family-grid--compact">
                  <article
                    v-for="f in displayOwnedFamilies"
                    :key="f.id"
                    class="family-card family-card--selectable"
                    @click="emit('selectFamily', f.id)"
                  >
                    <div class="family-avatar">{{ familyInitial(f) }}</div>
                    <div class="family-info">
                      <h3>{{ f.name }}</h3>
                      <span class="count">{{ f.person_count || 0 }} 位成员</span>
                    </div>
                    <button
                      type="button"
                      class="family-card-delete btn-xs btn-danger-text"
                      title="删除族谱"
                      @click.stop="emit('deleteFamily', f)"
                    >
                      删除
                    </button>
                  </article>
                </div>
              </section>
              <section v-if="dashboard.followed.length" class="agent-home-section">
                <h3 class="agent-home-section-title">关注族谱</h3>
                <div class="family-grid family-grid--compact">
                  <article
                    v-for="f in dashboard.followed"
                    :key="'f-' + f.id"
                    class="family-card family-card--selectable family-card--followed"
                    @click="emit('selectFamily', f.id)"
                  >
                    <div class="family-avatar">{{ familyInitial(f) }}</div>
                    <div class="family-info">
                      <h3>{{ f.name }}</h3>
                      <span class="count">{{ f.person_count || 0 }} 位成员 · 只读关注</span>
                    </div>
                    <button type="button" class="btn-xs" @click.stop="unfollowFamilyId(f.id)">取消关注</button>
                  </article>
                </div>
              </section>
              <section v-if="dashboard.discoverable.length" class="agent-home-section">
                <h3 class="agent-home-section-title">可关注族谱</h3>
                <div class="family-grid family-grid--compact">
                  <article
                    v-for="f in dashboard.discoverable"
                    :key="'d-' + f.id"
                    class="family-card family-card--selectable"
                  >
                    <div class="family-avatar">{{ familyInitial(f) }}</div>
                    <div class="family-info">
                      <h3>{{ f.name }}</h3>
                      <span class="count">{{ f.person_count || 0 }} 位成员</span>
                    </div>
                    <button type="button" class="btn-xs btn-primary" @click.stop="followFamilyId(f.id)">关注</button>
                  </article>
                </div>
              </section>
              <div v-if="!displayOwnedFamilies.length && !dashboard.followed.length" class="empty-state compact">
                <p>还没有族谱。在对话里说「扫描建谱」，或点新建。</p>
              </div>
            </template>
          </div>

          <template v-else>
            <div v-if="loading" class="agent-chat-loading">加载族谱…</div>
            <template v-else>
              <header
                v-if="activeTab === 'tree'"
                class="agent-workspace-header agent-workspace-header--tree"
              >
                <div class="agent-workspace-header-main">
                  <span class="agent-workspace-tab-icon">{{ activeTabMeta.icon }}</span>
                  <h3 class="agent-workspace-title">{{ activeTabMeta.label }}</h3>
                  <span v-if="selectedPerson" class="agent-workspace-context">· {{ selectedPerson.name }}</span>
                </div>
                <div v-if="activeTab === 'tree'" class="ocr-view-mode-group agent-view-mode-group">
                  <button
                    type="button"
                    class="ocr-view-mode-btn"
                    :class="{ active: genealogyViewMode === 'page' }"
                    @click="genealogyViewMode = 'page'"
                  >
                    谱页
                  </button>
                  <button
                    type="button"
                    class="ocr-view-mode-btn"
                    :class="{ active: genealogyViewMode === 'card' }"
                    @click="genealogyViewMode = 'card'"
                  >
                    卡片
                  </button>
                  <button
                    type="button"
                    class="ocr-view-mode-btn"
                    :class="{ active: genealogyViewMode === 'graph' }"
                    @click="genealogyViewMode = 'graph'"
                  >
                    关系图
                  </button>
                </div>
                <p v-if="agentLinkHint" class="agent-workspace-hint">{{ agentLinkHint }}</p>
              </header>

              <div v-show="activeTab === 'tree'" class="agent-page agent-page--tree">
                <GenealogyReferenceView
                  v-if="persons.length"
                  :mode="genealogyViewMode"
                  :persons="persons"
                  :relations="relations"
                  :structured-text="sourceText"
                  :title="family?.name || '族谱'"
                  :selected-person-id="selectedPersonId"
                  fill
                  @select="selectPersonFromTree"
                />
                <div v-else class="empty-state compact agent-tree-empty">
                  <p>暂无成员。在对话里说「扫描建谱」，或进入经典编辑添加。</p>
                  <button type="button" class="btn-secondary btn-sm" @click="emit('switchClassic')">经典编辑</button>
                </div>
                <div v-if="selectedPerson" class="agent-selection-bar">
                  <span>已选 <strong>{{ selectedPerson.name }}</strong> · 相关关系已高亮</span>
                  <button type="button" class="btn-secondary btn-sm" @click="emit('switchClassic')">编辑成员</button>
                </div>
              </div>

              <div v-show="activeTab === 'source'" class="agent-page agent-page--source">
                <div class="agent-source-toolbar">
                  <span class="hint">
                    {{ sourceImageUrl ? '扫描原图 ↔ 版本一 OCR 原文' : '当前活跃原文版本（上传扫描图请用「整理」→ ① 扫描 OCR）' }}
                  </span>
                  <button type="button" class="btn-xs btn-secondary" @click="emit('switchClassic', 'source')">
                    经典编辑 · 对照校对
                  </button>
                </div>
                <div v-if="sourceExcerpt" class="agent-source-excerpt">
                  <strong v-if="selectedPerson">节选 · {{ selectedPerson.name }}</strong>
                  <p>{{ sourceExcerpt }}</p>
                </div>
                <div v-if="sourceImageUrl" class="agent-source-pair">
                  <div class="agent-source-pair-image">
                    <SourceImageZoom :src="sourceImageUrl" alt="族谱扫描原图" />
                  </div>
                  <div class="agent-source-pair-text">
                    <p class="hint agent-source-pair-label">版本一 · OCR 原文</p>
                    <textarea
                      :value="sourceV1Text || organizeSourceText"
                      class="input agent-source-text agent-source-text--pair"
                      readonly
                      rows="12"
                    />
                  </div>
                </div>
                <textarea
                  v-else
                  :value="organizeSourceText"
                  class="input agent-source-text"
                  readonly
                  rows="14"
                />
              </div>

              <div v-show="activeTab === 'organize'" class="agent-page agent-page--organize">
                <GenealogyOrganizeWorkspace
                  ref="organizeWorkspaceRef"
                  v-if="family?.id"
                  :family-id="family.id"
                  :family-name="family.name"
                  :member-count="persons.length"
                  :selected-person-id="selectedPersonId || undefined"
                  :selected-person-name="selectedPerson?.name || ''"
                  :plan="organizePlan"
                  :diff="organizeDiff"
                  :apply-mode="organizeApplyMode"
                  :clean-slate="organizeCleanSlate"
                  @update:apply-mode="organizeApplyMode = $event"
                  @update:clean-slate="organizeCleanSlate = $event"
                  @update:plan="organize.onPlanPatch($event)"
                  @load-plan="organize.onLoadPlan($event)"
                  @plan-edited="onOrganizePlanEdited"
                  @applied="onOrganizeApplied"
                  @cleared="onOrganizeCleared"
                  @dismiss="organize.dismissPlan()"
                  @notify="(msg, type) => showToast(msg, type || 'info')"
                  @refresh="loadFamilyData(); emit('refresh')"
                  @select-person="selectPerson"
                />
              </div>

              <div v-show="activeTab === 'discoveries'" class="agent-page agent-page--discoveries">
                <AgentDiscoveryPanel
                  embedded
                  :family-id="family?.id"
                  @toast="(msg, kind) => showToast(msg, kind || 'info')"
                  @apply-plan="applyDiscoveryPlanLocal"
                  @refresh="(n) => emit('refresh', n)"
                />
              </div>

              <div v-show="activeTab === 'fusion'" class="agent-page agent-page--fusion">
                <FamilyMergePanel
                  v-if="family?.id"
                  :family-id="family.id"
                  :family-name="family.name"
                  :initial-fusion-text="fusionSeedText"
                  @toast="(msg, kind) => showToast(msg, kind || 'info')"
                  @saved="loadFamilyData(); emit('refresh')"
                  @open-organize="switchTab('organize')"
                />
              </div>
            </template>
          </template>

          <div v-if="showDiscoveryDrawer && !hasFamily" class="modal" @click.self="showDiscoveryDrawer = false">
            <div class="modal-content modal-lg agent-discovery-modal" @click.stop>
              <div class="ai-settings-header">
                <h3>智能体发现</h3>
                <button type="button" class="btn-close" @click="showDiscoveryDrawer = false">×</button>
              </div>
              <AgentDiscoveryPanel
                embedded
                :show-header="false"
                @toast="(msg, kind) => showToast(msg, kind || 'info')"
                @refresh="(n?: number) => emit('refresh', n)"
              />
            </div>
          </div>
        </div>

        <nav v-if="hasFamily" class="agent-tab-bar agent-tab-bar--minimal">
          <button
            v-for="t in TABS"
            :key="t.id"
            type="button"
            class="agent-tab"
            :class="{ active: activeTab === t.id, 'agent-tab--pulse': pulseTab === t.id }"
            @click="switchTab(t.id)"
          >
            <span class="agent-tab-icon">{{ t.icon }}</span>
            <span class="agent-tab-label">{{ t.label }}</span>
            <span
              v-if="t.id === 'organize' && hasPendingPlan()"
              class="agent-tab-badge"
            >1</span>
            <span
              v-if="t.id === 'discoveries' && agentPendingCount"
              class="agent-tab-badge"
            >{{ agentPendingCount > 9 ? '9+' : agentPendingCount }}</span>
          </button>
        </nav>
      </div>

      <aside
        class="agent-chat-sidebar"
        :class="{ 'agent-chat-sidebar--expanded': chatExpanded }"
      >
        <AgentChatPane
          :agent-name="agent.name"
          :agent-icon="agent.icon"
          :agent-tagline="agent.tagline"
          :messages="messages"
          :visible-messages="visibleMessages"
          :chat-loading="chatLoading"
          :chat-expanded="isCompact ? chatExpanded : true"
          :session-label="sessionLabel"
          :session-title="sessionTitle"
          :chat-context-label="chatContextLabel"
          :home-sessions="homeSessionsList"
          :message-count="messageCount"
          :confirmation-loading="confirmationLoading"
          :placeholder="chatPlaceholder"
          :layout="chatPaneLayout"
          :show-collapse="false"
          :show-mobile-handle="isCompact"
          :show-scan="true"
          :quick-prompts="hasFamily ? WORKSPACE_QUICK_PROMPTS : undefined"
          @send="sendChat"
          @toggle-expanded="toggleChatExpanded"
          @new-session="newChatSession"
          @clear-history="clearChatHistory"
          @switch-session="switchHomeChatSession"
          @back-to-home="emit('leaveFamily')"
          @confirm="respondConfirmation"
          @scan="emit('scan')"
        />
      </aside>
    </div>
  </section>
</template>
