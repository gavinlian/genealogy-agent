<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { api } from '../../utils/api'
import { getAgent } from '../../agent/registry'
import { applyGenealogyUiActions } from '../../agent/uiActions'
import type { AgentMessage, AgentUiAction } from '../../agent/types'
import AgentChatPane from './AgentChatPane.vue'

const props = defineProps<{
  familyId: string
  familyName?: string
}>()

const emit = defineEmits<{
  refresh: []
  backToChat: []
}>()

const agent = getAgent()
const messages = ref<AgentMessage[]>([])
const chatLoading = ref(false)
const chatExpanded = ref(false)
const confirmationLoading = ref<string | null>(null)
const sessionId = ref<string | null>(null)

const sessionLabel = computed(() => sessionId.value?.slice(0, 6) || '默认')
const messageCount = computed(() => messages.value.length)
const chatContextLabel = computed(() => props.familyName || '族谱')
const sessionTitle = computed(() => {
  const first = messages.value.find((m) => m.role === 'user' && m.content?.trim())
  if (!first) return props.familyName ? `${props.familyName} · 对话` : '族谱对话'
  const t = first.content.trim()
  return t.length > 16 ? `${t.slice(0, 16)}…` : t
})

async function loadState() {
  if (!props.familyId) return
  const stateRes = await api('GET', `/families/${props.familyId}/agent/state`)
  if (stateRes.success) {
    sessionId.value = stateRes.session_id || null
    messages.value = stateRes.messages || []
  }
  if (!messages.value.length) {
    messages.value = [{
      role: 'assistant',
      content: agent.welcomeWorkspace({ familyName: props.familyName }),
    }]
  }
}

function applyUiActions(actions: AgentUiAction[]) {
  applyGenealogyUiActions(actions, {
    switchTab: () => {},
    focusPerson: () => {},
    prefillPerson: () => {},
    openClassic: () => {},
    openSettings: () => {},
    openScan: () => {},
  })
}

async function sendChat(text: string) {
  const msg = text.trim()
  if (!msg || chatLoading.value || !props.familyId) return
  chatLoading.value = true
  chatExpanded.value = true
  messages.value = [...messages.value, { role: 'user', content: msg }]
  try {
    const res = await api('POST', `/families/${props.familyId}/agent/chat`, { message: msg })
    if (!res.success) {
      messages.value.push({ role: 'assistant', content: res.message || res.detail || '发送失败' })
      return
    }
    applyUiActions(res.ui_actions || [])
    if (res.state?.messages) {
      messages.value = res.state.messages
    } else {
      messages.value.push({
        role: 'assistant',
        content: res.reply || '',
        meta: { parts: res.message_parts || [] },
      })
    }
    emit('refresh')
  } finally {
    chatLoading.value = false
  }
}

async function newChatSession() {
  const res = await api('POST', `/families/${props.familyId}/agent/session/reset`, { mode: 'new' })
  if (res.success) {
    messages.value = res.messages || []
    sessionId.value = res.session_id || null
    chatExpanded.value = true
  }
}

async function clearChatHistory() {
  if (!confirm('确定清空当前对话历史？')) return
  const res = await api('POST', `/families/${props.familyId}/agent/session/reset`, { mode: 'clear' })
  if (res.success) {
    messages.value = []
    sessionId.value = res.session_id || sessionId.value
  }
}

watch(() => props.familyId, () => loadState())
onMounted(() => loadState())
</script>

<template>
  <div class="agent-chat-dock" :class="{ 'agent-chat-dock--open': chatExpanded }">
    <button
      v-if="!chatExpanded"
      type="button"
      class="agent-chat-dock-fab"
      @click="chatExpanded = true"
    >
      <span class="agent-chat-dock-fab-icon">{{ agent.icon }}</span>
      <span>与智能体对话</span>
      <span v-if="messageCount" class="agent-chat-dock-fab-count">{{ messageCount }}</span>
    </button>

    <div v-show="chatExpanded" class="agent-chat-dock-panel">
      <AgentChatPane
        :agent-name="agent.name"
        :agent-icon="agent.icon"
        :agent-tagline="agent.tagline"
        :messages="messages"
        :visible-messages="messages"
        :chat-loading="chatLoading"
        :chat-expanded="true"
        :session-label="sessionLabel"
        :session-title="sessionTitle"
        :chat-context-label="chatContextLabel"
        :message-count="messageCount"
        :confirmation-loading="confirmationLoading"
        :placeholder="agent.placeholderWorkspace"
        :show-mobile-handle="false"
        :show-scan="false"
        :show-back-to-chat="true"
        @send="sendChat"
        @toggle-expanded="chatExpanded = false"
        @new-session="newChatSession"
        @clear-history="clearChatHistory"
        @back-to-chat="emit('backToChat')"
      />
    </div>
  </div>
</template>
