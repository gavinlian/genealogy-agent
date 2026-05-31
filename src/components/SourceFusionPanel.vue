<script setup lang="ts">
import { ref, watch } from 'vue'
import { api } from '../utils/api'

const props = defineProps<{
  familyId: string
  initialText?: string
}>()

const emit = defineEmits<{
  saved: []
  toast: [message: string, kind?: 'success' | 'error' | 'info']
}>()

const loading = ref(false)
const saving = ref(false)
const exportLoading = ref(false)
const steppedText = ref('')
const stats = ref<Record<string, number> | null>(null)

watch(
  () => props.initialText,
  (text) => {
    if (text?.trim()) {
      steppedText.value = text.trim()
    }
  },
  { immediate: true },
)

async function runFusion() {
  if (!props.familyId) return
  loading.value = true
  try {
    const res = await api('POST', `/families/${props.familyId}/source-fusion`, { include_tree: true })
    if (!res.success) {
      emit('toast', res.detail || res.message || '融合失败', 'error')
      return
    }
    steppedText.value = res.stepped_text || ''
    stats.value = res.stats || null
    emit('toast', '已生成多版本融合逐步稿', 'success')
  } catch (e: any) {
    emit('toast', e?.message || '融合失败', 'error')
  } finally {
    loading.value = false
  }
}

async function saveFusion() {
  if (!props.familyId || !steppedText.value.trim()) {
    emit('toast', '请先生成融合稿', 'info')
    return
  }
  saving.value = true
  try {
    const res = await api('POST', `/families/${props.familyId}/source-fusion/save`, {
      stepped_text: steppedText.value,
    })
    if (res.success) {
      emit('toast', '融合稿已保存为原文版本', 'success')
      emit('saved')
    } else {
      emit('toast', res.detail || '保存失败', 'error')
    }
  } catch (e: any) {
    emit('toast', e?.message || '保存失败', 'error')
  } finally {
    saving.value = false
  }
}

async function downloadArchive() {
  if (!props.familyId) return
  exportLoading.value = true
  try {
    const res = await api('GET', `/families/${props.familyId}/archive`)
    const blob = new Blob([JSON.stringify(res.archive, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `genealogy-archive-${props.familyId}.json`
    a.click()
    URL.revokeObjectURL(url)
    emit('toast', '族谱归档包已下载', 'success')
  } catch (e: any) {
    emit('toast', e?.message || '导出失败', 'error')
  } finally {
    exportLoading.value = false
  }
}

function downloadGedcom() {
  if (!props.familyId) return
  window.open(`/api/families/${props.familyId}/gedcom/export`, '_blank')
}
</script>

<template>
  <div class="source-fusion-panel">
    <div class="source-fusion-toolbar">
      <button type="button" class="btn-xs btn-primary" :disabled="loading" @click="runFusion">
        {{ loading ? '融合中…' : '融合各版原文' }}
      </button>
      <button type="button" class="btn-xs" :disabled="saving || !steppedText.trim()" @click="saveFusion">
        {{ saving ? '保存中…' : '保存融合稿' }}
      </button>
      <button type="button" class="btn-xs" :disabled="exportLoading" @click="downloadArchive">
        {{ exportLoading ? '导出中…' : '下载归档 JSON' }}
      </button>
      <button type="button" class="btn-xs" @click="downloadGedcom">导出 GEDCOM</button>
    </div>
    <p v-if="stats" class="hint source-fusion-stats">
      已处理 {{ stats.version_count }} 个原文版本 · 合并 {{ stats.merged_relation_count }} 条关系 ·
      {{ stats.merged_person_count }} 位人物
    </p>
    <p class="hint source-fusion-tip">
      从版本一 OCR、版本二关系描述、版本三修正稿与主谱关系生成<strong>逐步融合文字</strong>；保存后可在「原文」中继续校对。
      也可在对话中说：「融合各版原文并保存」。
    </p>
    <textarea
      v-model="steppedText"
      class="source-fusion-editor"
      rows="16"
      placeholder="点击「融合各版原文」生成逐步叙述稿…"
      spellcheck="false"
    />
  </div>
</template>
