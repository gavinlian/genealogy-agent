<script setup lang="ts">
import { computed, ref, watch, onMounted, onUnmounted } from 'vue'
import { resolveViewData } from '../../utils/genealogyViewData'
import { layoutRelationGraph } from '../../utils/relationGraphLayout'
import { buildFocusNeighborhood, isPersonFocused, isEdgeFocused } from '../../utils/focusNeighborhood'

const props = withDefaults(
  defineProps<{
    persons?: any[]
    relations?: any[]
    structuredText?: string
    rawText?: string
    title?: string
    selectedName?: string | null
    unbounded?: boolean
  }>(),
  {
    persons: () => [],
    relations: () => [],
    structuredText: '',
    rawText: '',
    title: '关系图',
    selectedName: null,
    unbounded: false,
  },
)

const emit = defineEmits<{ select: [name: string] }>()

const data = computed(() =>
  resolveViewData({
    persons: props.persons,
    relations: props.relations,
    structuredText: props.structuredText,
    rawText: props.rawText,
  }),
)

const layout = computed(() => layoutRelationGraph(data.value.persons, data.value.relations))

const focusNeighborhood = computed(() =>
  buildFocusNeighborhood(data.value.persons, data.value.relations, props.selectedName),
)
const hasFocus = computed(() => Boolean(props.selectedName))

function nodeFocused(id: string) {
  return isPersonFocused(id, focusNeighborhood.value, hasFocus.value)
}

function edgeFocused(fromId: string, toId: string, type: string) {
  return isEdgeFocused(fromId, toId, type, focusNeighborhood.value, hasFocus.value)
}

const MIN_SCALE = 0.35
const MAX_SCALE = 3
const viewportRef = ref<HTMLElement | null>(null)
const scale = ref(1)
const pan = ref({ x: 0, y: 0 })
const isPanning = ref(false)
const panStart = ref({ x: 0, y: 0, panX: 0, panY: 0 })
const dragNodeId = ref<string | null>(null)
const dragOffset = ref({ x: 0, y: 0 })
const nodePositions = ref<Record<string, { x: number; y: number }>>({})

function syncNodePositions() {
  const m: Record<string, { x: number; y: number }> = {}
  for (const n of layout.value.nodes) {
    m[n.id] = nodePositions.value[n.id] || { x: n.x, y: n.y }
  }
  nodePositions.value = m
}

watch(layout, () => syncNodePositions(), { immediate: true })

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
  const px = (clientX - rect.left - pan.value.x) / old
  const py = (clientY - rect.top - pan.value.y) / old
  scale.value = s
  pan.value = {
    x: clientX - rect.left - px * s,
    y: clientY - rect.top - py * s,
  }
}

function zoomIn() {
  const vp = viewportRef.value
  if (!vp) return
  const r = vp.getBoundingClientRect()
  zoomAt(r.left + r.width / 2, r.top + r.height / 2, scale.value + 0.15)
}

function zoomOut() {
  const vp = viewportRef.value
  if (!vp) return
  const r = vp.getBoundingClientRect()
  zoomAt(r.left + r.width / 2, r.top + r.height / 2, scale.value - 0.15)
}

function fitView() {
  scale.value = 1
  pan.value = { x: 0, y: 0 }
}

function onWheel(e: WheelEvent) {
  if (!e.ctrlKey && !e.metaKey) return
  zoomAt(e.clientX, e.clientY, scale.value + (e.deltaY > 0 ? -0.1 : 0.1))
}

function onPanStart(e: MouseEvent) {
  if (dragNodeId.value) return
  if (e.button !== 0) return
  isPanning.value = true
  panStart.value = { x: e.clientX, y: e.clientY, panX: pan.value.x, panY: pan.value.y }
}

function onPanMove(e: MouseEvent) {
  if (dragNodeId.value) {
    const pos = nodePositions.value[dragNodeId.value]
    if (pos) {
      const vp = viewportRef.value
      if (!vp) return
      const rect = vp.getBoundingClientRect()
      pos.x = (e.clientX - rect.left - pan.value.x) / scale.value - dragOffset.value.x
      pos.y = (e.clientY - rect.top - pan.value.y) / scale.value - dragOffset.value.y
    }
    return
  }
  if (!isPanning.value) return
  pan.value = {
    x: panStart.value.panX + (e.clientX - panStart.value.x),
    y: panStart.value.panY + (e.clientY - panStart.value.y),
  }
}

function onPanEnd() {
  isPanning.value = false
  dragNodeId.value = null
}

