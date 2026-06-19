<script setup lang="ts">
import { computed, ref } from 'vue'

const props = withDefaults(
  defineProps<{
    baselineText: string
    baselineLabel?: string
    modelValue: string
    rightLabel?: string
    rightPlaceholder?: string
    readonlyRight?: boolean
    /** 左侧对照稿可折叠，默认收起以节省空间 */
    collapsibleBaseline?: boolean
    defaultBaselineExpanded?: boolean
  }>(),
  {
    baselineLabel: '对照稿',
    rightLabel: '当前稿',
    rightPlaceholder: '在此编辑…',
    readonlyRight: false,
    collapsibleBaseline: true,
    defaultBaselineExpanded: false,
  },
)

const emit = defineEmits<{ 'update:modelValue': [value: string] }>()

const baselineExpanded = ref(props.defaultBaselineExpanded)

const rightText = computed({
  get: () => props.modelValue,
  set: (v: string) => emit('update:modelValue', v),
})

const baselineLines = computed(() => (props.baselineText || '').split('\n'))
const rightLines = computed(() => (rightText.value || '').split('\n'))
const baselineCharCount = computed(() => (props.baselineText || '').trim().length)

function toggleBaseline() {
  baselineExpanded.value = !baselineExpanded.value
}
</script>

<template>
  <div
    class="source-text-pair"
    :class="{
      'source-text-pair--baseline-collapsed': collapsibleBaseline && !baselineExpanded,
      'source-text-pair--baseline-open': !collapsibleBaseline || baselineExpanded,
    }"
  >
    <div v-if="collapsibleBaseline" class="source-text-pair-toolbar">
      <button
        type="button"
        class="source-text-pair-toggle"
        :aria-expanded="baselineExpanded"
        @click="toggleBaseline"
      >
        <span aria-hidden="true">{{ baselineExpanded ? '▾' : '▸' }}</span>
        {{ baselineExpanded ? `收起${baselineLabel}` : `查看${baselineLabel}` }}
        <span v-if="baselineCharCount" class="source-text-pair-toggle-meta">（{{ baselineLines.length }} 行）</span>
      </button>
    </div>

    <div
      v-show="!collapsibleBaseline || baselineExpanded"
      class="source-text-pair-col source-text-pair-col--baseline"
    >
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
      <template v-if="!collapsibleBaseline || baselineExpanded">
        左 {{ baselineLines.length }} 行 · 右 {{ rightLines.length }} 行 · 左右对照改字
      </template>
      <template v-else>
        右 {{ rightLines.length }} 行 · 点上方按钮展开左侧对照
      </template>
    </p>
  </div>
</template>
