<script setup lang="ts">
import { ref, watch } from 'vue'
import { api } from '../utils/api'

const show = defineModel<boolean>({ default: false })

const emit = defineEmits<{
  toast: [message: string, type?: 'success' | 'error' | 'info']
  saved: []
}>()

const loading = ref(false)
const saving = ref(false)
const scanning = ref(false)
const enabled = ref(true)
const dailyRunTimes = ref('08:00, 20:00')
const onOpenMaxHours = ref(48)
const compareOwned = ref(true)
const compareFollowed = ref(true)
const compareSnapshots = ref(true)
const minConfidence = ref(0.62)
const lastScan = ref<any>(null)
const pendingCount = ref(0)
const snapshots = ref<any[]>([])
const snapshotImportInput = ref<HTMLInputElement | null>(null)
const familySnapshotId = ref('')

const props = defineProps<{
  families?: Array<{ id: string; name?: string }>
}>()

function notify(msg: string, type: 'success' | 'error' | 'info' = 'info') {
  emit('toast', msg, type)
}

function parseTimes(raw: string): string[] {
  return raw
    .split(/[,，\n]/)
    .map(s => s.trim())
    .filter(Boolean)
}

async function load() {
  loading.value = true
  try {
    const res = await api('GET', '/agent/schedule')
    if (res.success && res.settings) {
      const s = res.settings
      enabled.value = !!s.enabled
      dailyRunTimes.value = (s.daily_run_times || ['08:00', '20:00']).join(', ')
      onOpenMaxHours.value = Number(s.on_open_max_hours) || 48
      compareOwned.value = s.compare_owned_families !== false
      compareFollowed.value = s.compare_followed_families !== false
      compareSnapshots.value = s.compare_snapshots !== false
      minConfidence.value = Number(s.min_match_confidence) || 0.62
    }
    lastScan.value = res.last_scan || null
    pendingCount.value = res.pending_discoveries || 0
    const snapRes = await api('GET', '/genealogy-snapshots')
    snapshots.value = snapRes.snapshots || []
  } finally {
    loading.value = false
  }
}

function normalizeTimes(raw: string): string[] {
  const parts = parseTimes(raw)
  const valid: string[] = []
  for (const slot of parts) {
    const m = slot.match(/^(\d{1,2}):(\d{2})$/)
    if (!m) continue
    const h = Number(m[1])
    const min = Number(m[2])
    if (h >= 0 && h <= 23 && min >= 0 && min <= 59) {
      valid.push(`${String(h).padStart(2, '0')}:${String(min).padStart(2, '0')}`)
    }
  }
  return valid
}

function buildSavePayload() {
  const times = normalizeTimes(dailyRunTimes.value)
  const hours = Number(onOpenMaxHours.value)
  const confidence = Number(minConfidence.value)
  return {
    enabled: enabled.value,
    daily_run_times: times,
    on_open_max_hours: Number.isFinite(hours) ? Math.min(168, Math.max(1, Math.round(hours))) : 48,
    compare_owned_families: compareOwned.value,
    compare_followed_families: compareFollowed.value,
    compare_snapshots: compareSnapshots.value,
    min_match_confidence: Number.isFinite(confidence)
      ? Math.min(1, Math.max(0.3, Math.round(confidence * 100) / 100))
      : 0.62,
  }
}

async function saveSettings() {
  const times = normalizeTimes(dailyRunTimes.value)
  if (enabled.value && !times.length) {
    notify('请填写至少一个有效的运行时刻，如 08:00, 20:00', 'error')
    return
  }
  saving.value = true
  try {
    const payload = buildSavePayload()
    const res = await api('PUT', '/agent/schedule', payload)
    if (res.success) {
      if (res.settings) {
        const s = res.settings
        enabled.value = !!s.enabled
        dailyRunTimes.value = (s.daily_run_times || times).join(', ')
        onOpenMaxHours.value = Number(s.on_open_max_hours) || payload.on_open_max_hours
        minConfidence.value = Number(s.min_match_confidence) || payload.min_match_confidence
      }
      notify('智能体设置已保存', 'success')
      emit('saved')
    } else {
      notify(res.message || res.detail || '保存失败，请确认后端已重启（python main.py）', 'error')
    }
  } catch (e: unknown) {
    notify((e as Error)?.message || '保存失败', 'error')
  } finally {
    saving.value = false
  }
}

async function scanNow() {
  scanning.value = true
  try {
    const res = await api('POST', '/agent/genealogy-scan', { trigger: 'manual' })
    if (res.success) {
      notify(res.summary || '扫描完成', 'success')
      pendingCount.value = res.pending_total || 0
      emit('saved')
    } else {
      notify(res.message || '扫描失败', 'error')
    }
  } finally {
    scanning.value = false
  }
}

