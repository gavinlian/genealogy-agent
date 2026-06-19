<script setup lang="ts">
import { ref, watch } from 'vue'
import { api } from '../utils/api'

export type GenerationScheme = 'absolute' | 'local_restart' | 'zibei_assist'

const props = withDefaults(
  defineProps<{
    familyId: string
    generationScheme?: GenerationScheme
    generationEpochOffset?: number
    compact?: boolean
  }>(),
  {
    generationScheme: 'absolute',
    generationEpochOffset: 1,
    compact: false,
  },
)

const emit = defineEmits<{
  saved: [payload: { generation_scheme: GenerationScheme; generation_epoch_offset: number }]
  notify: [message: string, type?: 'success' | 'error' | 'info']
}>()

const scheme = ref<GenerationScheme>(props.generationScheme)
const epochOffset = ref(Math.max(1, props.generationEpochOffset || 1))
const saving = ref(false)
const recalculating = ref(false)

watch(
  () => [props.generationScheme, props.generationEpochOffset] as const,
  ([s, o]) => {
    scheme.value = s || 'absolute'
    epochOffset.value = Math.max(1, o || 1)
  },
)

async function saveRules() {
  if (!props.familyId) return
  saving.value = true
  try {
    const res = await api('PUT', `/families/${props.familyId}`, {
      generation_scheme: scheme.value,
      generation_epoch_offset: epochOffset.value,
    })
    if (!res.success) {
      emit('notify', res.detail || '保存世代规则失败', 'error')
      return
    }
    emit('saved', {
      generation_scheme: scheme.value,
      generation_epoch_offset: epochOffset.value,
    })
    emit('notify', '世代规则已保存', 'success')
  } catch (e: unknown) {
    emit('notify', (e as Error)?.message || '保存失败', 'error')
  } finally {
    saving.value = false
  }
}

async function recalculateGenerations() {
  if (!props.familyId) return
  recalculating.value = true
  try {
    await saveRules()
    const res = await api('POST', `/families/${props.familyId}/recalculate-generations`, {})
    if (!res.success) {
      emit('notify', res.detail || '重算失败', 'error')
      return
    }
    const n = res.unresolved_count ?? 0
    emit('notify', n ? `已重算，${n} 人未能连到始祖` : '已按始祖重算全谱世次', 'success')
  } catch (e: unknown) {
    emit('notify', (e as Error)?.message || '重算失败', 'error')
  } finally {
    recalculating.value = false
  }
}
</script>

<template>
  <div class="family-generation-rules" :class="{ 'family-generation-rules--compact': compact }">
    <div class="family-generation-rules-head">
      <strong>世代规则</strong>
      <span class="hint">支谱常「谱面一世 = 全谱第 N 世」</span>
    </div>
    <div class="family-generation-rules-body">
      <label class="family-generation-rules-field">
        <span>计数方式</span>
        <select v-model="scheme" class="input input-inline">
          <option value="absolute">全谱（谱面一世 = 全谱一世）</option>
          <option value="local_restart">支谱（谱面从一世重计）</option>
          <option value="zibei_assist">字辈辅助（暂同全谱）</option>
        </select>
      </label>
      <label v-if="scheme === 'local_restart'" class="family-generation-rules-field">
        <span>谱面「一世」= 全谱第</span>
        <input v-model.number="epochOffset" type="number" min="1" max="999" class="input input-inline family-generation-rules-offset" />
        <span>世</span>
      </label>
      <p v-if="scheme === 'local_restart'" class="hint family-generation-rules-tip">
        例：设为 15 时，RDL 行「一世 张公」入库为全谱第 15 世；也可在行内写 <code>[全世15]</code> 强制指定。
      </p>
    </div>
    <div class="family-generation-rules-actions">
      <button type="button" class="btn-xs btn-primary" :disabled="saving" @click="saveRules">
        {{ saving ? '保存中…' : '保存规则' }}
      </button>
      <button type="button" class="btn-xs btn-secondary" :disabled="recalculating" @click="recalculateGenerations">
        {{ recalculating ? '重算中…' : '重算全谱世次' }}
      </button>
    </div>
  </div>
</template>
