<script setup lang="ts">
import { computed } from 'vue'
import GenealogyCardTreeView from './GenealogyCardTreeView.vue'
import SourceSilkwormPageView from './SourceSilkwormPageView.vue'
import { mapApiPersons, mapApiRelations } from '../../utils/genealogyViewData'

export type ReferenceViewMode = 'card' | 'page'

const props = withDefaults(
  defineProps<{
    mode?: ReferenceViewMode
    persons?: any[]
    relations?: any[]
    title?: string
    selectedPersonId?: string | null
    structuredText?: string
    fill?: boolean
    unbounded?: boolean
  }>(),
  {
    mode: 'page',
    persons: () => [],
    relations: () => [],
    title: '族谱',
    selectedPersonId: null,
    structuredText: '',
    fill: true,
    unbounded: false,
  },
)

const emit = defineEmits<{ select: [personId: string] }>()

const viewPersons = computed(() => mapApiPersons(props.persons))
const viewRelations = computed(() => mapApiRelations(props.relations))

const selectedName = computed(() => {
  if (!props.selectedPersonId) return null
  const p = props.persons.find((x) => x.id === props.selectedPersonId)
  return p?.name || null
})

function onSelectName(name: string) {
  const p = props.persons.find((x) => x.name === name)
  if (p?.id) emit('select', p.id)
}
</script>

<template>
  <div
    class="genealogy-reference-view"
    :class="{ 'genealogy-reference-view--fill': fill, 'genealogy-reference-view--unbounded': unbounded }"
  >
    <GenealogyCardTreeView
      v-if="mode === 'card'"
      :persons="viewPersons"
      :relations="viewRelations"
      :structured-text="structuredText"
      :title="title"
      :selected-name="selectedName"
      :unbounded="unbounded"
      @select="onSelectName"
    />
    <SourceSilkwormPageView
      v-else
      :persons="viewPersons"
      :relations="viewRelations"
      :structured-text="structuredText"
      :title="title"
      :selected-name="selectedName"
      :unbounded="unbounded"
      @select="onSelectName"
    />
  </div>
</template>
