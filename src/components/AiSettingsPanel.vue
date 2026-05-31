<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { api } from '../utils/api'

const show = defineModel<boolean>({ default: false })

const providers = ref<any[]>([])
const keyTab = ref('minimax')
const providerKeys = ref<Record<string, { api_key: string; api_base: string; group_id?: string; configured?: boolean }>>({})
const ocrConfig = ref({ provider: 'minimax', model: 'MiniMax-M2.7' })
const parseConfig = ref({ provider: 'minimax', model: 'MiniMax-M2.7' })
const routingMode = ref<'auto' | 'manual'>('auto')
const ocrTier = ref<'auto' | 'fast' | 'slow'>('auto')
const parseTier = ref<'auto' | 'fast' | 'slow'>('auto')
const aiRouting = ref<any>(null)
const showByok = ref(false)
const saving = ref(false)

type TestState = { loading: boolean; ok: boolean | null; message: string; preview: string; latency: number }
const emptyTest = (): TestState => ({ loading: false, ok: null, message: '', preview: '', latency: 0 })
const testStatus = ref<Record<'key' | 'ocr' | 'parse', TestState>>({
  key: emptyTest(),
  ocr: emptyTest(),
  parse: emptyTest(),
})

const TEST_MIN_DISPLAY_MS = 400

const visionProviders = computed(() =>
  providers.value.filter(p => p.supports_vision && (p.vision_models?.length || p.vision_model))
)

const ocrModelOptions = computed(() => {
  const p = providers.value.find(item => item.id === ocrConfig.value.provider)
  if (!p) return []
  const list = p.vision_models?.length ? p.vision_models : (p.vision_model ? [p.vision_model] : [])
  if (ocrConfig.value.model && !list.includes(ocrConfig.value.model)) {
    return [ocrConfig.value.model, ...list]
  }
  return list
})

const parseModelOptions = computed(() => {
  const p = providers.value.find(item => item.id === parseConfig.value.provider)
  if (!p) return []
  const list = p.text_models?.length ? p.text_models : (p.text_model ? [p.text_model] : [])
  if (parseConfig.value.model && !list.includes(parseConfig.value.model)) {
    return [parseConfig.value.model, ...list]
  }
  return list
})

const activeProvider = computed(() =>
  providers.value.find(p => p.id === keyTab.value) || { id: 'minimax', label: 'MiniMax' }
)

const quotaBuckets = computed(() => aiRouting.value?.quota?.buckets || {})

function providerLabel(p: { id?: string; label?: string; name?: string }) {
  return p.label || p.name || p.id || ''
}

function initProviderKeys(list: any[]) {
  const keys: Record<string, { api_key: string; api_base: string; group_id?: string; configured?: boolean }> = {}
  for (const p of list) {
    keys[p.id] = providerKeys.value[p.id] || {
      api_key: '',
      api_base: p.id === 'custom' ? '' : (p.api_base || ''),
      group_id: '',
      configured: false,
    }
  }
  providerKeys.value = keys
}

function quotaPercent(key: string) {
  const b = quotaBuckets.value[key]
  if (!b || !b.limit) return 0
  return Math.min(100, Math.round((b.used / b.limit) * 100))
}

function tierLabel(tier: string) {
  if (tier === 'fast') return '快速'
  if (tier === 'slow') return '慢速'
  return '自动'
}

async function fetchProviders() {
  try {
    const res = await api('GET', '/ai/providers')
    providers.value = res
    initProviderKeys(res)
  } catch {
    providers.value = []
  }
}

async function fetchAISettings() {
  try {
    const res = await api('GET', '/ai/config')
    if (res.ocr) ocrConfig.value = { ...ocrConfig.value, ...res.ocr }
    if (res.parse) parseConfig.value = { ...parseConfig.value, ...res.parse }
    if (res.routing_mode) routingMode.value = res.routing_mode
    if (res.ocr_tier) ocrTier.value = res.ocr_tier
    if (res.parse_tier) parseTier.value = res.parse_tier
    if (res.keys) {
      for (const [pid, info] of Object.entries(res.keys as Record<string, any>)) {
        if (!providerKeys.value[pid]) {
          providerKeys.value[pid] = { api_key: '', api_base: info.api_base || '', group_id: '', configured: false }
        }
        providerKeys.value[pid].configured = info.configured
        if (info.api_base) providerKeys.value[pid].api_base = info.api_base
        if (info.group_id) providerKeys.value[pid].group_id = info.group_id
      }
    }
  } catch { /* ignore */ }
}

async function fetchAiRouting() {
  try {
    aiRouting.value = await api('GET', '/ai/routing')
  } catch {
    aiRouting.value = null
  }
}