function onNodeDown(e: MouseEvent, nodeId: string) {
  e.stopPropagation()
  syncNodePositions()
  const pos = nodePositions.value[nodeId]
  const vp = viewportRef.value
  if (!pos || !vp) return
  const rect = vp.getBoundingClientRect()
  dragNodeId.value = nodeId
  dragOffset.value = {
    x: (e.clientX - rect.left - pan.value.x) / scale.value - pos.x,
    y: (e.clientY - rect.top - pan.value.y) / scale.value - pos.y,
  }
}

function nodePos(id: string, fallback: { x: number; y: number }) {
  return nodePositions.value[id] || fallback
}

const edgeLines = computed(() =>
  layout.value.edges.map((e) => {
    const a = nodePos(e.fromId, { x: e.x1, y: e.y1 })
    const b = nodePos(e.toId, { x: e.x2, y: e.y2 })
    return { ...e, x1: a.x, y1: a.y, x2: b.x, y2: b.y }
  }),
)

onMounted(() => window.addEventListener('mouseup', onPanEnd))
onUnmounted(() => window.removeEventListener('mouseup', onPanEnd))
</script>

<template>
  <div class="relation-graph-view" role="region" aria-label="人物关系图">
    <header class="relation-graph-header">
      <h3 class="relation-graph-title">{{ title }}</h3>
      <span v-if="data.persons.length" class="relation-graph-meta">
        {{ data.persons.length }} 人 · {{ layout.edges.length }} 条关系
      </span>
      <div class="relation-graph-toolbar">
        <button type="button" class="btn-xs" @click="zoomOut">−</button>
        <span class="relation-graph-scale">{{ Math.round(scale * 100) }}%</span>
        <button type="button" class="btn-xs" @click="zoomIn">+</button>
        <button type="button" class="btn-xs" @click="fitView">适应</button>
      </div>
    </header>

    <div v-if="!data.persons.length" class="zupu-view-empty">
      暂无成员。整理人物关系后，可在此以关系图浏览（可拖拽节点、Ctrl+滚轮缩放）
    </div>

    <div
      v-else
      ref="viewportRef"
      class="relation-graph-viewport"
      :class="{ panning: isPanning, 'relation-graph-viewport--unbounded': unbounded, 'relation-graph-viewport--focus': hasFocus }"
      @wheel.prevent="onWheel"
      @mousedown="onPanStart"
      @mousemove="onPanMove"
      @mouseup="onPanEnd"
      @mouseleave="onPanEnd"
    >
      <div
        class="relation-graph-inner"
        :style="{
          width: layout.width + 'px',
          height: layout.height + 'px',
          transform: `translate(${pan.x}px, ${pan.y}px) scale(${scale})`,
        }"
      >
        <svg class="relation-graph-edges" :width="layout.width" :height="layout.height">
          <line
            v-for="(e, i) in edgeLines"
            :key="'ge' + i"
            :x1="e.x1"
            :y1="e.y1"
            :x2="e.x2"
            :y2="e.y2"
            :class="[
              'relation-graph-edge relation-graph-edge--' + (e.type === 'spouse' ? 'spouse' : 'parent'),
              { 'relation-graph-edge--dimmed': hasFocus && !edgeFocused(e.fromId, e.toId, e.type) },
              { 'relation-graph-edge--focused': hasFocus && edgeFocused(e.fromId, e.toId, e.type) },
            ]"
          />
        </svg>
        <button
          v-for="n in layout.nodes"
          :key="n.id"
          type="button"
          class="relation-graph-node"
          :class="[
            'relation-graph-node--' + n.gender,
            {
              'relation-graph-node--selected': selectedName === n.name,
              'relation-graph-node--dimmed': hasFocus && !nodeFocused(n.id),
              'relation-graph-node--focused': hasFocus && nodeFocused(n.id),
            },
          ]"
          :style="{
            left: (nodePos(n.id, n).x - n.r) + 'px',
            top: (nodePos(n.id, n).y - n.r) + 'px',
            width: n.r * 2 + 'px',
            height: n.r * 2 + 'px',
          }"
          @mousedown="onNodeDown($event, n.id)"
          @click.stop="emit('select', n.name)"
        >
          <span class="relation-graph-node-label">{{ n.name }}</span>
        </button>
      </div>
    </div>
    <p class="relation-graph-hint">点选成员高亮父母/子女/配偶/兄弟姐妹 · 拖节点 · Ctrl+滚轮缩放</p>
  </div>
</template>
