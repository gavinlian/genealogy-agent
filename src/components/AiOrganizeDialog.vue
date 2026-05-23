<script setup lang="ts">
import { ref, watch, nextTick, onMounted, computed } from 'vue'
import {
  type OrganizePlan,
  type OrganizeDiff,
  planSummary,
  planHasChanges,
  pickDefaultApplyMode,
  relLabel,
} from '../types/organize'

const props = defineProps<{
  familyId: string
  sourceText?: string
  sourceVersionId?: string
  sourceVersionLabel?: string
  initialPrompt?: string
  bootstrapFromSource?: boolean
  style?: string
  cleanSlate?: boolean
}>()

const emit = defineEmits<{
  close: []
  'plan-update': [payload: { plan: OrganizePlan | null; diff: OrganizeDiff | null }]
  'update:cleanSlate': [value: boolean]
}>()

type ChatMsg = { role: 'user' | 'assistant'; content: string }

const API = '/api'
const SOURCE_MARKER = '【族谱原文】'

const input = ref('')
const sending = ref(false)
const includeSource = ref(true)
const showSourcePreview = ref(false)
const textareaRef = ref<HTMLTextAreaElement | null>(null)
const welcomeMsg =
  '请用自然语言描述您希望的主谱效果。我会列出关系变更建议；实际应用请在主界面「族谱整理」面板操作。'
const BOOTSTRAP_PROMPT =
  '请根据附带的族谱原文，干净整理出完整主谱：提取所有人物、世代与父子/配偶关系，给出可应用的整理方案。'
const messages = ref<ChatMsg[]>([{ role: 'assistant', content: welcomeMsg }])
const lastPlan = ref<OrganizePlan | null>(null)
const lastDiff = ref<OrganizeDiff | null>(null)
const parseModelHint = ref('')
const chatEnd = ref<HTMLElement | null>(null)
const sessionId = ref('')
const refreshContextNext = ref(true)
const agentTurnCount = ref(0)
const agentContextMode = ref<'full' | 'summary'>('full')

const cleanSlateModel = computed({
  get: () => Boolean(props.cleanSlate),
  set: (v: boolean) => emit('update:cleanSlate', v),
})

async function persistAiState(extra: Record<string, unknown> = {}) {
  if (!props.familyId) return
  try {
    await api('PUT', `/families/${props.familyId}/ai-organize/state`, {
      messages: messages.value,
      session_id: sessionId.value || null,
      session_meta: {
        turn_count: agentTurnCount.value,
        context_mode: agentContextMode.value,
      },
      ...extra,
    })
  } catch {
    /* ignore persist errors */
  }
}

async function loadAiState() {
  if (!props.familyId) return
  try {
    const res = await api('GET', `/families/${props.familyId}/ai-organize/state`)
    if (res.success === false) return
    messages.value =
      Array.isArray(res.messages) && res.messages.length
        ? res.messages
        : [{ role: 'assistant', content: welcomeMsg }]
    sessionId.value = res.session_id || ''
    const meta = res.session_meta || {}
    agentTurnCount.value = meta.turn_count || 0
    agentContextMode.value = meta.context_mode === 'summary' ? 'summary' : 'full'
    refreshContextNext.value = !sessionId.value
    if (res.pending_plan) {
      lastPlan.value = res.pending_plan
      lastDiff.value = res.pending_diff || null
      emit('plan-update', { plan: res.pending_plan, diff: res.pending_diff || null })
    }
  } catch {
    messages.value = [{ role: 'assistant', content: welcomeMsg }]
  }
}

const sourceTextTrimmed = computed(() => (props.sourceText || '').trim())
const sourceCharCount = computed(() => sourceTextTrimmed.value.length)
const hasSource = computed(() => sourceCharCount.value > 0)
const sourcePreview = computed(() => {
  const t = sourceTextTrimmed.value
  if (!t) return ''
  return t.length > 600 ? `${t.slice(0, 600)}…（共 ${t.length} 字）` : t
})

watch(
  () => props.familyId,
  () => {
    input.value = ''
    parseModelHint.value = ''
    includeSource.value = hasSource.value
    showSourcePreview.value = false
    loadAiState()
  },
  { immediate: true },
)

watch(hasSource, (val) => {
  if (val) includeSource.value = true
})

async function loadParseModelHint() {
  try {
    const res = await api('GET', '/ai/config')
    if (res.parse?.provider && res.parse?.model) {
      parseModelHint.value = `${res.parse.provider} / ${res.parse.model}`
    }
  } catch {
    parseModelHint.value = ''
  }
}

async function api(method: string, path: string, data?: unknown) {
  const res = await fetch(`${API}${path}`, {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: data ? JSON.stringify(data) : undefined,
  })
  const text = await res.text()
  try {
    return JSON.parse(text)
  } catch {
    return { success: false, error: text.slice(0, 120) }
  }
}

