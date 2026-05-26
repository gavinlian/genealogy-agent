<script setup lang="ts">
import { ref, onMounted, onUnmounted, nextTick } from 'vue'
import GenealogyReferenceView, { type ReferenceViewMode } from './GenealogyReferenceView.vue'

const props = withDefaults(
  defineProps<{
    mode?: ReferenceViewMode
    persons?: any[]
    relations?: any[]
    title?: string
    selectedPersonId?: string | null
    structuredText?: string
  }>(),
  {
    mode: 'page',
    persons: () => [],
    relations: () => [],
    title: '族谱',
    selectedPersonId: null,
    structuredText: '',
  },
)

const emit = defineEmits<{ select: [personId: string] }>()

const MIN_SCALE = 0.45
const MAX_SCALE = 2.2

const viewportRef = ref<HTMLElement | null>(null)
const scale = ref(1)
const pan = ref({ x: 0, y: 0 })
const isPanning = ref(false)
const panStart = ref({ x: 0, y: 0, panX: 0, panY: 0 })
const touchState = ref({
  mode: 'none' as 'none' | 'pan' | 'pinch',
  startX: 0,
  startY: 0,
  panX: 0,
  panY: 0,
  pinchDist: 0,
  pinchScale: 1,
})

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
    scale.value = clampScale(scale.value + 0.12)
    return
  }
  const rect = vp.getBoundingClientRect()
  zoomAt(rect.left + rect.width / 2, rect.top + rect.height / 2, scale.value + 0.12)
}

function zoomOut() {
  const vp = viewportRef.value
  if (!vp) {
    scale.value = clampScale(scale.value - 0.12)
    return
  }
  const rect = vp.getBoundingClientRect()
  zoomAt(rect.left + rect.width / 2, rect.top + rect.height / 2, scale.value - 0.12)
}

function zoomReset() {
  scale.value = 1
  pan.value = { x: 0, y: 0 }
}

function fitView() {
  scale.value = 1
  pan.value = { x: 0, y: 0 }
  nextTick(() => viewportRef.value?.scrollTo({ left: 0, top: 0, behavior: 'smooth' }))
}

function onWheel(e: WheelEvent) {
  if (!e.ctrlKey && !e.metaKey) return
  const delta = e.deltaY > 0 ? -0.1 : 0.1
  zoomAt(e.clientX, e.clientY, scale.value + delta)
}

function onPanStart(e: MouseEvent) {
  if (e.button !== 0) return
  const t = e.target as HTMLElement
  if (t.closest('.zupu-person-card, .zupu-page-name-node, button, a, input, textarea, select')) return
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

function touchDist(a: Touch, b: Touch) {
  const dx = a.clientX - b.clientX
  const dy = a.clientY - b.clientY
  return Math.hypot(dx, dy)
}

function onTouchStart(e: TouchEvent) {
  if (e.touches.length === 1) {
    touchState.value = {
      mode: 'pan',
      startX: e.touches[0].clientX,
      startY: e.touches[0].clientY,
      panX: pan.value.x,
      panY: pan.value.y,
      pinchDist: 0,
      pinchScale: scale.value,
    }
  } else if (e.touches.length === 2) {
    touchState.value = {
      mode: 'pinch',
      startX: 0,
      startY: 0,
      panX: pan.value.x,
      panY: pan.value.y,
      pinchDist: touchDist(e.touches[0], e.touches[1]),
      pinchScale: scale.value,
    }
  }
}

function onTouchMove(e: TouchEvent) {
  const ts = touchState.value
  if (ts.mode === 'pan' && e.touches.length === 1) {
    pan.value = {
      x: ts.panX + (e.touches[0].clientX - ts.startX),
      y: ts.panY + (e.touches[0].clientY - ts.startY),
    }
  } else if (ts.mode === 'pinch' && e.touches.length === 2) {
    e.preventDefault()
    const dist = touchDist(e.touches[0], e.touches[1])
    const midX = (e.touches[0].clientX + e.touches[1].clientX) / 2
    const midY = (e.touches[0].clientY + e.touches[1].clientY) / 2
    zoomAt(midX, midY, ts.pinchScale * (dist / (ts.pinchDist || dist)))
  }
}

function onTouchEnd() {
  touchState.value.mode = 'none'
}

onMounted(() => {
  window.addEventListener('mouseup', onPanEnd)
})
onUnmounted(() => {
  window.removeEventListener('mouseup', onPanEnd)
})

defineExpose({
  zoomIn,
  zoomOut,
  zoomReset,
  fitView,
  scale,
})
</script>

<template>
  <div
    ref="viewportRef"
    class="ref-zoom-viewport"
    :class="{ panning: isPanning }"
    @wheel.prevent="onWheel"
    @mousedown="onPanStart"
    @mousemove="onPanMove"
    @mouseup="onPanEnd"
    @mouseleave="onPanEnd"
    @touchstart.passive="onTouchStart"
    @touchmove="onTouchMove"
    @touchend="onTouchEnd"
    @touchcancel="onTouchEnd"
  >
    <div
      class="ref-zoom-inner"
      :style="{
        transform: `translate(${pan.x}px, ${pan.y}px) scale(${scale})`,
      }"
    >
      <GenealogyReferenceView
        :mode="mode"
        :persons="persons"
        :relations="relations"
        :structured-text="structuredText"
        :title="title"
        :selected-person-id="selectedPersonId"
        :fill="false"
        unbounded
        @select="emit('select', $event)"
      />
    </div>
    <p class="ref-zoom-hint">滚轮 + Ctrl 缩放 · 拖动画布 · 或点工具栏 ±</p>
  </div>
</template>
