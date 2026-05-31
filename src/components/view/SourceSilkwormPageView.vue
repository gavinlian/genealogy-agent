<script setup lang="ts">
import { computed } from 'vue'
import { resolveViewData } from '../../utils/genealogyViewData'
import { layoutSilkwormPage, NODE_W, NODE_H, GUTTER_W, PAD, ROW_H } from '../../utils/silkwormPageLayout'
import { buildFocusNeighborhood, isPersonFocused } from '../../utils/focusNeighborhood'

const props = withDefaults(defineProps<{
  persons?: any[]
  relations?: any[]
  structuredText?: string
  rawText?: string
  imagePreview?: string
  title?: string
  selectedName?: string | null
  unbounded?: boolean
}>(), {
  persons: () => [],
  relations: () => [],
  structuredText: '',
  rawText: '',
  imagePreview: '',
  title: '世系谱页',
  selectedName: null,
  unbounded: false,
})

const emit = defineEmits<{ select: [name: string] }>()

const data = computed(() =>
  resolveViewData({
    persons: props.persons,
    relations: props.relations,
    structuredText: props.structuredText,
    rawText: props.rawText,
  }),
)

const layout = computed(() => layoutSilkwormPage(data.value.persons, data.value.relations))

const hasTreeRelations = computed(() =>
  data.value.relations.some((r) => r.type === 'parent_child'),
)

const focusNeighborhood = computed(() =>
  buildFocusNeighborhood(data.value.persons, data.value.relations, props.selectedName),
)
const hasFocus = computed(() => Boolean(props.selectedName))

function personFocused(id: string) {
  return isPersonFocused(id, focusNeighborhood.value, hasFocus.value)
}

function genTop(gen: number) {
  const min = layout.value.generations[0] ?? gen
  return PAD + (gen - min) * ROW_H + 4
}
</script>

<template>
  <div class="zupu-page-view" role="region" aria-label="谱页世系">
    <div v-if="imagePreview" class="zupu-page-view-scan">
      <img :src="imagePreview" alt="扫描原图" />
    </div>

    <div class="zupu-page-view-frame">
      <header class="zupu-page-view-header">
        <span class="zupu-page-view-title">{{ title }}</span>
        <span v-if="data.persons.length" class="zupu-page-view-meta">
          {{ data.persons.length }} 人
          <template v-if="data.relations.length"> · {{ data.relations.length }} 关系</template>
          <template v-if="!hasTreeRelations"> · 按世代平铺</template>
        </span>
      </header>

      <div v-if="!data.persons.length" class="zupu-view-empty">
        暂无世系内容。版本二关系描述或解析完成后，将按旧谱样式展示（参考族谱 App · 谱页模式）
      </div>

      <div v-else class="zupu-page-view-scroll" :class="{ 'zupu-page-view-scroll--unbounded': unbounded, 'zupu-page-view-scroll--focus': hasFocus }">
        <div
          class="zupu-page-view-canvas-wrap"
          :style="{ minWidth: layout.width + 'px', minHeight: layout.height + 'px' }"
        >
          <svg class="zupu-page-edges" :width="layout.width" :height="layout.height">
            <line
              v-for="(e, i) in layout.edges"
              :key="'pe' + i"
              :x1="e.x1"
              :y1="e.y1"
              :x2="e.x2"
              :y2="e.y2"
              class="zupu-page-edge"
            />
            <circle
              v-for="(n, i) in layout.nodes"
              :key="'dot' + i"
              :cx="n.cx"
              :cy="n.y + 2"
              r="3"
              class="zupu-page-node-dot"
            />
          </svg>

          <aside class="zupu-page-gutter" :style="{ width: GUTTER_W + 'px' }">
            <span class="zupu-page-gutter-title">世系</span>
            <span
              v-for="gen in layout.generations"
              :key="'badge-' + gen"
              class="zupu-page-gen-badge"
              :style="{ top: genTop(gen) + 'px' }"
            >{{ gen }}世</span>
          </aside>

          <div class="zupu-page-nodes">
            <div
              v-for="n in layout.nodes"
              :key="n.person.id"
              class="zupu-page-name-node"
              :class="[
                'zupu-page-name-node--' + n.person.gender,
                {
                  'zupu-page-name-node--selected': selectedName === n.person.name,
                  'zupu-page-name-node--dimmed': hasFocus && !personFocused(n.person.id),
                  'zupu-page-name-node--focused': hasFocus && personFocused(n.person.id),
                },
              ]"
              :style="{ left: n.x + 'px', top: n.y + 'px', width: NODE_W + 'px', minHeight: NODE_H + 'px' }"
              role="button"
              tabindex="0"
              @click="emit('select', n.person.name)"
              @keydown.enter="emit('select', n.person.name)"
            >
              <span class="zupu-page-name-vertical">{{ n.person.name }}</span>
            </div>
          </div>
        </div>
      </div>

      <footer class="zupu-page-view-footer">
        <span class="zupu-page-footer-hint">左右滑动查看支脉</span>
      </footer>
    </div>
  </div>
</template>
