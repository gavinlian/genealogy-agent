<script setup lang="ts">
import { computed } from 'vue'

export type SourceCompareData = {
  compare_mode?: 'parse_import' | string
  has_source?: boolean
  aligned?: boolean
  message?: string
  source_version?: { label?: string; version_no?: number; status?: string }
  source_length?: number
  current?: { person_count?: number; relation_count?: number }
  from_source?: { person_count?: number; relation_count?: number }
  missing_persons?: string[]
  extra_persons?: string[]
  missing_relations?: Array<{ from: string; to: string; type?: string }>
  extra_relations?: Array<{ from: string; to: string; type?: string }>
  proposed_relations?: Array<{ from: string; to: string; type?: string }>
  persons_to_add?: string[]
  persons_skipped?: string[]
  relations_to_add?: Array<{ from: string; to: string; type?: string }>
  relations_skipped?: Array<{ from: string; to: string; type?: string }>
  relations_unresolved?: Array<{ from: string; to: string; type?: string }>
  persons_to_add_count?: number
  relations_to_add_count?: number
  hints?: string[]
  issues_count?: number
}

const props = defineProps<{
  compare: SourceCompareData | null
  relationsToAdd: number
  personsToAdd?: number
  personDetailsToAdd?: number
  mode?: 'source' | 'parse'
}>()

const emit = defineEmits<{
  close: []
  apply: []
  openSource: []
}>()

const isParseMode = computed(() => props.mode === 'parse' || props.compare?.compare_mode === 'parse_import')
const title = computed(() => (isParseMode.value ? '解析结果 vs 主谱' : '主谱 vs 原文对比'))

const applyLabel = computed(() => {
  if (isParseMode.value) {
    const p = props.personsToAdd ?? props.compare?.persons_to_add_count ?? 0
    const r = props.relationsToAdd ?? props.compare?.relations_to_add_count ?? 0
    if (p === 0 && r === 0) return '无新增项'
    return `确认加入主谱（+${p} 人、+${r} 关系）`
  }
  return props.relationsToAdd || props.personDetailsToAdd
    ? (props.compare?.has_source
      ? `应用整理（+${props.relationsToAdd} 关系${props.personDetailsToAdd ? `、+${props.personDetailsToAdd} 人资料` : ''}）`
      : `仍要补全（+${props.relationsToAdd} 关系${props.personDetailsToAdd ? `、+${props.personDetailsToAdd} 人资料` : ''}）`)
    : (props.compare?.has_source ? '无需补关系' : '无法对比')
})

const canApply = computed(() => {
  if (isParseMode.value) {
    const p = props.personsToAdd ?? props.compare?.persons_to_add_count ?? 0
    const r = props.relationsToAdd ?? props.compare?.relations_to_add_count ?? 0
    return p > 0 || r > 0
  }
  return props.relationsToAdd > 0 || (props.personDetailsToAdd ?? 0) > 0
})

const versionLabel = computed(() => {
  const v = props.compare?.source_version
  if (!v) return '族谱原文'
  return v.label || `第${v.version_no}版`
})

function relLabel(r: { from: string; to: string; type?: string }) {
  const t = r.type === 'spouse' ? '配偶' : '父子'
  return `${r.from} → ${r.to}（${t}）`
}
</script>