async function importSnapshotFile(e: Event) {
  const file = (e.target as HTMLInputElement).files?.[0]
  if (!file) return
  try {
    const text = await file.text()
    const data = JSON.parse(text)
    const res = await api('POST', '/genealogy-snapshots', {
      name: file.name.replace(/\.json$/i, ''),
      archive: data,
    })
    if (res.success) {
      notify('大库快照已导入', 'success')
      await load()
    } else {
      notify(res.message || '导入失败', 'error')
    }
  } catch {
    notify('JSON 解析失败', 'error')
  } finally {
    if (snapshotImportInput.value) snapshotImportInput.value.value = ''
  }
}

async function snapshotFromFamily() {
  if (!familySnapshotId.value) return
  const fam = props.families?.find(f => f.id === familySnapshotId.value)
  const res = await api('POST', `/genealogy-snapshots/from-family/${familySnapshotId.value}`, {
    name: fam?.name ? `${fam.name} · 快照` : undefined,
  })
  if (res.success) {
    notify('已从族谱生成快照', 'success')
    await load()
  } else {
    notify(res.message || '生成失败', 'error')
  }
}

async function removeSnapshot(id: string) {
  const res = await api('DELETE', `/genealogy-snapshots/${id}`)
  if (res.success) {
    notify('已删除快照', 'success')
    snapshots.value = snapshots.value.filter(s => s.id !== id)
  } else {
    notify(res.message || '删除失败', 'error')
  }
}

watch(show, open => {
  if (open) void load()
})
</script>

<template>
  <div v-if="show" class="modal" @click.self="show = false">
    <div class="modal-content modal-lg ai-settings-modal agent-settings-modal" @click.stop>
      <div class="ai-settings-header">
        <h3>族谱智能体</h3>
        <button type="button" class="btn-close" @click="show = false">×</button>
      </div>
      <p class="hint agent-settings-intro">定时整理关系、跨族谱与大库对照；发现结果需您确认后才写入。</p>

      <div v-if="loading" class="loading">加载中…</div>
      <template v-else>
        <section class="agent-settings-section">
          <label class="agent-settings-toggle">
            <input v-model="enabled" type="checkbox" />
            启用后台智能整理
          </label>
          <div class="agent-settings-grid">
            <label>
              每天运行时刻（逗号分隔）
              <input v-model="dailyRunTimes" class="input" placeholder="08:00, 20:00" />
            </label>
            <label>
              打开网页超过（小时）自动扫
              <input v-model.number="onOpenMaxHours" type="number" min="1" max="168" class="input" />
            </label>
            <label>
              最低匹配置信度（0~1）
              <input v-model.number="minConfidence" type="number" min="0.3" max="1" step="0.01" class="input" />
            </label>
          </div>
          <div class="agent-settings-checks">
            <label><input v-model="compareOwned" type="checkbox" /> 本人多份族谱互相对照</label>
            <label><input v-model="compareFollowed" type="checkbox" /> 与关注族谱对照</label>
            <label><input v-model="compareSnapshots" type="checkbox" /> 与大库快照对照</label>
          </div>
          <p v-if="lastScan" class="hint agent-settings-meta">
            上次扫描：{{ lastScan.started_at?.slice(0, 16) }} · {{ lastScan.summary || '—' }}
            <span v-if="pendingCount"> · 待确认 {{ pendingCount }} 条</span>
          </p>
          <div class="agent-settings-actions">
            <button type="button" class="btn-secondary btn-sm" :disabled="scanning" @click="scanNow">
              {{ scanning ? '扫描中…' : '立即扫描' }}
            </button>
          </div>
        </section>

        <section class="agent-settings-section">
          <h4>大库快照</h4>
          <p class="hint">导入 JSON 归档或从现有族谱生成，供智能体对照匹配。</p>
          <div class="agent-settings-actions agent-settings-actions--wrap">
            <button type="button" class="btn-secondary btn-sm" @click="snapshotImportInput?.click()">导入 JSON</button>
            <input ref="snapshotImportInput" type="file" accept=".json,application/json" class="ocr-image-file-input" @change="importSnapshotFile" />
            <select v-if="families?.length" v-model="familySnapshotId" class="input input-inline">
              <option value="">从族谱生成…</option>
              <option v-for="f in families" :key="f.id" :value="f.id">{{ f.name }}</option>
            </select>
            <button type="button" class="btn-secondary btn-sm" :disabled="!familySnapshotId" @click="snapshotFromFamily">生成快照</button>
          </div>
          <ul v-if="snapshots.length" class="agent-snapshot-list">
            <li v-for="s in snapshots" :key="s.id">
              <strong>{{ s.name }}</strong>
              <span class="hint">{{ s.person_count || 0 }} 人 · {{ s.relation_count || 0 }} 关系</span>
              <button type="button" class="btn-xs btn-danger-text" @click="removeSnapshot(s.id)">删除</button>
            </li>
          </ul>
          <p v-else class="hint">暂无大库快照</p>
        </section>
      </template>

      <div class="modal-actions">
        <button type="button" class="btn-secondary" @click="show = false">关闭</button>
        <button type="button" class="btn-primary" :disabled="saving" @click="saveSettings">
          {{ saving ? '保存中…' : '保存设置' }}
        </button>
      </div>
    </div>
  </div>
</template>