function scrollChat() {
  nextTick(() => chatEnd.value?.scrollIntoView({ behavior: 'smooth' }))
}

function historyForApi() {
  return messages.value
    .filter((m) => m.role === 'user' || (m.role === 'assistant' && m.content !== welcomeMsg))
    .slice(-10)
    .map((m) => ({ role: m.role, content: m.content }))
}

function inputAlreadyHasSource() {
  return input.value.includes(SOURCE_MARKER)
}

function insertSourceText() {
  if (!hasSource.value) return
  if (inputAlreadyHasSource()) {
    showSourcePreview.value = true
    return
  }
  const block = `${SOURCE_MARKER}\n${sourceTextTrimmed.value}\n\n`
  const el = textareaRef.value
  if (el) {
    const start = el.selectionStart ?? input.value.length
    const end = el.selectionEnd ?? input.value.length
    input.value = input.value.slice(0, start) + block + input.value.slice(end)
    nextTick(() => {
      el.focus()
      const pos = start + block.length
      el.setSelectionRange(pos, pos)
    })
  } else {
    input.value = block + input.value
  }
}

function organizePayload(message: string) {
  return {
    message,
    history: historyForApi().slice(0, -1),
    style: props.style || 'su',
    include_source: includeSource.value && hasSource.value,
    source_text: includeSource.value && hasSource.value ? sourceTextTrimmed.value : '',
    source_version_id: props.sourceVersionId || undefined,
    session_id: sessionId.value || undefined,
    refresh_context: refreshContextNext.value,
    clean_slate: cleanSlateModel.value,
  }
}

function applyAgentMeta(res: any) {
  if (res.agent?.session_id) sessionId.value = res.agent.session_id
  agentTurnCount.value = res.agent?.turn_count ?? agentTurnCount.value
  agentContextMode.value = res.agent?.context_mode === 'summary' ? 'summary' : 'full'
  refreshContextNext.value = false
  if (agentTurnCount.value >= 1 && includeSource.value) includeSource.value = false
}

async function clearChatSession() {
  if (!confirm('清空本族谱 AI 对话记录？待应用方案也会清除。')) return
  if (sessionId.value) {
    await api('DELETE', `/families/${props.familyId}/ai-organize/session?session_id=${encodeURIComponent(sessionId.value)}`)
  }
  await api('PUT', `/families/${props.familyId}/ai-organize/state`, { clear_messages: true, pending_plan: null, pending_diff: null })
  sessionId.value = ''
  messages.value = [{ role: 'assistant', content: welcomeMsg }]
  lastPlan.value = null
  lastDiff.value = null
  emit('plan-update', { plan: null, diff: null })
  agentTurnCount.value = 0
  agentContextMode.value = 'full'
  refreshContextNext.value = true
  includeSource.value = hasSource.value
}

function refreshAgentContext() {
  refreshContextNext.value = true
  if (hasSource.value) includeSource.value = true
}

function bootstrapFromSource() {
  input.value = BOOTSTRAP_PROMPT
  includeSource.value = true
  cleanSlateModel.value = true
  showSourcePreview.value = true
  nextTick(() => textareaRef.value?.focus())
}

function applyInitialPrompt() {
  const prompt = (props.initialPrompt || '').trim() || (props.bootstrapFromSource ? BOOTSTRAP_PROMPT : '')
  if (!prompt) return
  input.value = prompt
  includeSource.value = hasSource.value
  cleanSlateModel.value = Boolean(props.bootstrapFromSource)
  showSourcePreview.value = hasSource.value
  nextTick(() => textareaRef.value?.focus())
}

watch(
  () => [props.familyId, props.initialPrompt, props.bootstrapFromSource] as const,
  () => {
    if (props.bootstrapFromSource || props.initialPrompt) nextTick(() => applyInitialPrompt())
  },
)

async function sendMessage() {
  const text = input.value.trim()
  if (!text || sending.value || !props.familyId) return

  messages.value.push({ role: 'user', content: text })
  input.value = ''
  sending.value = true
  scrollChat()

  try {
    const res = await api('POST', `/families/${props.familyId}/ai-organize`, organizePayload(text))
    if (res.parse?.provider && res.parse?.model) {
      parseModelHint.value = `${res.parse.provider} / ${res.parse.model}`
    }

    if (!res.success) {
      messages.value.push({
        role: 'assistant',
        content: res.explanation || res.error || res.detail || '整理失败，请重试',
      })
      lastPlan.value = null
      lastDiff.value = null
      emit('plan-update', { plan: null, diff: null })
      return
    }

    let a = res.explanation || '已完成分析'
    let suffix = res.used_ai ? '' : res.fallback === 'local' ? '\n（未配置解析模型，已用本地规则）' : ''
    if (planHasChanges(res.plan)) {
      suffix += '\n\n方案已同步到主界面「族谱整理」面板，请在那里预览并应用。'
    }
    messages.value.push({ role: 'assistant', content: a + suffix })
    lastPlan.value = res.plan || null
    lastDiff.value = res.diff || null
    pickDefaultApplyMode(res)
    applyAgentMeta(res)
    emit('plan-update', { plan: lastPlan.value, diff: lastDiff.value })
  } catch {
    messages.value.push({ role: 'assistant', content: '请求失败，请确认后端已启动' })
  } finally {
    sending.value = false
    await persistAiState({
      pending_plan: lastPlan.value,
      pending_diff: lastDiff.value,
    })
    scrollChat()
  }
}

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    sendMessage()
  }
}

