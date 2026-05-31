<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(
  defineProps<{
    baselineText: string
    baselineLabel?: string
    modelValue: string
    rightLabel?: string
    rightPlaceholder?: string
    readonlyRight?: boolean
  }>(),
  {
    baselineLabel: '对照稿',
    rightLabel: '当前稿',
    rightPlaceholder: '在此编辑…',
    readonlyRight: false,
  },
)

const emit = defineEmits<{ 'update:modelValue': [value: string] }>()

const rightText = computed({
  get: () => props.modelValue,
  set: (v: string) => emit('update:modelValue', v),
})

const baselineLines = computed(() => (props.baselineText || '').split('\n'))
const rightLines = computed(() => (rightText.value || '').split('\n'))
</script>

<template>
  <div class="source-text-pair">
    <div class="source-text-pair-col source-text-pair-col--baseline">
      <div class="source-text-pair-head">{{ baselineLabel }}</div>
      <pre class="source-text-pair-body">{{ baselineText || '（暂无内容）' }}</pre>
    </div>
    <div class="source-text-pair-col source-text-pair-col--edit">
      <div class="source-text-pair-head">{{ rightLabel }}</div>
      <textarea
        v-if="!readonlyRight"
        v-model="rightText"
        class="source-text-pair-editor"
        :placeholder="rightPlaceholder"
        spellcheck="false"
      />
      <pre v-else class="source-text-pair-body">{{ modelValue || '（暂无内容）' }}</pre>
    </div>
    <p v-if="baselineLines.length || rightLines.length" class="hint source-text-pair-meta">
      左 {{ baselineLines.length }} 行 · 右 {{ rightLines.length }} 行 · 左右对照改字
    </p>
  </div>
</template>
