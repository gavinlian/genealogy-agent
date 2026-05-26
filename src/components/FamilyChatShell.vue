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
import { useChatSidebar } from '../composables/useChatSidebar'

type FamilySummary = {
  id: string
  name?: string
  surname?: string
  description?: string
  person_count?: number
  source_text?: string
}

const props = defineProps<{
  family: FamilySummary | null
  families: FamilySummary[]
  familiesLoading?: boolean
}>()

const emit = defineEmits<{
  selectFamily: [id: string]
  leaveFamily: []
  switchClassic: [panel?: string]
  refresh: []
  createFamily: [payload?: { name?: string; surname?: string; description?: string }]
  scan: []
  settings: []
  deleteFamily: [family: FamilySummary]
}>()

type TabId = 'tree' | 'source'

const TABS: { id: TabId; label: string; icon: string }[] = [
  { id: 'tree', label: '族谱', icon: '🌳' },
  { id: 'source', label: '原文', icon: '📜' },
]

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
  return extractSourceExcerpt(sourceText.value, name)
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
      activeTab.value = tab === 'source' ? 'source' : 'tree'
      anchorPersonId.value = stateRes.anchor_person_id || null
      selectedPersonId.value = stateRes.selected_person_id || null
      sessionId.value = stateRes.session_id || null
      messages.value = stateRes.messages || []
    }
    ensureWelcome()
    const entryCtx = popFamilyEntryContext(props.family.id)
    if (entryCtx) appendFamilyEntryBridge(entryCtx)
  } finally {
    loading.value = false
  }
}

function switchTab(tab: TabId) {
  if (!hasFamily.value) return
  activeTab.value = tab
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
      if (tab === 'organize' || tab === 'diff' || tab === 'person') {
        emit('switchClassic', tab === 'person' ? undefined : tab)
        return
      }
      if (tab === 'source' || tab === 'tree') {
        activeTab.value = tab
        triggerAgentPulse(tab)
      }
    },
    focusPerson: (personId, name) => {
      selectedPersonId.value = personId
      activeTab.value = 'tree'
      triggerAgentPulse('tree')
      if (name) agentLinkHint.value = `已选中【${name}】· 编辑请用经典模式`
    },
    prefillPerson: (personId, _draft) => {
      selectedPersonId.value = personId
      activeTab.value = 'tree'
      agentLinkHint.value = '对话已提取资料 · 请在经典模式中编辑成员'
      emit('switchClassic')
    },
    setAnchor: (personId, name) => {
      anchorPersonId.value = personId
      void persistUiState()
      if (name) agentLinkHint.value = `我在谱中：${name}`
    },
    openClassic: (panel) => emit('switchClassic', panel),
    openSettings: () => emit('settings'),
    openScan: () => emit('scan'),
  })
  setAgentLinkHint(hints)
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
    if (res.state) {
      messages.value = res.state.messages || messages.value
    } else {
      messages.value.push({ role: 'assistant', content: res.reply || '' })
    }
    await persistUiState()
    await loadFamilyData()
    emit('refresh')
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

watch(() => props.family?.id, () => loadFamilyData(), { immediate: true })
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

    <div class="agent-shell-body">
      <div class="agent-shell-main">
        <div class="agent-page-area">
          <div v-if="!hasFamily" class="agent-page agent-page--home">
            <div class="agent-home-toolbar">
              <h2 class="page-title">我的族谱</h2>
              <button type="button" class="btn-primary btn-sm" @click="emit('createFamily')">+ 新建</button>
            </div>
            <div v-if="familiesLoading" class="loading">加载中…</div>
            <div v-else-if="!families.length" class="empty-state compact">
              <p>还没有族谱。在对话里说「扫描建谱」，或点新建。</p>
            </div>
            <div v-else class="family-grid family-grid--compact">
              <article
                v-for="f in families"
                :key="f.id"
                class="family-card family-card--selectable"
                @click="emit('selectFamily', f.id)"
              >
                <div class="family-avatar">{{ familyInitial(f) }}</div>
                <div class="family-info">
                  <h3>{{ f.name }}</h3>
                  <span class="count">{{ f.person_count || 0 }} 位成员</span>
                </div>
              </article>
            </div>
          </div>

          <template v-else>
            <div v-if="loading" class="agent-chat-loading">加载族谱…</div>
            <template v-else>
              <header class="agent-workspace-header agent-workspace-header--tree">
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
                  <span>已选 <strong>{{ selectedPerson.name }}</strong></span>
                  <button type="button" class="btn-secondary btn-sm" @click="emit('switchClassic')">编辑成员</button>
                </div>
              </div>

              <div v-show="activeTab === 'source'" class="agent-page agent-page--source">
                <p class="hint">原文预览（完整三版编辑请用「经典编辑」→ 原文抽屉）</p>
                <div v-if="sourceExcerpt" class="agent-source-excerpt">
                  <strong v-if="selectedPerson">节选 · {{ selectedPerson.name }}</strong>
                  <p>{{ sourceExcerpt }}</p>
                </div>
                <textarea v-model="sourceText" class="input agent-source-text" readonly rows="12" />
              </div>
            </template>
          </template>
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
