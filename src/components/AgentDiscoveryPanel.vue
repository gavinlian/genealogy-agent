<script setup lang="ts">
import { ref, watch, onMounted } from 'vue'
import { api } from '../utils/api'

const show = defineModel<boolean>({ default: false })

const props = defineProps<{
  familyId?: string | null
  /** 嵌入 Tab/抽屉时始终展开，不依赖 v-model */
  embedded?: boolean
  showHeader?: boolean
}>()

const emit = defineEmits<{
  toast: [message: string, type?: 'success' | 'error' | 'info']
  applyPlan: [payload: { familyId: string; plan: unknown }]
  refresh: [pendingCount?: number]
}>()

const loading = ref(false)
const discoveries = ref<any[]>([])
const scanning = ref(false)

const TYPE_LABEL: Record<string, string> = {
  optimize_relation: '关系优化',
  data_conflict: '数据核查',
  cross_family_match: '跨谱匹配',
  snapshot_match: '大库匹配',
}

function typeLabel(t: string) {
  return TYPE_LABEL[t] || t
}

function notify(msg: string, type: 'success' | 'error' | 'info' = 'info') {
  emit('toast', msg, type)
}

async function load() {
  loading.value = true
  try {
    const q = props.familyId ? `?family_id=${encodeURIComponent(props.familyId)}&status=pending` : '?status=pending'
    const res = await api('GET', `/agent/discoveries${q}`)
    discoveries.value = res.discoveries || []
  } finally {
    loading.value = false
  }
}

async function dismiss(id: string) {
  const res = await api('POST', `/agent/discoveries/${id}/dismiss`)
  if (res.success) {
    discoveries.value = discoveries.value.filter(d => d.id !== id)
    emit('refresh', res.pending_discoveries)
  } else {
    notify(res.message || '操作失败', 'error')
  }
}

async function accept(item: any) {
  const res = await api('POST', `/agent/discoveries/${item.id}/accept`)
  if (!res.success) {
    notify(res.message || '操作失败', 'error')
    return
  }
  discoveries.value = discoveries.value.filter(d => d.id !== item.id)
  if (res.plan && res.family_id) {
    emit('applyPlan', { familyId: res.family_id, plan: res.plan })
    notify('已载入整理方案，请在整理页预览确认', 'success')
  } else {
    notify('已标记处理，请手动核对族谱', 'info')
  }
  emit('refresh', res.pending_discoveries)
}

async function scanNow() {
  scanning.value = true
  try {
    const body = props.familyId ? { family_ids: [props.familyId], trigger: 'manual' } : { trigger: 'manual' }
    const res = await api('POST', '/agent/genealogy-scan', body)
    if (res.success) {
      notify(res.summary || '扫描完成', 'success')
      await load()
      emit('refresh', res.pending_total)
    } else {
      notify(res.message || '扫描失败', 'error')
    }
  } finally {
    scanning.value = false
  }
}

watch(show, open => {
  if (open || props.embedded) void load()
})

watch(() => props.familyId, () => {
  if (show.value || props.embedded) void load()
})

onMounted(() => {
  if (props.embedded) void load()
})

defineExpose({ load, count: () => discoveries.value.length })
</script>

<template>
  <div v-if="embedded || show" :class="embedded ? 'agent-discovery-embedded' : 'workspace-drawer workspace-drawer--discoveries'">
    <header v-if="showHeader !== false" class="agent-discovery-head">
      <div>
        <h3>智能体发现</h3>
        <p class="hint">定时扫描与跨谱对照的结果；确认后才会写入族谱。</p>
      </div>
      <div class="agent-discovery-head-actions">
        <button type="button" class="btn-secondary btn-sm" :disabled="scanning" @click="scanNow">
          {{ scanning ? '扫描中…' : '立即扫描' }}
        </button>
        <button v-if="!embedded" type="button" class="btn-ghost btn-sm" @click="show = false">收起</button>
      </div>
    </header>

    <div v-if="loading" class="loading">加载中…</div>
    <div v-else-if="!discoveries.length" class="empty-state compact">
      <p>暂无待确认发现。智能体会按设置在后台继续扫描。</p>
    </div>
    <ul v-else class="agent-discovery-list">
      <li v-for="d in discoveries" :key="d.id" class="agent-discovery-item">
        <div class="agent-discovery-item-head">
          <span class="agent-discovery-type">{{ typeLabel(d.discovery_type) }}</span>
          <span v-if="d.confidence" class="agent-discovery-conf">{{ Math.round(d.confidence * 100) }}%</span>
        </div>
        <strong>{{ d.title }}</strong>
        <p v-if="d.summary" class="hint">{{ d.summary }}</p>
        <div class="agent-discovery-actions">
          <button
            v-if="d.plan"
            type="button"
            class="btn-primary btn-xs"
            @click="accept(d)"
          >
            查看整理方案
          </button>
          <button v-else type="button" class="btn-secondary btn-xs" @click="accept(d)">知道了</button>
          <button type="button" class="btn-ghost btn-xs" @click="dismiss(d.id)">忽略</button>
        </div>
      </li>
    </ul>
  </div>
</template>
