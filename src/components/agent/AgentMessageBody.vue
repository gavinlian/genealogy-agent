<script setup lang="ts">
import type { AgentMessagePart } from '../../agent/types'
import CreateFamilyPreview from './elements/CreateFamilyPreview.vue'
import PersonCard from './elements/PersonCard.vue'
import FieldDiff from './elements/FieldDiff.vue'

defineProps<{
  parts?: AgentMessagePart[]
  fallbackContent?: string
}>()

function peopleFromData(data: Record<string, unknown> | undefined) {
  return (data?.people as { name?: string; courtesy_name?: string; generation?: number }[]) || []
}
</script>

<template>
  <div class="agent-message-body">
    <template v-if="parts?.length">
      <template v-for="(part, i) in parts" :key="i">
        <p v-if="part.type === 'text' && part.content" class="agent-msg-text">{{ part.content }}</p>

        <CreateFamilyPreview
          v-else-if="part.type === 'create_family_preview' && part.data"
          :name="String(part.data.name || '')"
          :surname="String(part.data.surname || '')"
          :description="String(part.data.description || '')"
          :status="String(part.data.status || 'pending')"
          :family-id="String(part.data.family_id || '')"
        />

        <PersonCard
          v-else-if="part.type === 'person_card' && part.data"
          :name="String(part.data.name || '未知')"
          :courtesy-name="String(part.data.courtesy_name || '')"
          :art-name="String(part.data.art_name || '')"
          :generation="part.data.generation as number | string | null"
          :birth-year="part.data.birth_year as number | string | null"
          :death-year="part.data.death_year as number | string | null"
          :biography="String(part.data.biography || '')"
          :source-excerpt="String(part.data.source_excerpt || '')"
        />

        <FieldDiff
          v-else-if="part.type === 'field_diff' && part.data"
          :title="String(part.data.title || '')"
          :changes="(part.data.changes as { field: string; from?: unknown; to?: unknown }[]) || []"
        />

        <div v-else-if="part.type === 'search_results' && part.data" class="agent-el agent-el--search">
          <div class="agent-el-header">
            <span class="agent-el-icon">🔍</span>
            <strong>{{ String(part.data.title || '搜索结果') }}</strong>
          </div>
          <ul class="agent-el-list">
            <li v-for="(p, pi) in peopleFromData(part.data)" :key="pi">
              {{ p.name }}
              <span v-if="p.courtesy_name" class="agent-el-muted">字 {{ p.courtesy_name }}</span>
              <span v-if="p.generation" class="agent-el-muted"> · 第{{ p.generation }}代</span>
            </li>
          </ul>
          <p v-if="Number(part.data.total) > peopleFromData(part.data).length" class="agent-el-muted">
            共 {{ part.data.total }} 人，仅显示前 {{ peopleFromData(part.data).length }} 位
          </p>
        </div>
      </template>
    </template>
    <p v-else-if="fallbackContent" class="agent-msg-text">{{ fallbackContent }}</p>
  </div>
</template>
