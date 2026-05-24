<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted, nextTick } from 'vue'
import { api } from '../utils/api'

const props = withDefaults(defineProps<{
  familyId: string
  selectedPersonId?: string | null
  pulsePersonId?: string | null
  treeStyle?: 'silkworm' | 'su' | 'eu' | 'tower' | 'radial'
}>(), {
  selectedPersonId: null,
  pulsePersonId: null,
  treeStyle: 'silkworm',
})

const emit = defineEmits<{
  select: [id: string]
}>()

const SILKWORM_LABEL_COL = 88
const MIN_TREE_ZOOM = 5
const MAX_TREE_ZOOM = 250

const treeNodes = ref<any[]>([])
const relations = ref<any[]>([])
const treeZoom = ref(100)
const treePan = ref({ x: 0, y: 0 })
const treeBounds = ref({ width: 880, height: 640 })
const treeViewport = ref<HTMLElement | null>(null)
const isPanning = ref(false)
const panStart = ref({ x: 0, y: 0, panX: 0, panY: 0 })
const touchCanvas = ref({
  mode: 'none' as 'none' | 'pan' | 'pinch',
  startX: 0,
  startY: 0,
  panX: 0,
  panY: 0,
  pinchDist: 0,
  pinchZoom: 100,
})
const loading = ref(false)
let resizeObserver: ResizeObserver | null = null

const isAbsoluteTreeLayout = computed(() =>
  props.treeStyle === 'silkworm' || props.treeStyle === 'radial',
)

const treeDisplayWidth = computed(() => {
  const base = treeBounds.value.width || 880
  return props.treeStyle === 'silkworm' ? base + SILKWORM_LABEL_COL : base
})

const maxGeneration = computed(() => {
  if (!treeNodes.value.length) return 0
  return Math.max(...treeNodes.value.map((p) => p.generation || 0))
})

const treeCompact = computed(() => maxGeneration.value >= 15 || treeNodes.value.length > 60)

const treeNodeById = computed(() => {
  const map = new Map<string, any>()
  for (const n of treeNodes.value) map.set(n.id, n)
  return map
})

const silkwormGenerationRows = computed(() => {
  if (props.treeStyle !== 'silkworm' || !treeNodes.value.length) return []
  const byGen = new Map<number, any[]>()
  for (const n of treeNodes.value) {
    const g = Number(n.generation) || 1
    if (!byGen.has(g)) byGen.set(g, [])
    byGen.get(g)!.push(n)
  }
  const rows: { generation: number; top: number; height: number; count: number; even: boolean }[] = []
  let idx = 0
  for (const g of [...byGen.keys()].sort((a, b) => a - b)) {
    const nodes = byGen.get(g)!
    const first = nodes.reduce((a, b) =>
      ((a.layout?.offset_y ?? 0) < (b.layout?.offset_y ?? 0) ? a : b),
    )
    const rowY = first.layout?.offset_y ?? 0
    const rowH = Math.max(
      first.layout?.node_height || 72,
      ...nodes.map((n) => n.layout?.node_height || 72),
    )
    rows.push({ generation: g, top: rowY, height: rowH + 16, count: nodes.length, even: idx % 2 === 0 })
    idx += 1
  }
  return rows
})

const treeEdges = computed(() => {
  if (!isAbsoluteTreeLayout.value) return []
  const labelOffset = props.treeStyle === 'silkworm' ? SILKWORM_LABEL_COL : 0
  const edges: { x1: number; y1: number; x2: number; y2: number; type: string }[] = []
  for (const r of relations.value) {
    if (r.relation_type !== 'parent_child' && r.relation_type !== 'spouse') continue
    const from = treeNodeById.value.get(r.from_person_id)
    const to = treeNodeById.value.get(r.to_person_id)
    if (!from?.layout || !to?.layout) continue
    const fw = from.layout.node_width || 128
    const fh = from.layout.node_height || 56
    const tw = to.layout.node_width || 128
    edges.push({
      x1: labelOffset + from.layout.offset_x + fw / 2,
      y1: from.layout.offset_y + fh,
      x2: labelOffset + to.layout.offset_x + tw / 2,
      y2: to.layout.offset_y,
      type: r.relation_type,
    })
  }
  return edges
})

