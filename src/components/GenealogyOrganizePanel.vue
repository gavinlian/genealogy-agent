<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import {
  type OrganizePlan,
  type OrganizeDiff,
  planHasChanges,
  pickDefaultApplyMode,
  relLabel,
} from '../types/organize'
import { api, API_TIMEOUT_LONG } from '../utils/api'

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
  sourceText?: string
  /** 嵌入整理工作台：隐藏顶部说明与「长对话」入口 */
  embedded?: boolean
}>()

const emit = defineEmits<{
  'update:applyMode': [value: 'merge' | 'replace']
  'update:cleanSlate': [value: boolean]
  'update:plan': [value: OrganizePlan]
  'load-plan': [payload: { plan: OrganizePlan; diff: OrganizeDiff | null }]
  applied: [stats?: Record<string, number>]
  cleared: []
  dismiss: []
  'plan-edited': []
  notify: [message: string, type?: 'success' | 'error' | 'info']
}>()

const API = '/api'
const API_LONG = 300000
const applying = ref(false)
const clearing = ref(false)
const smartLoading = ref(false)
const aiLoading = ref(false)
const chatInput = ref('')
const showAdvancedEditor = ref(false)
const autoRanFamilies = new Set<string>()

const AI_PRESETS = [
  {
    key: 'full',
    label: 'AI 整理全谱',
    hint: '从原文提取全部人物关系',
    prompt: '请根据附带的族谱原文，干净整理出完整主谱：提取所有人物、世代与父子/配偶关系，给出可应用的整理方案。',
    cleanSlate: true,
  },
  {
    key: 'gaps',
    label: '补缺失关系',
    hint: '只补主谱里没有的边',
    prompt: '对比原文与当前主谱，只补充缺失的父子/配偶关系；已有成员不要重复添加到 new_persons。',
    cleanSlate: false,
  },
  {
    key: 'spouse',
    label: '整理配偶',
    hint: '识别配/妻/夫',
    prompt: '重点从原文中整理配偶关系（配、妻、夫），补全 relations_add，尽量不改已有父子结构。',
    cleanSlate: false,
  },
  {
    key: 'branch',
    label: '整理选中支',
    hint: '需先在左侧选中成员',
    prompt: '',
    cleanSlate: false,
    needsSelection: true,
  },
] as const

const newRelFrom = ref('')
const newRelTo = ref('')
const newRelType = ref<'parent_child' | 'spouse'>('parent_child')
const textPreview = ref('')
const textPreviewLoading = ref(false)
const textPreviewLabel = ref('')
const applyDiagnostics = ref<{
  unmatched_names?: string[]
  skipped_relations?: { from: string; to: string; reason: string }[]
} | null>(null)

function notify(message: string, type: 'success' | 'error' | 'info' = 'info') {
  emit('notify', message, type)
}

function formatApplyDiagnostics(applied: Record<string, unknown>) {
  const diag = applied.diagnostics as {
    unmatched_names?: string[]
    skipped_relations?: { from: string; to: string; reason: string }[]
  } | undefined
  if (!diag) return ''
  const parts: string[] = []
  if (diag.unmatched_names?.length) {
    parts.push(`未在主谱匹配到的姓名：${diag.unmatched_names.slice(0, 8).join('、')}${diag.unmatched_names.length > 8 ? '…' : ''}`)
  }
  const skipped = diag.skipped_relations || []
  const missing = skipped.filter((r) => r.reason === 'missing_person')
  const exists = skipped.filter((r) => r.reason === 'already_exists')
  if (missing.length) {
    parts.push(`${missing.length} 条关系因姓名未入库被跳过（请检查方案关系中的「父/子」姓名）`)
  }
  if (exists.length) {
    parts.push(`${exists.length} 条关系已存在，未重复写入`)
  }
  return parts.join('；')
}

const isEmptyGenealogy = computed(() => props.memberCount <= 0)

const planRelations = computed(() => props.plan?.relations_add || [])

const personsToAdd = computed(() => props.diff?.persons_to_add || [])

const relationCards = computed(() => {
  const fromDiff = props.diff?.relations_to_add
  if (fromDiff?.length) return fromDiff
  return planRelations.value
})

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
  const card = relationCards.value[index]
  if (!card) return
  const list = planRelations.value.filter(
    (r) =>
      !(
        r.from === card.from
        && r.to === card.to
        && (r.type || 'parent_child') === (card.type || 'parent_child')
      ),
  )
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
      notify(res.error || res.message || '文字版预览失败', 'error')
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

watch(
  () => [props.familyId, props.plan] as const,
  ([fid, plan]) => {
    if (props.embedded || !fid || plan || autoRanFamilies.has(fid)) return
    autoRanFamilies.add(fid)
    void runSmartSuggest(false)
  },
  { immediate: true },
)

