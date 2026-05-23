<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import {
  type OrganizePlan,
  type OrganizeDiff,
  planHasChanges,
  relLabel,
} from '../types/organize'

const props = defineProps<{
  familyId: string
  memberCount: number
  selectedPersonId?: string
  selectedPersonName?: string
  plan: OrganizePlan | null
  diff: OrganizeDiff | null
  applyMode: 'merge' | 'replace'
  cleanSlate: boolean
  sourceVersionId?: string
  sourceVersionLabel?: string
}>()

const emit = defineEmits<{
  'update:applyMode': [value: 'merge' | 'replace']
  'update:cleanSlate': [value: boolean]
  'update:plan': [value: OrganizePlan]
  applied: [stats?: Record<string, number>]
  cleared: []
  'open-ai-chat': []
  dismiss: []
  'plan-edited': []
}>()

const API = '/api'
const applying = ref(false)
const clearing = ref(false)
const newRelFrom = ref('')
const newRelTo = ref('')
const newRelType = ref<'parent_child' | 'spouse'>('parent_child')
const textPreview = ref('')
const textPreviewLoading = ref(false)
const textPreviewLabel = ref('')

const isEmptyGenealogy = computed(() => props.memberCount <= 0)

const planRelations = computed(() => props.plan?.relations_add || [])

const suspiciousDuplicateAdd = computed(() => {
  const addCount = props.diff?.persons_to_add?.length || 0
  return props.memberCount > 0 && addCount > Math.max(3, Math.floor(props.memberCount * 0.3))
})

function patchPlan(patch: Partial<OrganizePlan>) {
  if (!props.plan) return
  emit('update:plan', { ...props.plan, ...patch })
  emit('plan-edited')
}

function updateRelationField(index: number, field: 'from' | 'to' | 'type', value: string) {
  const list = planRelations.value.map((r, i) =>
    i === index ? { ...r, [field]: value } : { ...r },
  )
  patchPlan({ relations_add: list })
}

function removeRelationAt(index: number) {
  const list = planRelations.value.filter((_, i) => i !== index)
  patchPlan({ relations_add: list })
}

function addRelationRow() {
  const from = newRelFrom.value.trim()
  const to = newRelTo.value.trim()
  if (!from || !to) return
  patchPlan({
    relations_add: [...planRelations.value, { from, to, type: newRelType.value }],
  })
  newRelFrom.value = ''
  newRelTo.value = ''
}

function removeNewPerson(name: string) {
  const list = (props.plan?.new_persons || []).filter((p) => p.name !== name)
  patchPlan({ new_persons: list })
}

async function loadTextPreview() {
  if (!props.familyId) return
  textPreviewLoading.value = true
  try {
    const res = await api('POST', `/families/${props.familyId}/source-versions/text-preview`, {
      source_version_id: props.sourceVersionId || undefined,
    })
    if (res.success === false) {
      textPreview.value = ''
      textPreviewLabel.value = ''
      return
    }
    textPreview.value = res.relation_text || ''
    textPreviewLabel.value = res.source_version_label || props.sourceVersionLabel || '当前原文'
  } catch {
    textPreview.value = ''
  } finally {
    textPreviewLoading.value = false
  }
}

watch(
  () => [props.familyId, props.sourceVersionId] as const,
  () => {
    void loadTextPreview()
  },
  { immediate: true },
)

const applyModeModel = computed({
  get: () => props.applyMode,
  set: (v: 'merge' | 'replace') => emit('update:applyMode', v),
})

const cleanSlateModel = computed({
  get: () => props.cleanSlate,
  set: (v: boolean) => emit('update:cleanSlate', v),
})

async function api(method: string, path: string, data?: unknown) {
  const res = await fetch(`${API}${path}`, {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: data ? JSON.stringify(data) : undefined,
  })
  const text = await res.text()
  try {
    return JSON.parse(text)
  } catch {
    return { success: false, error: text.slice(0, 120) }
  }
}

function applyModeSummary() {
  if (!props.diff) return ''
  const d = props.diff
  if (props.applyMode === 'replace' && d.has_replace_impact) {
    return `将合并变更，并额外移除 ${d.extra_relations?.length || 0} 条关系、${d.extra_persons?.length || 0} 人`
  }
  return '仅应用新增/修改/删除项，保留其余主谱内容'
}