const treeViewSizeStyle = computed(() => {
  if (!isAbsoluteTreeLayout.value) return {}
  return {
    width: `${treeDisplayWidth.value}px`,
    height: `${treeBounds.value.height}px`,
  }
})

function clampTreeZoom(v: number) {
  return Math.min(MAX_TREE_ZOOM, Math.max(MIN_TREE_ZOOM, v))
}

function zoomAtPoint(clientX: number, clientY: number, nextZoom: number) {
  const vp = treeViewport.value
  const z = clampTreeZoom(nextZoom)
  if (!vp) {
    treeZoom.value = z
    return
  }
  const rect = vp.getBoundingClientRect()
  const oldScale = treeZoom.value / 100
  const newScale = z / 100
  const px = (clientX - rect.left - treePan.value.x) / oldScale
  const py = (clientY - rect.top - treePan.value.y) / oldScale
  treeZoom.value = z
  treePan.value = {
    x: clientX - rect.left - px * newScale,
    y: clientY - rect.top - py * newScale,
  }
}

function computeTreeBoundsLocal() {
  let maxX = 0
  let maxY = 0
  for (const p of treeNodes.value) {
    const l = p.layout || {}
    const w = l.node_width || 128
    const h = l.node_height || 72
    maxX = Math.max(maxX, (l.offset_x || 0) + w)
    maxY = Math.max(maxY, (l.offset_y || 0) + h)
  }
  treeBounds.value = {
    width: Math.max(maxX + 64 + (props.treeStyle === 'silkworm' ? SILKWORM_LABEL_COL : 0), 480),
    height: Math.max(maxY + 64, 360),
  }
}

function fitTreeToView() {
  const vp = treeViewport.value
  if (!vp || !treeNodes.value.length) return
  const vw = Math.max(vp.clientWidth, 120)
  const vh = Math.max(vp.clientHeight, 120)
  const pad = 24
  const bw = treeBounds.value.width || 880
  const bh = treeBounds.value.height || 640
  const scalePct = clampTreeZoom(Math.floor(Math.min(vw / bw, vh / bh) * 100))
  treeZoom.value = scalePct
  const sw = bw * (scalePct / 100)
  const sh = bh * (scalePct / 100)
  treePan.value = {
    x: pad + Math.max(0, (vw - sw) / 2),
    y: pad + Math.max(0, (vh - sh) / 2),
  }
}

function treeNodeStyle(p: any) {
  const layout = p.layout || {}
  const nodeW = layout.node_width || (treeCompact.value ? 96 : 128)
  const labelOffset = props.treeStyle === 'silkworm' ? SILKWORM_LABEL_COL : 0
  if (props.treeStyle === 'silkworm' || props.treeStyle === 'radial') {
    return {
      position: 'absolute',
      left: (layout.offset_x || 0) + labelOffset + 'px',
      top: (layout.offset_y || 0) + 'px',
      width: nodeW + 'px',
    }
  }
  return { marginLeft: ((layout.offset_x || 0) + (p.depth || 0) * 24) + 'px', marginTop: '6px' }
}

function zoomIn() {
  const vp = treeViewport.value
  if (!vp) {
    treeZoom.value = clampTreeZoom(treeZoom.value + 10)
    return
  }
  const rect = vp.getBoundingClientRect()
  zoomAtPoint(rect.left + rect.width / 2, rect.top + rect.height / 2, treeZoom.value + 10)
}

function zoomOut() {
  const vp = treeViewport.value
  if (!vp) {
    treeZoom.value = clampTreeZoom(treeZoom.value - 10)
    return
  }
  const rect = vp.getBoundingClientRect()
  zoomAtPoint(rect.left + rect.width / 2, rect.top + rect.height / 2, treeZoom.value - 10)
}

function onTreeWheel(e: WheelEvent) {
  const delta = e.deltaY > 0 ? -8 : 8
  zoomAtPoint(e.clientX, e.clientY, treeZoom.value + delta)
}

function onCanvasPanStart(e: MouseEvent) {
  if ((e.target as HTMLElement).closest('.tree-node-card')) return
  isPanning.value = true
  panStart.value = { x: e.clientX, y: e.clientY, panX: treePan.value.x, panY: treePan.value.y }
  window.addEventListener('mousemove', onCanvasPanMove)
  window.addEventListener('mouseup', onCanvasPanEnd)
}