function absorbPlanResponse(res: {
  plan?: OrganizePlan | null
  diff?: OrganizeDiff | null
  explanation?: string
}) {
  if (!res.plan || !planHasChanges(res.plan)) {
    notify(res.explanation || '未产生可应用的整理变更', 'info')
    return false
  }
  emit('load-plan', { plan: res.plan, diff: res.diff ?? null })
  if (props.memberCount <= 0) {
    emit('update:applyMode', 'replace')
  } else {
    emit('update:applyMode', pickDefaultApplyMode(res, { memberCount: props.memberCount }))
  }
  return true
}

async function runSmartSuggest(showNotice = true) {
  if (!props.familyId || smartLoading.value) return
  smartLoading.value = true
  try {
    const res = await api('POST', `/families/${props.familyId}/smart-suggest`, {
      source_version_id: props.sourceVersionId || undefined,
    })
    if (!res.success) {
      if (showNotice) notify(res.error || res.detail || '智能分析失败', 'error')
      return
    }
    const ok = absorbPlanResponse(res)
    if (showNotice && ok) {
      const st = res.stats || {}
      notify(
        `智能分析完成：+${st.persons_to_add || 0} 人 · +${st.relations_to_add || 0} 关系`,
        'success',
      )
    } else if (showNotice && !ok) {
      notify(res.plan?.explanation || '原文与主谱已基本一致', 'info')
    }
  } catch {
    if (showNotice) notify('智能分析失败，请确认后端已启动', 'error')
  } finally {
    smartLoading.value = false
  }
}

async function runAiPreset(preset: (typeof AI_PRESETS)[number]) {
  if (!props.familyId || aiLoading.value) return
  if (preset.needsSelection && !props.selectedPersonName) {
    notify('请先在左侧世代导航选中一位成员', 'info')
    return
  }
  let message = preset.prompt
  if (preset.key === 'branch' && props.selectedPersonName) {
    message = `请围绕「${props.selectedPersonName}」及其上下几代，从原文整理并补全父子/配偶关系；不要重复添加主谱已有成员。`
  }
  if (preset.cleanSlate) emit('update:cleanSlate', true)
  aiLoading.value = true
  try {
    const res = await api(
      'POST',
      `/families/${props.familyId}/ai-organize`,
      {
        message,
        include_source: Boolean((props.sourceText || '').trim()),
        source_text: props.sourceText || undefined,
        source_version_id: props.sourceVersionId || undefined,
        clean_slate: preset.cleanSlate,
        refresh_context: true,
      },
      API_TIMEOUT_LONG,
    )
    if (!res.success) {
      notify(res.explanation || res.error || res.detail || 'AI 整理失败', 'error')
      return
    }
    if (absorbPlanResponse(res)) {
      notify('AI 方案已生成，请核对下方关系卡片后一键应用', 'success')
    }
  } catch {
    notify('AI 请求失败', 'error')
  } finally {
    aiLoading.value = false
  }
}

async function sendInlineChat() {
  const text = chatInput.value.trim()
  if (!text || aiLoading.value) return
  chatInput.value = ''
  aiLoading.value = true
  try {
    const res = await api(
      'POST',
      `/families/${props.familyId}/ai-organize`,
      {
        message: text,
        include_source: Boolean((props.sourceText || '').trim()),
        source_text: props.sourceText || undefined,
        source_version_id: props.sourceVersionId || undefined,
        clean_slate: props.cleanSlate,
      },
      API_TIMEOUT_LONG,
    )
    if (!res.success) {
      notify(res.explanation || res.error || '整理失败', 'error')
      return
    }
    if (absorbPlanResponse(res)) {
      notify('已更新整理方案', 'success')
    } else {
      notify(res.explanation || 'AI 已回复，本次无结构变更', 'info')
    }
  } catch {
    notify('请求失败', 'error')
  } finally {
    aiLoading.value = false
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
    notify('当前主谱尚无成员', 'info')
    return
  }
  if (scope === 'branch' && !props.selectedPersonId) {
    notify('请先在左侧世代导航选中要清空的分支根节点', 'info')
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
      notify(res.error || res.detail || '清空失败', 'error')
      return
    }
    emit('cleared')
  } catch {
    notify('清空失败，请确认后端已启动', 'error')
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
  applyDiagnostics.value = null
  try {
    const res = await api('POST', `/families/${props.familyId}/ai-organize`, {
      persist: true,
      plan: props.plan,
      apply_mode: props.applyMode,
      diff: props.diff,
    })
    if (!res.success) {
      notify(res.error || res.detail || res.message || '应用失败', 'error')
      return
    }
    const applied = res.applied || {}
    const wrote = (applied.persons_added || 0) + (applied.relations_added || 0) + (applied.persons_updated || 0)
    const diagMsg = formatApplyDiagnostics(applied as Record<string, unknown>)
    if (applied.diagnostics) {
      applyDiagnostics.value = applied.diagnostics as typeof applyDiagnostics.value
    }
    if (wrote <= 0 && planHasChanges(props.plan)) {
      notify(
        diagMsg || '未能写入主谱：请检查「方案关系」中的姓名是否与主谱一致，或先删除误增成员后再应用',
        'error',
      )
      return
    }
    emit('dismiss')
    emit('applied', applied)
  } catch {
    notify('应用失败，请确认后端已启动', 'error')
  } finally {
    applying.value = false
  }
}
</script>