async function clearGenealogy(scope: 'all' | 'branch') {
  if (clearing.value || applying.value) return
  if (scope === 'all' && props.memberCount <= 0) {
    alert('当前主谱尚无成员')
    return
  }
  if (scope === 'branch' && !props.selectedPersonId) {
    alert('请先在左侧世代导航选中要清空的分支根节点')
    return
  }

  const msg =
    scope === 'all'
      ? `确定清空全部主谱？\n\n将删除本族谱全部 ${props.memberCount} 名成员与所有关系。\n族谱记录、原文版本与 AI 对话会保留，此操作不可撤销。`
      : `确定清空当前分支？\n\n将删除「${props.selectedPersonName || '选中成员'}」及其全部后代（不含上级与兄弟支）。\n此操作不可撤销。`
  if (!confirm(msg)) return

  clearing.value = true
  try {
    const res = await api('POST', `/families/${props.familyId}/clear-genealogy`, {
      scope,
      root_person_id: scope === 'branch' ? props.selectedPersonId : undefined,
    })
    if (!res.success) {
      alert(res.error || res.detail || '清空失败')
      return
    }
    emit('cleared')
  } catch {
    alert('清空失败，请确认后端已启动')
  } finally {
    clearing.value = false
  }
}

async function applyQuick(mode: 'merge' | 'replace') {
  applyModeModel.value = mode
  const skipConfirm = isEmptyGenealogy.value && mode === 'replace'
  await applyPlan(skipConfirm)
}

async function applyPlan(skipReplaceConfirm = false) {
  if (!props.plan || applying.value) return
  if (
    !skipReplaceConfirm
    && props.applyMode === 'replace'
    && props.diff?.has_replace_impact
    && props.memberCount > 0
  ) {
    const extra = props.diff.replace_extra_count || 0
    const ok = confirm(
      `「干净替换」会删除 ${props.diff.extra_relations?.length || 0} 条多余关系`
        + `、${props.diff.extra_persons?.length || 0} 名未出现在整理结果中的成员（共 ${extra} 项）。\n\n此操作不可自动撤销，是否继续？`,
    )
    if (!ok) return
  }
  applying.value = true
  try {
    const res = await api('POST', `/families/${props.familyId}/ai-organize`, {
      persist: true,
      plan: props.plan,
      apply_mode: props.applyMode,
      diff: props.diff,
    })
    if (!res.success) {
      alert(res.error || res.detail || '应用失败')
      return
    }
    const applied = res.applied || {}
    const wrote = (applied.persons_added || 0) + (applied.relations_added || 0) + (applied.persons_updated || 0)
    if (wrote <= 0 && planHasChanges(props.plan)) {
      alert(
        '未能写入主谱：方案中的姓名可能与主谱不一致，或关系已存在。\n'
        + '请检查「方案关系」中的姓名，或先在上方文字版中校对后再应用。',
      )
      return
    }
    emit('dismiss')
    emit('applied', applied)
  } catch {
    alert('应用失败')
  } finally {
    applying.value = false
  }
}
</script>

