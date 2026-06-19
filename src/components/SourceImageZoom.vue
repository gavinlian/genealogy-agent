<script setup lang="ts">
import { ref, watch, onMounted, onUnmounted, nextTick } from 'vue'

const props = withDefaults(
  defineProps<{
    src?: string
    alt?: string
    /** 紧凑模式：降低默认视口高度，适合嵌入对照区 */
    compact?: boolean
  }>(),
  {
    src: '',
    alt: '扫描原图',
    compact: false,
  },
)

const MIN_SCALE = 0.35
const MAX_SCALE = 4

const imageLoadFailed = ref(false)
const viewportRef = ref<HTMLElement | null>(null)
const imgRef = ref<HTMLImageElement | null>(null)
const scale = ref(1)
const pan = ref({ x: 0, y: 0 })
const isPanning = ref(false)
const panStart = ref({ x: 0, y: 0, panX: 0, panY: 0 })

function clampScale(v: number) {
  return Math.min(MAX_SCALE, Math.max(MIN_SCALE, v))
}

function zoomAt(clientX: number, clientY: number, next: number) {
  const vp = viewportRef.value
  const s = clampScale(next)
  if (!vp) {
    scale.value = s
    return
  }
  const rect = vp.getBoundingClientRect()
  const old = scale.value
  const px = (clientX - rect.left - pan.value.x + vp.scrollLeft) / old
  const py = (clientY - rect.top - pan.value.y + vp.scrollTop) / old
  scale.value = s
  pan.value = {
    x: clientX - rect.left - px * s + vp.scrollLeft,
    y: clientY - rect.top - py * s + vp.scrollTop,
  }
}

function zoomIn() {
  const vp = viewportRef.value
  if (!vp) {
    scale.value = clampScale(scale.value + 0.15)
    return
  }
  const r = vp.getBoundingClientRect()
  zoomAt(r.left + r.width / 2, r.top + r.height / 2, scale.value + 0.15)
}

function zoomOut() {
  const vp = viewportRef.value
  if (!vp) {
    scale.value = clampScale(scale.value - 0.15)
    return
  }
  const r = vp.getBoundingClientRect()
  zoomAt(r.left + r.width / 2, r.top + r.height / 2, scale.value - 0.15)
}

function zoomReset() {
  scale.value = 1
  pan.value = { x: 0, y: 0 }
}

function fitView() {
  fitImageToViewport()
  viewportRef.value?.scrollTo({ left: 0, top: 0, behavior: 'smooth' })
}

/** 优先按可视区宽度放大原图，便于竖排族谱对照 */
function fitImageToViewport() {
  const vp = viewportRef.value
  const img = imgRef.value
  if (!vp || !img?.naturalWidth) return
  const pad = 12
  const vpW = Math.max(vp.clientWidth - pad * 2, 240)
  const scaleW = vpW / img.naturalWidth
  const s = clampScale(scaleW)
  scale.value = s
  pan.value = { x: pad, y: pad }
}

let resizeObserver: ResizeObserver | null = null

function attachResizeObserver() {
  if (resizeObserver || !viewportRef.value || typeof ResizeObserver === 'undefined') return
  resizeObserver = new ResizeObserver(() => {
    if (props.src && imgRef.value?.complete) fitImageToViewport()
  })
  resizeObserver.observe(viewportRef.value)
}

watch(
  () => props.src,
  async () => {
    scale.value = 1
    pan.value = { x: 0, y: 0 }
    await nextTick()
    attachResizeObserver()
    fitImageToViewport()
  },
  { immediate: true },
)

function onWheel(e: WheelEvent) {
  if (!e.ctrlKey && !e.metaKey) return
  const delta = e.deltaY > 0 ? -0.12 : 0.12
  zoomAt(e.clientX, e.clientY, scale.value + delta)
}

function onPanStart(e: MouseEvent) {
  if (e.button !== 0) return
  isPanning.value = true
  panStart.value = { x: e.clientX, y: e.clientY, panX: pan.value.x, panY: pan.value.y }
}

function onPanMove(e: MouseEvent) {
  if (!isPanning.value) return
  pan.value = {
    x: panStart.value.panX + (e.clientX - panStart.value.x),
    y: panStart.value.panY + (e.clientY - panStart.value.y),
  }
}

function onPanEnd() {
  isPanning.value = false
}

onMounted(() => {
  window.addEventListener('mouseup', onPanEnd)
})
onUnmounted(() => {
  window.removeEventListener('mouseup', onPanEnd)
  resizeObserver?.disconnect()
})

watch(
  () => props.src,
  () => {
    imageLoadFailed.value = false
  },
)

function onImageLoad() {
  imageLoadFailed.value = false
  attachResizeObserver()
  fitImageToViewport()
}

function onImageError() {
  imageLoadFailed.value = true
}

defineExpose({ zoomIn, zoomOut, zoomReset, fitView, scale })
</script>

<template>
  <div class="source-image-zoom" :class="{ 'source-image-zoom--compact': compact }">
    <div class="source-image-zoom-toolbar">
      <span class="source-image-zoom-label">扫描原图</span>
      <span class="source-image-zoom-scale">{{ Math.round(scale * 100) }}%</span>
      <button type="button" class="btn-xs" title="缩小" @click="zoomOut">−</button>
      <button type="button" class="btn-xs" title="放大" @click="zoomIn">+</button>
      <button type="button" class="btn-xs" @click="fitView">适应</button>
      <button type="button" class="btn-xs" @click="zoomReset">100%</button>
    </div>
    <div
      v-if="!src"
      class="source-image-zoom-empty"
    >
      暂无对照原图。扫描入库或上传图片后，可与版本一 OCR 原文左右对照修改。
    </div>
    <div
      v-else-if="imageLoadFailed"
      class="source-image-zoom-empty source-image-zoom-empty--error"
    >
      原图文件无法加载（可能未保存到族谱或已被删除）。请点「添加原图」重新上传，或重新扫描识别。
    </div>
    <div
      v-else
      ref="viewportRef"
      class="source-image-zoom-viewport"
      :class="{ panning: isPanning }"
      @wheel.prevent="onWheel"
      @mousedown="onPanStart"
      @mousemove="onPanMove"
      @mouseup="onPanEnd"
      @mouseleave="onPanEnd"
    >
      <div
        class="source-image-zoom-inner"
        :style="{ transform: `translate(${pan.x}px, ${pan.y}px) scale(${scale})` }"
      >
        <img ref="imgRef" :src="src" :alt="alt" draggable="false" @load="onImageLoad" @error="onImageError" />
      </div>
    </div>
    <p class="source-image-zoom-hint">Ctrl+滚轮缩放 · 拖动画布</p>
  </div>
</template>
