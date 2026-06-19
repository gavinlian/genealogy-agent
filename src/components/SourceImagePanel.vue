<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { uploadImageUrl } from '../utils/uploadImageUrl'
import SourceImageZoom from './SourceImageZoom.vue'

export type SourceImagePage = {
  path?: string
  preview?: string
  label?: string
}

const props = withDefaults(
  defineProps<{
    imagePath?: string
    imagePaths?: string[]
    imagePreview?: string
    imagePreviews?: string[]
    alt?: string
    collapsible?: boolean
    defaultExpanded?: boolean
    compact?: boolean
  }>(),
  {
    imagePath: '',
    imagePaths: () => [],
    imagePreview: '',
    imagePreviews: () => [],
    alt: '扫描原图',
    collapsible: true,
    defaultExpanded: false,
    compact: true,
  },
)

const expanded = defineModel<boolean>('expanded', { default: false })

const pageIndex = ref(0)

const pages = computed<SourceImagePage[]>(() => {
  const paths = props.imagePaths?.length
    ? [...props.imagePaths]
    : props.imagePath
      ? [props.imagePath]
      : []
  const previews = props.imagePreviews?.length
    ? [...props.imagePreviews]
    : props.imagePreview
      ? [props.imagePreview]
      : []
  const count = Math.max(paths.length, previews.length)
  if (!count) return []

  const out: SourceImagePage[] = []
  for (let i = 0; i < count; i += 1) {
    const path = paths[i] ?? ''
    const preview = previews[i] ?? ''
    const url = uploadImageUrl(path || undefined, preview || undefined)
    if (!url) continue
    out.push({
      path: path || undefined,
      preview: preview || undefined,
      label: count > 1 ? `第 ${i + 1} 张` : '原图',
    })
  }
  return out
})

const hasPages = computed(() => pages.value.length > 0)
const multiPage = computed(() => pages.value.length > 1)

const currentSrc = computed(() => {
  const page = pages.value[pageIndex.value]
  if (!page) return ''
  return uploadImageUrl(page.path, page.preview)
})

watch(
  () => pages.value.length,
  (len) => {
    if (pageIndex.value >= len) pageIndex.value = Math.max(0, len - 1)
  },
)

watch(
  () => props.defaultExpanded,
  (v) => {
    if (!props.collapsible) expanded.value = true
    else if (v && expanded.value === false) expanded.value = v
  },
  { immediate: true },
)

function toggleExpanded() {
  expanded.value = !expanded.value
}

function selectPage(index: number) {
  pageIndex.value = index
}
</script>

<template>
  <div
    v-if="hasPages"
    class="source-image-panel"
    :class="{
      'source-image-panel--expanded': expanded || !collapsible,
      'source-image-panel--compact': compact,
      'source-image-panel--multi': multiPage,
    }"
  >
    <div class="source-image-panel-bar">
      <button
        v-if="collapsible"
        type="button"
        class="source-image-panel-toggle"
        :aria-expanded="expanded"
        @click="toggleExpanded"
      >
        <span class="source-image-panel-toggle-icon" aria-hidden="true">{{ expanded ? '▾' : '▸' }}</span>
        {{ expanded ? '收起原图' : '查看原图' }}
        <span v-if="multiPage" class="source-image-panel-count">（{{ pages.length }} 张 · 当前第 {{ pageIndex + 1 }} 张）</span>
      </button>
      <span v-else class="source-image-panel-label">扫描原图</span>

      <div v-if="multiPage" class="source-image-panel-tabs" role="tablist" aria-label="原图页码">
        <button
          v-for="(page, index) in pages"
          :key="`${page.path || ''}-${page.preview || ''}-${index}`"
          type="button"
          role="tab"
          class="source-image-panel-tab"
          :class="{ active: index === pageIndex }"
          :aria-selected="index === pageIndex"
          @click="selectPage(index)"
        >
          {{ page.label }}
        </button>
      </div>
    </div>

    <div v-if="expanded || !collapsible" class="source-image-panel-body">
      <SourceImageZoom :src="currentSrc" :alt="alt" :compact="compact" />
    </div>
  </div>
</template>