<template>
  <div class="workspace-drawer organize-drawer">
    <div class="organize-drawer-header">
      <div>
        <h4>族谱整理</h4>
        <p class="hint organize-drawer-hint">
          基于上方「原文」里当前选中的版本预览文字稿（不会自动切换版本）；在此应用 AI 方案或清空主谱。
        </p>
      </div>
      <button type="button" class="btn-xs btn-primary" @click="emit('open-ai-chat')">打开 AI 对话</button>
    </div>

    <details v-if="textPreview || textPreviewLoading" class="organize-text-preview ai-organize-details" open>
      <summary>
        文字版预览（{{ textPreviewLabel || '当前原文' }}）{{ textPreviewLoading ? '…' : '' }}
      </summary>
      <pre class="organize-text-preview-body">{{ textPreview || '加载中…' }}</pre>
    </details>

    <div class="organize-toolbar">
      <label class="organize-toggle">
        <input v-model="cleanSlateModel" type="checkbox" :disabled="clearing || applying" />
        干净整理（AI 下次按方案重建，不保留旧错关系）
      </label>
      <div class="organize-toolbar-actions">
        <button
          type="button"
          class="btn-xs btn-danger"
          :disabled="clearing || applying || memberCount <= 0"
          @click="clearGenealogy('all')"
        >
          {{ clearing ? '清空中…' : '清空全部主谱' }}
        </button>
        <button
          v-if="selectedPersonId"
          type="button"
          class="btn-xs btn-danger-outline"
          :disabled="clearing || applying"
          @click="clearGenealogy('branch')"
        >
          清空当前分支（{{ selectedPersonName || '选中' }}）
        </button>
        <span v-else class="hint organize-branch-hint">清空分支：请先在左侧选中成员</span>
      </div>
    </div>

    <div v-if="!plan || !planHasChanges(plan)" class="organize-empty">
      <p v-if="plan && plan.explanation" class="organize-ai-note">{{ plan.explanation }}</p>
      <p v-else class="hint">暂无待应用的 AI 方案。可点「打开 AI 对话」描述整理意图，方案会显示在此处。</p>
    </div>

    <div v-else class="ai-organize-preview organize-plan-panel">
      <div class="organize-plan-header">
        <strong>待应用方案</strong>
        <button v-if="plan" type="button" class="btn-xs" @click="emit('dismiss')">清除方案</button>
      </div>
      <p v-if="plan?.explanation" class="organize-plan-explanation">{{ plan.explanation }}</p>

      <div v-if="isEmptyGenealogy" class="organize-empty-hint organize-empty-hint--action">
        主谱为空，可直接将 AI 方案写入主谱（推荐「替换写入」）。
      </div>

      <div v-if="suspiciousDuplicateAdd" class="organize-empty-hint organize-empty-hint--warn">
        检测到将新增 {{ diff?.persons_to_add?.length }} 人（主谱现有 {{ memberCount }} 人），可能是 AI 重复列出了已有成员。
        请在下方案例中删除多余「新增成员」，或改用「替换写入主谱」。
      </div>

      <div class="organize-quick-apply">
        <button
          type="button"
          class="btn-sm"
          :disabled="applying || isEmptyGenealogy"
          @click="applyQuick('merge')"
        >
          {{ applying && applyMode === 'merge' ? '写入中…' : '插入到现有主谱' }}
        </button>
        <button
          type="button"
          class="btn-primary btn-sm"
          :disabled="applying"
          @click="applyQuick('replace')"
        >
          {{ applying && applyMode === 'replace' ? '写入中…' : '替换写入主谱' }}
        </button>
      </div>

      <div v-if="diff" class="ai-organize-diff-stats">
        <div class="ai-organize-diff-col">
          <span class="ai-organize-diff-label">整理前</span>
          <strong>{{ diff.before?.person_count ?? 0 }}</strong> 人
          <span class="ai-organize-diff-sep">/</span>
          <strong>{{ diff.before?.relation_count ?? 0 }}</strong> 关系
        </div>
        <span class="ai-organize-diff-arrow">→</span>
        <div class="ai-organize-diff-col ai-organize-diff-col--after">
          <span class="ai-organize-diff-label">整理后（预览）</span>
          <strong>{{ diff.after?.person_count ?? 0 }}</strong> 人
          <span class="ai-organize-diff-sep">/</span>
          <strong>{{ diff.after?.relation_count ?? 0 }}</strong> 关系
        </div>
      </div>

      <ul v-if="diff?.hints?.length" class="ai-organize-diff-hints">
        <li v-for="(h, i) in diff.hints" :key="'h' + i">{{ h }}</li>
      </ul>

      <details v-if="diff?.persons_to_add?.length" class="ai-organize-details" open>
        <summary>将新增成员（{{ diff.persons_to_add.length }}）— 可删除误识别的重复项</summary>
        <ul class="organize-editable-list">
          <li v-for="name in diff.persons_to_add" :key="'np-' + name" class="organize-editable-row">
            <span>{{ name }}</span>
            <button type="button" class="btn-xs" @click="removeNewPerson(name)">删除</button>
          </li>
        </ul>
      </details>
      <details v-if="diff?.persons_to_update?.length" class="ai-organize-details">
        <summary>将更新成员（{{ diff.persons_to_update.length }}）</summary>
        <ul>
          <li v-for="(p, j) in diff.persons_to_update" :key="'u' + j">
            {{ p.name }}（{{ (p.fields || []).join('、') || '资料' }}）
          </li>
        </ul>
      </details>
      <details v-if="planRelations.length" class="ai-organize-details organize-editable-relations" open>
        <summary>方案关系（{{ planRelations.length }}）— 可直接编辑或删除</summary>
        <div class="organize-relation-editor">
          <div
            v-for="(r, j) in planRelations"
            :key="'edit-' + j"
            class="organize-relation-row"
          >
            <input
              class="input input-xs"
              :value="r.from"
              placeholder="父/夫"
              @change="updateRelationField(j, 'from', ($event.target as HTMLInputElement).value)"
            />
            <span class="organize-relation-arrow">→</span>
            <input
              class="input input-xs"
              :value="r.to"
              placeholder="子/妻"
              @change="updateRelationField(j, 'to', ($event.target as HTMLInputElement).value)"
            />
            <select
              class="input input-xs"
              :value="r.type || 'parent_child'"
              @change="updateRelationField(j, 'type', ($event.target as HTMLSelectElement).value)"
            >
              <option value="parent_child">父子</option>
              <option value="spouse">配偶</option>
            </select>
            <button type="button" class="btn-xs btn-danger-outline" @click="removeRelationAt(j)">删</button>
          </div>
          <div class="organize-relation-add">
            <input v-model="newRelFrom" class="input input-xs" placeholder="父/夫" />
            <span class="organize-relation-arrow">→</span>
            <input v-model="newRelTo" class="input input-xs" placeholder="子/妻" />
            <select v-model="newRelType" class="input input-xs">
              <option value="parent_child">父子</option>
              <option value="spouse">配偶</option>
            </select>
            <button type="button" class="btn-xs btn-primary" @click="addRelationRow">添加</button>
          </div>
        </div>
      </details>
      <details v-if="diff?.relations_to_add?.length && diff.relations_to_add.length !== planRelations.length" class="ai-organize-details">
        <summary>相对主谱将新增（{{ diff.relations_to_add.length }}）</summary>
        <ul>
          <li v-for="(r, j) in diff.relations_to_add" :key="'a' + j">{{ relLabel(r) }}</li>
        </ul>
      </details>
      <details v-if="diff?.relations_to_remove?.length" class="ai-organize-details">
        <summary>将删除关系（{{ diff.relations_to_remove.length }}）</summary>
        <ul>
          <li v-for="(r, j) in diff.relations_to_remove" :key="'r' + j">{{ relLabel(r) }}</li>
        </ul>
      </details>
      <details v-if="diff?.extra_persons?.length" class="ai-organize-details ai-organize-details--warn">
        <summary>干净替换时移除的成员（{{ diff.extra_persons.length }}）</summary>
        <p>{{ diff.extra_persons.join('、') }}</p>
      </details>
      <details v-if="diff?.extra_relations?.length" class="ai-organize-details ai-organize-details--warn">
        <summary>干净替换时移除的关系（{{ diff.extra_relations.length }}）</summary>
        <ul>
          <li v-for="(r, j) in diff.extra_relations.slice(0, 15)" :key="'e' + j">{{ relLabel(r) }}</li>
          <li v-if="diff.extra_relations.length > 15" class="hint">… 其余 {{ diff.extra_relations.length - 15 }} 条</li>
        </ul>
      </details>

      <div v-if="diff?.has_replace_impact || plan?.clean_slate" class="ai-organize-apply-mode">
        <span class="ai-organize-apply-mode-label">应用方式</span>
        <label class="ai-organize-mode-option">
          <input v-model="applyModeModel" type="radio" value="merge" :disabled="Boolean(plan?.clean_slate || diff?.clean_slate)" />
          增量合并
        </label>
        <label class="ai-organize-mode-option ai-organize-mode-option--recommended">
          <input v-model="applyModeModel" type="radio" value="replace" />
          干净替换（推荐）
        </label>
        <p v-if="plan?.clean_slate || diff?.clean_slate" class="hint ai-organize-mode-hint ai-organize-mode-hint--warn">
          干净整理：会移除未出现在方案中的旧关系与多余成员。
        </p>
        <p v-else class="hint ai-organize-mode-hint">{{ applyModeSummary() }}</p>
      </div>
    </div>
  </div>
</template>