onMounted(() => {
  loadParseModelHint()
  includeSource.value = hasSource.value
})
</script>

<template>
  <div class="modal ai-organize-modal" @click.self="emit('close')">
    <div class="modal-content modal-lg ai-organize-panel ai-organize-panel--chat">
      <div class="ai-settings-header">
        <h3>AI 对话助手</h3>
        <div class="ai-organize-header-actions">
          <button type="button" class="btn-xs btn-secondary" :disabled="sending" @click="refreshAgentContext">
            刷新主谱上下文
          </button>
          <button type="button" class="btn-xs btn-secondary" :disabled="sending" @click="clearChatSession">
            清空对话
          </button>
          <button class="btn-close" type="button" @click="emit('close')">×</button>
        </div>
      </div>

      <p class="hint ai-organize-hint">
        此处仅用于与 AI 对话、列出关系建议。清空主谱、应用方案请在主界面「族谱整理」面板完成。
        <span v-if="agentTurnCount > 0" class="ai-organize-model">
          会话第 {{ agentTurnCount }} 轮 · {{ agentContextMode === 'full' ? '完整上下文' : '摘要模式' }}
        </span>
        <span v-if="sourceVersionLabel" class="ai-organize-model">当前原文：{{ sourceVersionLabel }}</span>
        <span v-if="parseModelHint" class="ai-organize-model">关系解析模型：{{ parseModelHint }}</span>
      </p>

      <div class="ai-organize-chat">
        <div
          v-for="(msg, i) in messages"
          :key="i"
          :class="['ai-organize-bubble', msg.role === 'user' ? 'is-user' : 'is-assistant']"
        >
          {{ msg.content }}
        </div>
        <div v-if="sending" class="ai-organize-bubble is-assistant ai-organize-loading">思考中…</div>
        <div ref="chatEnd" />
      </div>

      <div v-if="lastPlan && planHasChanges(lastPlan)" class="ai-organize-preview ai-organize-preview--compact">
        <strong>关系摘要（详情见「族谱整理」）</strong>
        <ul class="ai-organize-compact-list">
          <li v-if="planSummary(lastPlan)!.addRel">新增关系 {{ planSummary(lastPlan)!.addRel }} 条</li>
          <li v-if="planSummary(lastPlan)!.removeRel">删除关系 {{ planSummary(lastPlan)!.removeRel }} 条</li>
          <li v-if="planSummary(lastPlan)!.newPerson">新增成员 {{ planSummary(lastPlan)!.newPerson }} 人</li>
        </ul>
        <details v-if="lastDiff?.relations_to_add?.length" class="ai-organize-details">
          <summary>新增关系列表</summary>
          <ul>
            <li v-for="(r, j) in lastDiff.relations_to_add.slice(0, 12)" :key="j">{{ relLabel(r) }}</li>
          </ul>
        </details>
      </div>

      <div v-if="hasSource" class="ai-organize-source-bar">
        <button class="btn-xs btn-secondary" type="button" :disabled="sending" @click="insertSourceText">
          {{ inputAlreadyHasSource() ? '原文已在输入框' : '插入原文' }}
        </button>
        <button class="btn-xs btn-primary" type="button" :disabled="sending || !hasSource" @click="bootstrapFromSource">
          从原文生成方案
        </button>
        <label class="ai-organize-source-toggle">
          <input v-model="includeSource" type="checkbox" :disabled="sending" />
          附带原文（{{ sourceCharCount }} 字）
        </label>
        <label class="ai-organize-source-toggle">
          <input v-model="cleanSlateModel" type="checkbox" :disabled="sending" />
          干净整理
        </label>
      </div>
      <p v-else class="hint ai-organize-no-source">暂无原文，可在顶栏「原文」中粘贴后再对话。</p>

      <div class="ai-organize-input-row">
        <textarea
          ref="textareaRef"
          v-model="input"
          class="input ai-organize-textarea"
          rows="3"
          placeholder="描述您想要的谱系结构，或请 AI 根据原文列出关系…"
          :disabled="sending"
          @keydown="onKeydown"
        />
        <div class="ai-organize-actions">
          <button class="btn-primary" type="button" :disabled="!input.trim() || sending" @click="sendMessage">
            {{ sending ? '发送中…' : '发送' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