function onOcrProviderChange() {
  const p = providers.value.find(item => item.id === ocrConfig.value.provider)
  const models = p?.vision_models?.length ? p.vision_models : (p?.vision_model ? [p.vision_model] : [])
  if (models.length) ocrConfig.value.model = models[0]
}

function onParseProviderChange() {
  const p = providers.value.find(item => item.id === parseConfig.value.provider)
  const models = p?.text_models?.length ? p.text_models : (p?.text_model ? [p.text_model] : [])
  if (models.length) parseConfig.value.model = models[0]
}

function buildTestPayload(task: 'key' | 'ocr' | 'parse') {
  const payload: Record<string, string> = { task }
  if (task === 'key') {
    payload.provider = keyTab.value
    if (keyTab.value === 'minimax') {
      payload.model = 'MiniMax-M2.7'
    } else {
      const p = providers.value.find(item => item.id === keyTab.value)
      payload.model = p?.text_models?.[0] || p?.text_model || parseConfig.value.model
    }
  } else if (task === 'ocr') {
    payload.provider = ocrConfig.value.provider
    payload.model = ocrConfig.value.model
  } else {
    payload.provider = parseConfig.value.provider
    payload.model = parseConfig.value.model
  }
  const pk = providerKeys.value[payload.provider]
  if (pk?.api_key) payload.api_key = pk.api_key
  if (pk?.group_id) payload.group_id = pk.group_id
  if (payload.provider === 'custom' && pk?.api_base) payload.api_base = pk.api_base
  return payload
}

async function sleep(ms: number) {
  return new Promise(resolve => setTimeout(resolve, ms))
}

async function applyTestResult(
  task: 'key' | 'ocr' | 'parse',
  startedAt: number,
  result: { ok: boolean; message: string; preview?: string; latency?: number },
) {
  const elapsed = Date.now() - startedAt
  if (elapsed < TEST_MIN_DISPLAY_MS) {
    await sleep(TEST_MIN_DISPLAY_MS - elapsed)
  }
  testStatus.value[task] = {
    loading: false,
    ok: result.ok,
    message: result.message,
    preview: result.preview || '',
    latency: result.latency || 0,
  }
}

async function testAIModel(task: 'key' | 'ocr' | 'parse') {
  const startedAt = Date.now()
  testStatus.value[task] = { ...emptyTest(), loading: true, message: '连接中…' }

  if (task === 'key' && keyTab.value === 'minimax') {
    const pk = providerKeys.value.minimax
    if (!pk?.configured) {
      if (!pk?.api_key?.trim()) {
        await applyTestResult(task, startedAt, { ok: false, message: '请先填写 API Key' })
        return
      }
      if (!pk?.group_id?.trim()) {
        await applyTestResult(task, startedAt, {
          ok: false,
          message: '请先填写 Group ID（MiniMax 控制台 → 基础信息）',
        })
        return
      }
    }
  }

  try {
    const res = await api('POST', '/ai/test', buildTestPayload(task))
    await applyTestResult(task, startedAt, {
      ok: !!res.success,
      message: res.message || res.error || (res.success ? '连接成功，模型有回应' : '测试失败'),
      preview: res.reply_preview || '',
      latency: res.latency_ms || 0,
    })
  } catch (e: any) {
    await applyTestResult(task, startedAt, {
      ok: false,
      message: e?.message || '请求失败，请确认后端已启动（端口 8080）',
    })
  }
}

async function saveSettings() {
  saving.value = true
  try {
    const keys: Record<string, { api_key?: string; api_base?: string; group_id?: string }> = {}
    for (const [pid, val] of Object.entries(providerKeys.value)) {
      const entry: { api_key?: string; api_base?: string; group_id?: string } = {}
      if (val.api_key) entry.api_key = val.api_key
      if (pid === 'custom' && val.api_base) entry.api_base = val.api_base
      if (pid === 'minimax' && val.group_id) entry.group_id = val.group_id
      if (Object.keys(entry).length) keys[pid] = entry
    }
    const mm = providerKeys.value.minimax
    if (mm) {
      keys.minimax = { ...(keys.minimax || {}), group_id: mm.group_id || '' }
    }
    await api('POST', '/ai/config', {
      keys,
      ocr: ocrConfig.value,
      parse: parseConfig.value,
      routing_mode: routingMode.value,
      ocr_tier: ocrTier.value,
      parse_tier: parseTier.value,
    })
    show.value = false
    await fetchAISettings()
    await fetchAiRouting()
  } finally {
    saving.value = false
  }
}

