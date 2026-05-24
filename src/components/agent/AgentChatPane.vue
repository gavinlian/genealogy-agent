<script setup lang="ts">
import { ref, watch, nextTick } from 'vue'
import type { AgentMessage } from '../../agent/types'
import type { HomeChatSession } from '../../agent/homeSessions'
import AgentMessageBody from './AgentMessageBody.vue'

const props = defineProps<{
  agentName: string
  agentIcon: string
  agentTagline?: string
  messages: AgentMessage[]
  visibleMessages: AgentMessage[]
  chatLoading: boolean
  chatExpanded: boolean
  sessionLabel: string
  sessionTitle?: string
  chatContextLabel?: string
  messageCount: number
  confirmationLoading: string | null
  placeholder: string
  layout?: 'sidebar' | 'drawer'
  showCollapse?: boolean
  showMobileHandle?: boolean
  showScan?: boolean
  showBackToChat?: boolean
  homeSessions?: HomeChatSession[]
}>()

const emit = defineEmits<{
  send: [text: string]
  toggleExpanded: []
  collapse: []
  newSession: []
  clearHistory: []
  confirm: [token: string, approved: boolean]
  scan: []
  switchSession: [sessionId: string]
  backToHome: []
  backToChat: []
}>()
const chatInput = ref('')
const chatMenuOpen = ref(false)
const messagesEl = ref<HTMLElement | null>(null)
const composerEl = ref<HTMLTextAreaElement | null>(null)

function scrollMessagesToBottom() {
  requestAnimationFrame(() => {
    const el = messagesEl.value
    if (el) el.scrollTop = el.scrollHeight
  })
}

function resizeComposer() {
  const el = composerEl.value
  if (!el) return
  el.style.height = 'auto'
  el.style.height = `${Math.min(el.scrollHeight, 120)}px`
}

function closeChatMenu() {
  chatMenuOpen.value = false
}

function submitChat() {
  const text = chatInput.value.trim()
  if (!text || props.chatLoading) return
  emit('send', text)
  chatInput.value = ''
  nextTick(() => {
    resizeComposer()
    scrollMessagesToBottom()
  })
}

function onComposerKeydown(e: KeyboardEvent) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    submitChat()
  }
}

watch(() => props.messages.length, () => nextTick(scrollMessagesToBottom))
watch(chatInput, () => nextTick(resizeComposer))
</script>

