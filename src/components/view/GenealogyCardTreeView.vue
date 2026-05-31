<script setup lang="ts">
import { computed } from 'vue'
import { resolveViewData } from '../../utils/genealogyViewData'
import { layoutCardTree, CARD_W, CARD_H, SIDEBAR_W } from '../../utils/cardTreeLayout'
import { buildFocusNeighborhood, isPersonFocused } from '../../utils/focusNeighborhood'

const props = withDefaults(defineProps<{
  persons?: any[]
  relations?: any[]
  structuredText?: string
  rawText?: string
  title?: string
  selectedName?: string | null
  unbounded?: boolean
}>(), {
  persons: () => [],
  relations: () => [],
  structuredText: '',
  rawText: '',
  title: '族谱总谱',
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

const layout = computed(() => layoutCardTree(data.value.persons, data.value.relations))

const focusNeighborhood = computed(() =>
  buildFocusNeighborhood(data.value.persons, data.value.relations, props.selectedName),
)
const hasFocus = computed(() => Boolean(props.selectedName))

function personFocused(id: string) {
  return isPersonFocused(id, focusNeighborhood.value, hasFocus.value)
}
</script>

<template>
  <div class="zupu-card-view" role="region" aria-label="卡片世代树">
    <header class="zupu-card-view-header">
      <h3 class="zupu-card-view-title">{{ title }}</h3>
      <span v-if="data.persons.length" class="zupu-card-view-meta">
        {{ data.persons.length }} 人
        <template v-if="data.relations.length"> · {{ data.relations.length }} 关系</template>
      </span>
    </header>

    <div v-if="!data.persons.length" class="zupu-view-empty">
      完成关系整理后可在此按世代浏览（参考族谱 App · 卡片模式）
    </div>

    <div v-else class="zupu-card-view-scroll" :class="{ 'zupu-card-view-scroll--unbounded': unbounded, 'zupu-card-view-scroll--focus': hasFocus }">
      <div
        class="zupu-card-view-canvas"
        :style="{ width: layout.width + 'px', minHeight: layout.height + 'px' }"
      >
        <svg class="zupu-card-view-edges" :width="layout.width" :height="layout.height">
          <line
            v-for="(e, i) in layout.edges"
            :key="'e' + i"
            :x1="e.x1"
            :y1="e.y1"
            :x2="e.x2"
            :y2="e.y2"
            :class="'zupu-edge zupu-edge--' + e.kind"
          />
        </svg>

        <aside class="zupu-card-view-sidebar" :style="{ width: SIDEBAR_W + 'px' }">
          <div
            v-for="row in layout.rows"
            :key="'g' + row.generation"
            class="zupu-gen-sidebar-label"
            :style="{ top: row.y + 'px', height: CARD_H + 'px' }"
          >
            第{{ row.generation }}代
          </div>
        </aside>

        <div class="zupu-card-view-main">
          <div
            v-for="row in layout.rows"
            :key="'r' + row.generation"
            class="zupu-card-row"
            :style="{ top: row.y + 'px', height: row.height + 'px' }"
          >
            <div
              v-for="(unit, ui) in row.units"
              :key="'u' + row.generation + '-' + ui"
              class="zupu-card-unit"
              :style="{ left: unit.x + 'px', width: unit.width + 'px' }"
            >
              <button
                v-for="p in unit.persons"
                :key="p.id"
                type="button"
                class="zupu-person-card"
                :class="[
                  'zupu-person-card--' + p.gender,
                  {
                    'zupu-person-card--selected': selectedName === p.name,
                    'zupu-person-card--dimmed': hasFocus && !personFocused(p.id),
                    'zupu-person-card--focused': hasFocus && personFocused(p.id),
                  },
                ]"
                :style="{ width: CARD_W + 'px', height: CARD_H + 'px' }"
                @click="emit('select', p.name)"
              >
                <span class="zupu-person-card-avatar" aria-hidden="true">
                  <svg viewBox="0 0 48 56" class="zupu-avatar-svg">
                    <ellipse cx="24" cy="14" rx="10" ry="11" fill="currentColor" opacity="0.4" />
                    <path d="M8 52c2-14 10-20 16-20s14 6 16 20" fill="currentColor" opacity="0.32" />
                  </svg>
                </span>
                <span class="zupu-person-card-name">{{ p.name }}</span>
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