function onCanvasPanMove(e: MouseEvent) {
  if (!isPanning.value) return
  treePan.value = {
    x: panStart.value.panX + (e.clientX - panStart.value.x),
    y: panStart.value.panY + (e.clientY - panStart.value.y),
  }
}

function onCanvasPanEnd() {
  isPanning.value = false
  window.removeEventListener('mousemove', onCanvasPanMove)
  window.removeEventListener('mouseup', onCanvasPanEnd)
}

function touchPinchDistance(touches: TouchList) {
  const dx = touches[0].clientX - touches[1].clientX
  const dy = touches[0].clientY - touches[1].clientY
  return Math.hypot(dx, dy)
}

function touchMidpoint(touches: TouchList) {
  return {
    x: (touches[0].clientX + touches[1].clientX) / 2,
    y: (touches[0].clientY + touches[1].clientY) / 2,
  }
}

function resetTouchCanvas() {
  touchCanvas.value = {
    mode: 'none',
    startX: 0,
    startY: 0,
    panX: 0,
    panY: 0,
    pinchDist: 0,
    pinchZoom: treeZoom.value,
  }
  isPanning.value = false
}

function onCanvasTouchStart(e: TouchEvent) {
  if ((e.target as HTMLElement).closest('.tree-node-card')) return
  if (e.touches.length === 1) {
    touchCanvas.value = {
      mode: 'pan',
      startX: e.touches[0].clientX,
      startY: e.touches[0].clientY,
      panX: treePan.value.x,
      panY: treePan.value.y,
      pinchDist: 0,
      pinchZoom: treeZoom.value,
    }
    isPanning.value = true
  } else if (e.touches.length === 2) {
    touchCanvas.value = {
      mode: 'pinch',
      startX: 0,
      startY: 0,
      panX: treePan.value.x,
      panY: treePan.value.y,
      pinchDist: touchPinchDistance(e.touches),
      pinchZoom: treeZoom.value,
    }
    isPanning.value = false
  }
}

function onCanvasTouchMove(e: TouchEvent) {
  const ts = touchCanvas.value
  if (ts.mode === 'pan' && e.touches.length === 1) {
    e.preventDefault()
    treePan.value = {
      x: ts.panX + (e.touches[0].clientX - ts.startX),
      y: ts.panY + (e.touches[0].clientY - ts.startY),
    }
    return
  }
  if (ts.mode === 'pinch' && e.touches.length === 2 && ts.pinchDist > 0) {
    e.preventDefault()
    const dist = touchPinchDistance(e.touches)
    const mid = touchMidpoint(e.touches)
    zoomAtPoint(mid.x, mid.y, ts.pinchZoom * (dist / ts.pinchDist))
  }
}

function onCanvasTouchEnd(e: TouchEvent) {
  if (e.touches.length === 0) {
    resetTouchCanvas()
    return
  }
  if (e.touches.length === 1 && touchCanvas.value.mode === 'pinch') {
    touchCanvas.value = {
      mode: 'pan',
      startX: e.touches[0].clientX,
      startY: e.touches[0].clientY,
      panX: treePan.value.x,
      panY: treePan.value.y,
      pinchDist: 0,
      pinchZoom: treeZoom.value,
    }
    isPanning.value = true
  }
}

function onNodeClick(p: any) {
  emit('select', p.id)
}

async function reload() {
  if (!props.familyId) return
  loading.value = true
  try {
    const [treeRes, relRes] = await Promise.all([
      api('GET', `/families/${props.familyId}/tree?style=${props.treeStyle}`),
      api('GET', `/families/${props.familyId}/relations`),
    ])
    treeNodes.value = treeRes.nodes || []
    relations.value = Array.isArray(relRes) ? relRes : relRes.relations || []
    if (treeRes.bounds?.width && treeRes.bounds?.height) {
      treeBounds.value = treeRes.bounds
    } else {
      computeTreeBoundsLocal()
    }
    await nextTick()
    fitTreeToView()
  } finally {
    loading.value = false
  }
}

watch(() => props.familyId, () => reload(), { immediate: true })

onMounted(() => {
  if (treeViewport.value && typeof ResizeObserver !== 'undefined') {
    resizeObserver = new ResizeObserver(() => {
      if (treeNodes.value.length) fitTreeToView()
    })
    resizeObserver.observe(treeViewport.value)
  }
})

