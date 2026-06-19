<script setup lang="ts">
export type PipelineRegenKind = 'ocr_raw' | 'relation_desc' | 'custom'

withDefaults(
  defineProps<{
    busy?: boolean
    statusText?: string
    compact?: boolean
    showPipeline?: boolean
  }>(),
  {
    busy: false,
    statusText: '',
    compact: false,
    showPipeline: true,
  },
)

const emit = defineEmits<{
  regenerate: [kind: PipelineRegenKind]
  pipeline: [opts?: { full?: boolean; fromOcr?: boolean }]
}>()
</script>

<template>
  <div class="source-pipeline-bar" :class="{ 'source-pipeline-bar--compact': compact, 'source-pipeline-bar--busy': busy }">
    <div class="source-pipeline-bar-head">
      <strong>AI 重生</strong>
      <span class="hint">不必手改全文；对话里也可说「重新识别」「重新生成关系描述」「从头递进生成」</span>
    </div>
    <div class="source-pipeline-bar-actions">
      <button type="button" class="btn-xs btn-secondary" :disabled="busy" @click="emit('regenerate', 'ocr_raw')">
        ① 重生 OCR
      </button>
      <button type="button" class="btn-xs btn-secondary" :disabled="busy" @click="emit('regenerate', 'relation_desc')">
        ② 重生关系描述
      </button>
      <button type="button" class="btn-xs btn-secondary" :disabled="busy" @click="emit('regenerate', 'custom')">
        ③ 重生修正稿
      </button>
      <template v-if="showPipeline">
        <span class="source-pipeline-bar-sep" aria-hidden="true">|</span>
        <button
          type="button"
          class="btn-xs btn-primary source-pipeline-bar-pipeline"
          :disabled="busy"
          @click="emit('pipeline', { full: true })"
        >
          一键递进 → 预览
        </button>
        <button type="button" class="btn-xs" :disabled="busy" @click="emit('pipeline', { fromOcr: true })">
          从 OCR 递进
        </button>
      </template>
    </div>
    <p v-if="statusText" class="source-pipeline-bar-status" role="status">{{ statusText }}</p>
  </div>
</template>
