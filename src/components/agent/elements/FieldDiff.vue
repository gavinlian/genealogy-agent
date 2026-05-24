<script setup lang="ts">
defineProps<{
  title?: string
  changes: { field: string; from?: unknown; to?: unknown }[]
}>()
</script>

<template>
  <div class="agent-el agent-el--field-diff">
    <div class="agent-el-header">
      <span class="agent-el-icon">✏️</span>
      <strong>{{ title || '字段变更' }}</strong>
    </div>
    <div class="agent-el-changes">
      <div
        v-for="(c, i) in changes"
        :key="i"
        class="agent-el-change-row"
      >
        <span class="agent-el-change-field">{{ c.field }}</span>
        <span class="agent-el-change-val">{{ c.from ?? '空' }} → {{ c.to }}</span>
      </div>
    </div>
  </div>
</template>