<template>
  <div
    class="agent-chat-drawer"
    :class="{
      'agent-chat-drawer--sidebar': layout === 'sidebar' || !layout,
      'agent-chat-drawer--expanded': chatExpanded && layout === 'drawer',
      'agent-chat-drawer--collapsed': !chatExpanded && layout === 'drawer',
      'agent-chat-drawer--with-tabs': showMobileHandle !== false && layout === 'drawer',
    }"
  >
    <div class="agent-chat-drawer-toolbar">
      <button
        v-if="showCollapse"
        type="button"
        class="btn-icon agent-chat-collapse-btn"
        title="收起对话"
        aria-label="收起对话"
        @click="emit('collapse')"
      >
        ‹
      </button>
      <div class="agent-chat-identity">
        <span class="agent-chat-identity-icon">{{ agentIcon }}</span>
        <div class="agent-chat-identity-text">
          <strong>{{ agentName }}</strong>
          <span v-if="chatContextLabel" class="agent-chat-context-chip">{{ chatContextLabel }}</span>
        </div>
      </div>
      <div class="agent-chat-session-meta">
        <span class="agent-session-title" :title="sessionTitle || ''">{{ sessionTitle || `会话 ${sessionLabel}` }}</span>
        <span class="agent-session-label">#{{ sessionLabel }}</span>
        <span v-if="messageCount" class="agent-msg-count">{{ messageCount }} 条</span>
      </div>
      <div class="agent-chat-menu" @mouseleave="closeChatMenu">
        <button
          type="button"
          class="btn-icon agent-chat-menu-btn"
          title="对话管理"
          aria-label="对话管理"
          @click.stop="chatMenuOpen = !chatMenuOpen"
        >
          ⋯
        </button>
        <div v-if="chatMenuOpen" class="agent-chat-menu-panel agent-chat-menu-panel--wide">
          <div class="agent-chat-menu-section">
            <p class="agent-chat-menu-heading">当前上下文</p>
            <p class="agent-chat-menu-desc">{{ chatContextLabel || '全局' }} · {{ sessionTitle || `会话 ${sessionLabel}` }}</p>
          </div>
          <div v-if="homeSessions?.length" class="agent-chat-menu-section">
            <p class="agent-chat-menu-heading">首页会话</p>
            <button
              v-for="s in homeSessions"
              :key="s.id"
              type="button"
              class="agent-chat-menu-item agent-chat-menu-item--session"
              :class="{ 'agent-chat-menu-item--active': sessionLabel === s.id.slice(0, 6) }"
              @click="emit('switchSession', s.id); closeChatMenu()"
            >
              <span>{{ s.title }}</span>
              <span class="agent-chat-menu-item-meta">{{ s.messages.length }} 条</span>
            </button>
          </div>
          <div class="agent-chat-menu-section">
            <p class="agent-chat-menu-heading">操作</p>
            <button type="button" class="agent-chat-menu-item" @click="emit('newSession'); closeChatMenu()">
              新建会话
            </button>
            <button type="button" class="agent-chat-menu-item" @click="emit('clearHistory'); closeChatMenu()">
              清空当前会话
            </button>
            <button
              v-if="showBackToChat"
              type="button"
              class="agent-chat-menu-item"
              @click="emit('backToChat'); closeChatMenu()"
            >
              回到对话模式
            </button>
            <button
              v-if="chatContextLabel && chatContextLabel !== '全局'"
              type="button"
              class="agent-chat-menu-item"
              @click="emit('backToHome'); closeChatMenu()"
            >
              回到首页对话
            </button>
          </div>
        </div>
      </div>
    </div>

    <button
      v-if="showMobileHandle !== false && layout === 'drawer'"
      type="button"
      class="agent-chat-drawer-handle"
      :aria-expanded="chatExpanded"
      @click="emit('toggleExpanded')"
    >
      <span class="agent-chat-drawer-grab" />
      <span class="agent-chat-drawer-hint">{{ chatExpanded ? '收起' : '展开对话' }}</span>
    </button>

    <div ref="messagesEl" class="agent-messages">
      <div
        v-for="(m, i) in visibleMessages"
        :key="`${messages.length}-${i}-${m.role}`"
        class="agent-msg-wrap"
      >
        <div
          class="agent-msg"
          :class="m.role === 'user' ? 'agent-msg--user' : 'agent-msg--assistant'"
        >
        <AgentMessageBody
          :parts="m.meta?.parts"
          :fallback-content="m.meta?.parts?.length ? '' : m.content"
        />
        </div>
        <div
          v-if="m.meta?.confirmation && m.role === 'assistant'"
          class="agent-confirm-card"
        >
          <strong>{{ m.meta.confirmation.title }}</strong>
          <p class="agent-confirm-summary">{{ m.meta.confirmation.summary }}</p>
          <div v-if="m.meta.confirmation.details?.changes" class="agent-confirm-changes">
            <div
              v-for="(c, ci) in (m.meta.confirmation.details.changes as { field: string; from: unknown; to: unknown }[])"
              :key="ci"
              class="agent-confirm-change-row"
            >
              <span class="agent-confirm-change-field">{{ c.field }}</span>
              <span class="agent-confirm-change-val">{{ c.from || '空' }} → {{ c.to }}</span>
            </div>
          </div>
          <div class="agent-confirm-actions">
            <button
              type="button"
              class="btn-primary btn-sm"
              :disabled="confirmationLoading === m.meta.confirmation.token"
              @click="emit('confirm', m.meta.confirmation.token, true)"
            >
              {{ confirmationLoading === m.meta.confirmation.token ? '处理中…' : '确认写入' }}
            </button>
            <button
              type="button"
              class="btn-ghost btn-sm"
              :disabled="confirmationLoading === m.meta.confirmation.token"
              @click="emit('confirm', m.meta.confirmation.token, false)"
            >
              取消
            </button>
          </div>
        </div>
      </div>
      <div v-if="chatLoading" class="agent-msg agent-msg--assistant agent-msg--typing">思考中…</div>
    </div>

    <form class="agent-composer" @submit.prevent="submitChat">
      <div class="agent-composer-box">
        <textarea
          ref="composerEl"
          v-model="chatInput"
          class="agent-composer-input"
          rows="1"
          :placeholder="placeholder"
          :disabled="chatLoading"
          @keydown="onComposerKeydown"
        />
        <div class="agent-composer-actions">
          <button
            v-if="showScan"
            type="button"
            class="btn-icon agent-chat-action"
            title="拍照建谱"
            @click="emit('scan')"
          >
            📷
          </button>
          <button type="button" class="btn-icon agent-chat-action" title="语音（后续）" disabled>🎤</button>
          <button type="submit" class="agent-composer-send" :disabled="chatLoading || !chatInput.trim()">
            {{ chatLoading ? '…' : '↑' }}
          </button>
        </div>
      </div>
      <p class="agent-composer-hint">Enter 发送 · Shift+Enter 换行</p>
    </form>
  </div>
</template>