watch(show, async (open) => {
  if (!open) return
  await fetchProviders()
  await fetchAISettings()
  await fetchAiRouting()
})
</script>

<template>
  <div v-if="show" class="modal">
    <div class="modal-content modal-lg ai-settings-modal">
      <div class="ai-settings-header">
        <h3>AI 模型</h3>
        <button type="button" class="btn-close" @click="show = false">×</button>
      </div>

      <!-- Auto / Manual -->
      <div class="ai-mode-toggle">
        <button
          type="button"
          :class="['ai-mode-btn', { active: routingMode === 'auto' }]"
          @click="routingMode = 'auto'"
        >
          <span class="ai-mode-title">Auto</span>
          <span class="ai-mode-desc">智能调度，无需配置 Key 也可上手</span>
        </button>
        <button
          type="button"
          :class="['ai-mode-btn', { active: routingMode === 'manual' }]"
          @click="routingMode = 'manual'"
        >
          <span class="ai-mode-title">手动</span>
          <span class="ai-mode-desc">指定 Provider 与模型</span>
        </button>
      </div>

      <!-- Quota -->
      <section v-if="aiRouting" class="ai-quota-section">
        <div class="ai-quota-head">
          <span class="ai-quota-plan">{{ aiRouting.quota?.plan_label || '免费版' }}</span>
          <span v-if="aiRouting.pro?.coming_soon" class="ai-pro-badge">
            Pro ¥{{ aiRouting.pro.price_monthly_cny }}/月 · 即将上线
          </span>
        </div>
        <p class="ai-quota-hint">
          <template v-if="aiRouting.platform_available">平台免费额度已启用，Auto 模式可直接使用。</template>
          <template v-else-if="aiRouting.byok_any_configured">已检测到自带 Key，Auto 将优先使用您的配置。</template>
          <template v-else>未配置 Key 时，关系解析可本地规则降级；OCR 需配置 Key 或等待平台额度。</template>
        </p>
        <div class="ai-quota-grid">
          <div v-for="key in ['ocr_fast', 'ocr_slow', 'parse_fast', 'parse_slow']" :key="key" class="ai-quota-row">
            <span class="ai-quota-label">
              {{ key.startsWith('ocr') ? 'OCR' : '解析' }}
              {{ key.endsWith('fast') ? '快速' : '慢速' }}
            </span>
            <div class="ai-quota-bar-wrap">
              <div class="ai-quota-bar" :style="{ width: quotaPercent(key) + '%' }"></div>
            </div>
            <span class="ai-quota-num">
              {{ quotaBuckets[key]?.used ?? 0 }}/{{ quotaBuckets[key]?.limit ?? '—' }}
            </span>
          </div>
        </div>
      </section>

      <!-- Auto recommendations -->
      <section v-if="routingMode === 'auto' && aiRouting?.recommendations" class="ai-rec-section">
        <h4 class="ai-section-title">当前调度预览</h4>
        <div class="ai-rec-card">
          <span class="ai-rec-task">OCR 识别</span>
          <span class="ai-rec-value">
            {{ aiRouting.recommendations.ocr?.label || '—' }}
            <em v-if="aiRouting.recommendations.ocr?.tier">（{{ tierLabel(aiRouting.recommendations.ocr.tier) }}）</em>
          </span>
        </div>
        <div class="ai-rec-card">
          <span class="ai-rec-task">关系解析</span>
          <span class="ai-rec-value">
            <template v-if="aiRouting.recommendations.parse?.fallback_local">本地规则（无 Key 降级）</template>
            <template v-else>
              {{ aiRouting.recommendations.parse?.label || '—' }}
              <em v-if="aiRouting.recommendations.parse?.tier">（{{ tierLabel(aiRouting.recommendations.parse.tier) }}）</em>
            </template>
          </span>
        </div>
        <div class="ai-tier-picks">
          <label>OCR 偏好</label>
          <select v-model="ocrTier" class="input input-inline">
            <option value="auto">自动（快→慢排队）</option>
            <option value="fast">优先快速</option>
            <option value="slow">慢速 / 省额度</option>
          </select>
          <label>解析偏好</label>
          <select v-model="parseTier" class="input input-inline">
            <option value="auto">自动（快→慢排队）</option>
            <option value="fast">优先快速</option>
            <option value="slow">慢速 / 省额度</option>
          </select>
        </div>
      </section>

      <!-- Manual model picks -->
      <section v-if="routingMode === 'manual'" class="ai-manual-section">
        <div class="model-row">
          <span class="model-label">OCR 识别</span>
          <select v-model="ocrConfig.provider" class="input input-inline" @change="onOcrProviderChange">
            <option v-for="p in visionProviders" :key="p.id" :value="p.id">{{ providerLabel(p) }}</option>
          </select>
          <select v-if="ocrModelOptions.length" v-model="ocrConfig.model" class="input input-inline">
            <option v-for="m in ocrModelOptions" :key="m" :value="m">{{ m }}</option>
          </select>
          <input v-else v-model="ocrConfig.model" class="input input-inline" placeholder="模型名称"/>
          <button type="button" class="btn-test" :disabled="testStatus.ocr.loading" @click="testAIModel('ocr')">
            {{ testStatus.ocr.loading ? '测试中…' : '测试' }}
          </button>
        </div>
        <p v-if="testStatus.ocr.message" :class="['test-result', 'test-result-block', testStatus.ocr.ok ? 'ok' : 'fail']">
          OCR：{{ testStatus.ocr.ok ? '✓' : '✗' }} {{ testStatus.ocr.message }}
        </p>

        <div class="model-row">
          <span class="model-label">关系解析</span>
          <select v-model="parseConfig.provider" class="input input-inline" @change="onParseProviderChange">
            <option v-for="p in providers" :key="p.id" :value="p.id">{{ providerLabel(p) }}</option>
          </select>
          <select v-if="parseModelOptions.length" v-model="parseConfig.model" class="input input-inline">
            <option v-for="m in parseModelOptions" :key="m" :value="m">{{ m }}</option>
          </select>
          <input v-else v-model="parseConfig.model" class="input input-inline" placeholder="模型名称"/>
          <button type="button" class="btn-test" :disabled="testStatus.parse.loading" @click="testAIModel('parse')">
            {{ testStatus.parse.loading ? '测试中…' : '测试' }}
          </button>
        </div>
        <p v-if="testStatus.parse.message" :class="['test-result', 'test-result-block', testStatus.parse.ok ? 'ok' : 'fail']">
          解析：{{ testStatus.parse.ok ? '✓' : '✗' }} {{ testStatus.parse.message }}
        </p>
      </section>

      <!-- BYOK -->
      <section class="ai-byok-section">
        <button type="button" class="ai-byok-toggle" @click="showByok = !showByok">
          {{ showByok ? '▼' : '▶' }} 自带 API Key（可选，Auto 模式下作为备选）
        </button>
        <div v-show="showByok" class="ai-byok-body">
          <div class="provider-tabs">
            <div
              v-for="p in providers"
              :key="p.id"
              :class="['tab-item', { active: keyTab === p.id }]"
              @click="keyTab = p.id"
            >
              <span class="tab-name">{{ providerLabel(p) }}</span>
              <span v-if="providerKeys[p.id]?.configured" class="tab-dot"></span>
              <span v-if="p.is_free" class="tab-badge">免费额度</span>
            </div>
          </div>
          <div class="settings-group">
            <label>{{ providerLabel(activeProvider) }} API Key</label>
            <input
              v-if="providerKeys[keyTab]"
              v-model="providerKeys[keyTab].api_key"
              type="password"
              :placeholder="providerKeys[keyTab]?.configured ? '已保存，输入新 Key 可覆盖' : '输入 API Key'"
              class="input"
            />
            <input
              v-if="keyTab === 'minimax' && providerKeys[keyTab]"
              v-model="providerKeys[keyTab].group_id"
              type="text"
              placeholder="Group ID（MiniMax 必填）"
              class="input"
            />
            <input
              v-if="keyTab === 'custom' && providerKeys[keyTab]"
              v-model="providerKeys[keyTab].api_base"
              type="text"
              placeholder="API Base URL"
              class="input"
            />
            <div class="test-row">
              <button type="button" class="btn-test" :disabled="testStatus.key.loading" @click="testAIModel('key')">
                {{ testStatus.key.loading ? '测试中…' : '测试 API Key' }}
              </button>
            </div>
            <div
              v-if="testStatus.key.loading || testStatus.key.message"
              class="test-banner"
              :class="testStatus.key.loading ? 'pending' : (testStatus.key.ok ? 'ok' : 'fail')"
            >
              <template v-if="testStatus.key.loading">正在连接 {{ providerLabel(activeProvider) }}…</template>
              <template v-else>{{ testStatus.key.ok ? '✓' : '✗' }} {{ testStatus.key.message }}</template>
            </div>
          </div>
        </div>
      </section>

      <div class="modal-actions">
        <button type="button" class="btn-secondary" @click="show = false">取消</button>
        <button type="button" class="btn-primary" :disabled="saving" @click="saveSettings">
          {{ saving ? '保存中…' : '保存' }}
        </button>
      </div>
    </div>
  </div>
</template>