<template>
  <div class="organize-drawer" :class="{ 'workspace-drawer': !embedded, 'organize-drawer--embedded': embedded }">
    <div v-if="!embedded" class="organize-drawer-header">
      <div>
        <h4>整理组谱</h4>
        <p class="hint organize-drawer-hint">点按钮自动分析关系，核对卡片后一键写入主谱。</p>
      </div>
    </div>

    <section
      v-if="embedded && (!plan || !planHasChanges(plan))"
      class="organize-smart-hub organize-smart-hub--embedded-mini"
      aria-label="AI 整理"
    >
      <div class="organize-smart-chips">
        <button
          type="button"
          class="organize-smart-chip"
          :disabled="smartLoading || aiLoading"
          @click="runSmartSuggest(true)"
        >
          ⚡ 智能分析
        </button>
        <button
          v-for="p in AI_PRESETS.slice(0, 3)"
          :key="p.key"
          type="button"
          class="organize-smart-chip"
          :disabled="aiLoading || smartLoading || (p.needsSelection && !selectedPersonName)"
          :title="p.hint"
          @click="runAiPreset(p)"
        >
          {{ p.label }}
        </button>
      </div>
      <div class="organize-inline-chat">
        <input
          v-model="chatInput"
          class="input organize-inline-chat-input"
          placeholder="问 AI：如「把张三的儿子都连上」"
          :disabled="aiLoading"
          @keydown.enter.prevent="sendInlineChat"
        />
        <button
          type="button"
          class="btn-primary btn-sm"
          :disabled="!chatInput.trim() || aiLoading"
          @click="sendInlineChat"
        >
          {{ aiLoading ? '…' : '问 AI' }}
        </button>
      </div>
    </section>

    <section v-if="!embedded" class="organize-smart-hub" aria-label="整理快捷操作">
      <div class="organize-smart-primary">
        <button
          type="button"
          class="btn-primary btn-sm organize-smart-btn-main"
          :disabled="smartLoading || aiLoading"
          @click="runSmartSuggest(true)"
        >
          {{ smartLoading ? '分析中…' : '⚡ 智能分析原文' }}
        </button>
        <span class="hint organize-smart-hint">秒级本地分析，无需等待 AI</span>
      </div>
      <div class="organize-smart-chips">
        <button
          v-for="p in AI_PRESETS"
          :key="p.key"
          type="button"
          class="organize-smart-chip"
          :disabled="aiLoading || smartLoading || (p.needsSelection && !selectedPersonName)"
          :title="p.hint"
          @click="runAiPreset(p)"
        >
          {{ p.label }}
        </button>
      </div>
      <div class="organize-inline-chat">
        <input
          v-model="chatInput"
          class="input organize-inline-chat-input"
          placeholder="或输入：如「把张三的儿子都连上」「王氏配给谁」"
          :disabled="aiLoading"
          @keydown.enter.prevent="sendInlineChat"
        />
        <button
          type="button"
          class="btn-primary btn-sm"
          :disabled="!chatInput.trim() || aiLoading"
          @click="sendInlineChat"
        >
          {{ aiLoading ? '…' : '问 AI' }}
        </button>
      </div>
    </section>

    <details v-if="!embedded && (textPreview || textPreviewLoading)" class="organize-text-preview ai-organize-details">
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
      <p v-else-if="smartLoading || aiLoading" class="hint">正在分析…</p>
      <p v-else class="hint">点上方「智能分析原文」或 AI 快捷按钮，关系建议会显示在下方卡片中。</p>
    </div>

    <div v-else class="ai-organize-preview organize-plan-panel">
      <div class="organize-plan-header">
        <strong>整理预览</strong>
        <div class="organize-plan-header-actions">
          <button type="button" class="btn-xs" :disabled="smartLoading" @click="runSmartSuggest(true)">重新分析</button>
          <button v-if="plan" type="button" class="btn-xs" @click="emit('dismiss')">清除</button>
        </div>
      </div>
      <p v-if="plan?.explanation" class="organize-plan-explanation">{{ plan.explanation }}</p>

      <div v-if="isEmptyGenealogy" class="organize-empty-hint organize-empty-hint--action">
        主谱为空，可直接将 AI 方案写入主谱（推荐「替换写入」）。
      </div>

      <div v-if="plan?.clean_slate && applyMode === 'merge' && memberCount > 0" class="organize-empty-hint organize-empty-hint--warn">
        本方案含「干净整理」标记，但您选择了<strong>插入合并</strong>：不会删除已有成员，仅新增/补全关系与字段。
        若要按方案替换整谱，请改用「替换写入主谱」。
      </div>

      <div v-if="suspiciousDuplicateAdd" class="organize-empty-hint organize-empty-hint--warn">
        检测到将新增 {{ diff?.persons_to_add?.length }} 人（主谱现有 {{ memberCount }} 人），可能是 AI 重复列出了已有成员。
        请在下方案例中删除多余「新增成员」，或改用「替换写入主谱」。
      </div>

      <div v-if="memberCount > 0 && planHasChanges(plan)" class="ai-organize-apply-mode">
        <span class="ai-organize-apply-mode-label">应用方式</span>
        <label class="ai-organize-mode-option ai-organize-mode-option--recommended">
          <input v-model="applyModeModel" type="radio" value="merge" />
          增量合并（插入到现有主谱）
        </label>
        <label class="ai-organize-mode-option">
          <input v-model="applyModeModel" type="radio" value="replace" />
          干净替换（替换写入主谱）
        </label>
        <p v-if="applyMode === 'replace' && (plan?.clean_slate || diff?.clean_slate)" class="hint ai-organize-mode-hint ai-organize-mode-hint--warn">
          干净替换：会移除未出现在方案中的旧关系与多余成员。
        </p>
        <p v-else-if="(plan?.clean_slate || diff?.clean_slate) && applyMode === 'merge'" class="hint ai-organize-mode-hint">
          插入合并：保留已有成员，从文字版补全生卒/简介并新增关系。
        </p>
        <p v-else class="hint ai-organize-mode-hint">{{ applyModeSummary() }}</p>
      </div>

      <div class="organize-apply-primary">
        <button
          type="button"
          class="btn-primary btn-sm"
          :disabled="applying"
          @click="applyPlan()"
        >
          {{ applying ? '写入中…' : applyMode === 'replace' ? '应用到主谱（替换）' : '应用到主谱（合并）' }}
        </button>
      </div>

      <div v-if="applyDiagnostics && (applyDiagnostics.unmatched_names?.length || applyDiagnostics.skipped_relations?.length)" class="organize-empty-hint organize-empty-hint--warn">
        <strong>上次应用未完全写入：</strong>
        <span v-if="applyDiagnostics.unmatched_names?.length">
          未匹配姓名 {{ applyDiagnostics.unmatched_names.join('、') }}
        </span>
        <span v-if="applyDiagnostics.skipped_relations?.length">
          ；跳过关系 {{ applyDiagnostics.skipped_relations.length }} 条
        </span>
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

      <div v-if="personsToAdd.length" class="organize-person-chips">
        <span class="organize-person-chips-label">将新增 {{ personsToAdd.length }} 人</span>
        <button
          v-for="name in personsToAdd"
          :key="'np-' + name"
          type="button"
          class="organize-person-chip"
          @click="removeNewPerson(name)"
        >
          {{ name }} ×
        </button>
      </div>

      <div v-if="relationCards.length" class="organize-relation-cards-wrap">
        <div class="organize-relation-cards-head">
          <strong>关系卡片（{{ relationCards.length }}）</strong>
          <span class="hint">点 × 移除误识别项</span>
        </div>
        <div class="organize-relation-cards">
          <article
            v-for="(r, j) in relationCards"
            :key="'rc-' + j + r.from + r.to"
            class="organize-relation-card"
            :class="r.type === 'spouse' ? 'organize-relation-card--spouse' : 'organize-relation-card--parent'"
          >
            <span class="organize-relation-card-from">{{ r.from }}</span>
            <span class="organize-relation-card-mid">{{ r.type === 'spouse' ? '配' : '→' }}</span>
            <span class="organize-relation-card-to">{{ r.to }}</span>
            <button type="button" class="organize-relation-card-remove" title="移除此关系" @click="removeRelationAt(j)">×</button>
          </article>
        </div>
      </div>

      <details v-if="planRelations.length" class="ai-organize-details organize-advanced-editor">
        <summary @click="showAdvancedEditor = !showAdvancedEditor">高级：逐条编辑关系</summary>
        <div v-if="showAdvancedEditor" class="organize-relation-editor">
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
      <details v-if="diff?.persons_to_update?.length" class="ai-organize-details">
        <summary>将更新成员资料（{{ diff.persons_to_update.length }}）</summary>
        <ul>
          <li v-for="(p, j) in diff.persons_to_update" :key="'u' + j">
            {{ p.name }}（{{ (p.fields || []).join('、') || '资料' }}）
          </li>
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

    </div>
  </div>
</template>
