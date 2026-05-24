<script setup lang="ts">
defineProps<{
  name: string
  surname?: string
  description?: string
  status?: string
  familyId?: string
}>()
</script>

<template>
  <div class="agent-el agent-el--create-family">
    <div class="agent-el-header">
      <span class="agent-el-icon">📖</span>
      <strong>{{ status === 'created' ? '族谱已创建' : '建谱预览' }}</strong>
      <span v-if="status === 'created'" class="agent-el-badge agent-el-badge--ok">已入库</span>
      <span v-else class="agent-el-badge">待创建</span>
    </div>
    <dl class="agent-el-dl">
      <div v-if="name" class="agent-el-row">
        <dt>名称</dt>
        <dd>{{ name }}</dd>
      </div>
      <div v-if="surname" class="agent-el-row">
        <dt>姓氏</dt>
        <dd>{{ surname }}氏</dd>
      </div>
      <div v-if="description" class="agent-el-row">
        <dt>简介</dt>
        <dd>{{ description }}</dd>
      </div>
    </dl>
  </div>
</template>
