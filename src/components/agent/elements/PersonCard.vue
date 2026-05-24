<script setup lang="ts">
defineProps<{
  name: string
  courtesyName?: string
  artName?: string
  generation?: number | string | null
  birthYear?: number | string | null
  deathYear?: number | string | null
  biography?: string
  sourceExcerpt?: string
}>()
</script>

<template>
  <div class="agent-el agent-el--person">
    <div class="agent-el-header">
      <span class="agent-el-icon">👤</span>
      <strong>{{ name }}</strong>
      <span v-if="generation" class="agent-el-badge">第{{ generation }}代</span>
    </div>
    <dl class="agent-el-dl">
      <div v-if="courtesyName || artName" class="agent-el-row">
        <dt>字号</dt>
        <dd>
          <span v-if="courtesyName">字 {{ courtesyName }}</span>
          <span v-if="artName">{{ courtesyName ? ' · ' : '' }}号 {{ artName }}</span>
        </dd>
      </div>
      <div v-if="birthYear || deathYear" class="agent-el-row">
        <dt>生卒</dt>
        <dd>{{ birthYear || '?' }} — {{ deathYear || '?' }}</dd>
      </div>
      <div v-if="biography" class="agent-el-row">
        <dt>简介</dt>
        <dd>{{ biography }}</dd>
      </div>
      <div v-if="sourceExcerpt" class="agent-el-row agent-el-row--excerpt">
        <dt>原文</dt>
        <dd>{{ sourceExcerpt }}</dd>
      </div>
    </dl>
  </div>
</template>