onUnmounted(() => {
  window.removeEventListener('mousemove', onCanvasPanMove)
  window.removeEventListener('mouseup', onCanvasPanEnd)
  resizeObserver?.disconnect()
})

defineExpose({ reload, fitTreeToView })
</script>

<template>
  <div class="genealogy-tree-canvas">
    <div v-if="loading && !treeNodes.length" class="genealogy-tree-loading">加载树图…</div>
    <div v-else-if="!treeNodes.length" class="empty-state compact">
      <p>暂无成员。在对话里说「扫描建谱」，或添加第一位祖先。</p>
    </div>
    <template v-else>
      <div
        ref="treeViewport"
        class="tree-canvas-viewport genealogy-tree-viewport"
        :class="{ panning: isPanning }"
        @wheel.prevent="onTreeWheel"
        @mousedown="onCanvasPanStart"
        @touchstart="onCanvasTouchStart"
        @touchmove="onCanvasTouchMove"
        @touchend="onCanvasTouchEnd"
        @touchcancel="onCanvasTouchEnd"
      >
        <div
          class="tree-canvas-inner"
          :style="{ transform: `translate(${treePan.x}px, ${treePan.y}px) scale(${treeZoom / 100})` }"
        >
          <div
            class="tree-view"
            :class="[
              'tree-' + treeStyle,
              { 'tree-layout-absolute': isAbsoluteTreeLayout, 'tree-compact': treeCompact, 'tree-silkworm-labeled': treeStyle === 'silkworm' },
            ]"
            :style="treeViewSizeStyle"
          >
            <template v-if="treeStyle === 'silkworm'">
              <div
                v-for="row in silkwormGenerationRows"
                :key="'band-' + row.generation"
                class="tree-gen-row-band"
                :class="{ 'tree-gen-row-band--alt': row.even }"
                :style="{ top: (row.top - 6) + 'px', height: row.height + 'px' }"
              />
              <div
                v-for="row in silkwormGenerationRows"
                :key="'label-' + row.generation"
                class="tree-gen-row-label"
                :style="{ top: row.top + 'px', height: row.height + 'px' }"
              >
                <span class="tree-gen-row-title">第{{ row.generation }}世</span>
                <span class="tree-gen-row-count">{{ row.count }}人</span>
              </div>
            </template>
            <svg
              v-if="isAbsoluteTreeLayout && treeEdges.length"
              class="tree-edges-layer"
              :width="treeDisplayWidth"
              :height="treeBounds.height"
            >
              <line
                v-for="(e, i) in treeEdges"
                :key="'edge' + i"
                :x1="e.x1"
                :y1="e.y1"
                :x2="e.x2"
                :y2="e.y2"
                :class="e.type === 'spouse' ? 'tree-edge-spouse' : 'tree-edge-parent'"
              />
            </svg>
            <div
              v-for="p in treeNodes"
              :key="p.id"
              class="tree-node"
              :style="treeNodeStyle(p)"
              @click.stop="onNodeClick(p)"
            >
              <div
                class="tree-node-card"
                :class="[
                  'gender-' + (p.gender || 'unknown'),
                  {
                    'tree-node-selected': selectedPersonId === p.id,
                    'tree-node--pulse': p.id === pulsePersonId,
                    'is-placeholder': p.is_placeholder,
                  },
                ]"
              >
                <div class="node-content">
                  <span class="node-name">{{ p.name }}</span>
                  <span v-if="p.birth_year" class="node-years">
                    {{ p.birth_year }}<span v-if="p.death_year">–{{ p.death_year }}</span>
                  </span>
                  <span v-if="p.generation" class="node-gen">第{{ p.generation }}代</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
      <p class="canvas-touch-hint">单指拖动 · 双指缩放</p>
      <div class="canvas-touch-controls">
        <button type="button" class="canvas-touch-btn" aria-label="放大" @click="zoomIn">+</button>
        <button type="button" class="canvas-touch-btn canvas-touch-btn--fit" aria-label="适应屏幕" @click="fitTreeToView">⊡</button>
        <button type="button" class="canvas-touch-btn" aria-label="缩小" @click="zoomOut">−</button>
      </div>
    </template>
  </div>
</template>