<template>
  <div class="modal source-compare-modal" @click.self="emit('close')">
    <div class="modal-content modal-lg source-compare-panel">
      <div class="ai-settings-header">
        <h3>{{ title }}</h3>
        <button class="btn-close" type="button" @click="emit('close')">×</button>
      </div>

      <p v-if="isParseMode" class="source-compare-intro">
        两阶段解析不会直接合并进主谱。请确认下方<strong>新增项</strong>后再入库；已存在成员与关系将自动跳过。
      </p>

      <p v-if="!compare?.has_source" class="hint">{{ compare?.message || '暂无原文，无法对比' }}</p>
      <p v-if="!compare?.has_source && relationsToAdd && !isParseMode" class="hint source-compare-fallback">
        仍可按现有成员与规则补全 {{ relationsToAdd }} 条关系。
      </p>

      <template v-else>
        <p class="source-compare-intro">
          <template v-if="isParseMode">
            当前主谱 {{ compare?.current?.person_count ?? 0 }} 人 / {{ compare?.current?.relation_count ?? 0 }} 关系
            · 本次解析 {{ compare?.from_source?.person_count ?? 0 }} 人 / {{ compare?.from_source?.relation_count ?? 0 }} 关系
          </template>
          <template v-else>
            对比基准：<strong>{{ versionLabel }}</strong>
            <span v-if="compare?.source_length">（{{ compare.source_length }} 字）</span>
            · 当前主谱 {{ compare?.current?.person_count ?? 0 }} 人 / {{ compare?.current?.relation_count ?? 0 }} 关系
            · 原文解析约 {{ compare?.from_source?.person_count ?? 0 }} 人 / {{ compare?.from_source?.relation_count ?? 0 }} 关系
          </template>
        </p>

        <div v-if="compare?.aligned && !canApply" class="source-compare-ok">
          {{ isParseMode ? '解析结果与主谱一致，无新增项。' : '当前主谱与原文基本一致，未发现明显差异。' }}
        </div>

        <ul v-if="compare?.hints?.length" class="source-compare-hints">
          <li v-for="(h, i) in compare.hints" :key="i">{{ h }}</li>
        </ul>

        <details v-if="isParseMode && compare?.persons_to_add?.length" class="source-compare-block" open>
          <summary>将新增成员（{{ compare.persons_to_add.length }}）</summary>
          <p>{{ compare.persons_to_add.join('、') }}</p>
        </details>

        <details v-if="isParseMode && compare?.persons_skipped?.length" class="source-compare-block">
          <summary>主谱已有、跳过（{{ compare.persons_skipped.length }}）</summary>
          <p>{{ compare.persons_skipped.join('、') }}</p>
        </details>

        <details v-if="!isParseMode && compare?.missing_persons?.length" class="source-compare-block" open>
          <summary>原文有、主谱缺（{{ compare.missing_persons.length }}）</summary>
          <p>{{ compare.missing_persons.join('、') }}</p>
        </details>

        <details v-if="compare?.extra_persons?.length && !isParseMode" class="source-compare-block">
          <summary>主谱有、原文未体现（{{ compare.extra_persons.length }}）</summary>
          <p>{{ compare.extra_persons.join('、') }}</p>
        </details>

        <details v-if="(isParseMode ? compare?.relations_to_add : compare?.missing_relations)?.length" class="source-compare-block" open>
          <summary>{{ isParseMode ? '将新增关系' : '原文暗示但主谱缺关系' }}（{{ (isParseMode ? compare?.relations_to_add : compare?.missing_relations)?.length }}）</summary>
          <ul>
            <li v-for="(r, i) in (isParseMode ? compare?.relations_to_add : compare?.missing_relations)" :key="'m' + i">{{ relLabel(r) }}</li>
          </ul>
        </details>

        <details v-if="isParseMode && compare?.relations_skipped?.length" class="source-compare-block">
          <summary>主谱已有、跳过关系（{{ compare.relations_skipped.length }}）</summary>
          <ul>
            <li v-for="(r, i) in compare.relations_skipped.slice(0, 15)" :key="'s' + i">{{ relLabel(r) }}</li>
          </ul>
        </details>

        <details v-if="isParseMode && compare?.relations_unresolved?.length" class="source-compare-block source-compare-block--warn">
          <summary>暂无法入库的关系（{{ compare.relations_unresolved.length }}）</summary>
          <ul>
            <li v-for="(r, i) in compare.relations_unresolved" :key="'u' + i">{{ relLabel(r) }}</li>
          </ul>
        </details>

        <details v-if="!isParseMode && compare?.extra_relations?.length" class="source-compare-block">
          <summary>主谱多出的关系（{{ compare.extra_relations.length }}）</summary>
          <ul>
            <li v-for="(r, i) in compare.extra_relations" :key="'e' + i">{{ relLabel(r) }}</li>
          </ul>
        </details>

        <details v-if="!isParseMode && relationsToAdd > 0" class="source-compare-block source-compare-proposed" open>
          <summary>快速整理将补全（{{ relationsToAdd }} 条关系）</summary>
          <ul>
            <li v-for="(r, i) in compare?.proposed_relations?.slice(0, 20)" :key="'p' + i">{{ relLabel(r) }}</li>
            <li v-if="(compare?.proposed_relations?.length || 0) > 20" class="hint">… 其余 {{ (compare?.proposed_relations?.length || 0) - 20 }} 条</li>
          </ul>
        </details>
      </template>

      <div class="modal-actions modal-actions-spread">
        <button v-if="!isParseMode" type="button" class="btn-secondary" @click="emit('openSource')">打开原文编辑</button>
        <div class="modal-actions-right">
          <button type="button" class="btn-secondary" @click="emit('close')">取消</button>
          <button type="button" class="btn-primary" :disabled="!canApply" @click="emit('apply')">
            {{ applyLabel }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
