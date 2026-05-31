<script setup lang="ts">
import { ref, computed, watch, onMounted, nextTick } from 'vue'
import { api, API_TIMEOUT_LONG } from '../utils/api'
import { compressImageFile } from '../utils/compressImage'
import { uploadImageUrl } from '../utils/uploadImageUrl'
import OcrTextWorkspace from './OcrTextWorkspace.vue'
import SourceTextPairView from './SourceTextPairView.vue'
import GenealogyOrganizePanel from './GenealogyOrganizePanel.vue'
import GenealogyReferenceView from './view/GenealogyReferenceView.vue'
import { resolveViewData } from '../utils/genealogyViewData'
import {
  RELATION_TEXT_FORMAT_HINT,
  RELATION_TEXT_FORMAT_TEMPLATE,
} from '../constants/relationTextFormat'
import { planHasChanges, type OrganizePlan, type OrganizeDiff } from '../types/organize'

const LIVE_PREVIEW_DEBOUNCE_MS = 550
const LIVE_PREVIEW_MIN_CHARS = 8

const props = defineProps<{
  familyId: string
  familyName?: string
  memberCount: number
  selectedPersonId?: string
  selectedPersonName?: string
  plan: OrganizePlan | null
  diff: OrganizeDiff | null
  applyMode: 'merge' | 'replace'
  cleanSlate: boolean
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
  refresh: []
  'select-person': [personId: string]
}>()

type WorkspaceStep = 'v1' | 'v2' | 'v3' | 'preview'

const workspaceStep = ref<WorkspaceStep>('v1')
const sourceVersions = ref<any[]>([])
const loadingVersions = ref(false)
const saving = ref(false)
const regeneratingOcr = ref(false)
const regeneratingRel = ref(false)
const versionRegenStatus = ref('')
const aiParseReady = ref(true)
const aiOcrReady = ref(true)
const analyzing = ref(false)
const aiOrganizing = ref(false)
const sourceImageDataUrl = ref('')
const suppressLivePreview = ref(false)
const livePreviewLoading = ref(false)
const livePreviewStatus = ref<'idle' | 'loading' | 'ready' | 'empty' | 'error'>('idle')
const livePreviewGraph = ref<{ persons: any[]; relations: any[] }>({ persons: [], relations: [] })
let livePreviewTimer: ReturnType<typeof setTimeout> | null = null
let livePreviewGen = 0
let livePreviewNeedsRerun = false

const ocrText = ref('')
const relationText = ref('')
const customText = ref('')
const editingRelationKind = ref<'relation_desc' | 'custom'>('relation_desc')

const v1 = computed(() => sourceVersions.value.find((v) => v.version_kind === 'ocr_raw') || null)
const v2 = computed(() => sourceVersions.value.find((v) => v.version_kind === 'relation_desc') || null)
const v3 = computed(() => sourceVersions.value.find((v) => v.version_kind === 'custom') || null)

const v1CharCount = computed(() => (ocrText.value || v1.value?.source_text || '').trim().length)
const v2CharCount = computed(() => (relationText.value || v2.value?.source_text || '').trim().length)
const v3CharCount = computed(() => (customText.value || v3.value?.source_text || '').trim().length)

function versionStatus(chars: number, hasPrereq = true): 'empty' | 'ready' | 'blocked' {
  if (!hasPrereq) return 'blocked'
  return chars > 0 ? 'ready' : 'empty'
}

const activeRelationText = computed({
  get: () => (editingRelationKind.value === 'custom' ? customText.value : relationText.value),
  set: (v: string) => {
    if (editingRelationKind.value === 'custom') customText.value = v
    else relationText.value = v
  },
})

const relationBaseline = computed(() => ocrText.value.trim() || relationText.value)

const imagePath = computed(() => v1.value?.image_path || '')
const imageUrl = computed(() => uploadImageUrl(imagePath.value, sourceImageDataUrl.value))
const v1HasImage = computed(() => Boolean(uploadImageUrl(imagePath.value, sourceImageDataUrl.value)))

const activeSourceVersionId = computed(() => {
  if (v3.value?.source_text?.trim()) return v3.value.id
  if (v2.value?.source_text?.trim()) return v2.value.id
  return v1.value?.id || undefined
})

const activeSourceVersionLabel = computed(() => {
  if (v3.value?.source_text?.trim()) return v3.value.label || '版本三 · 修正稿'
  if (v2.value?.source_text?.trim()) return v2.value.label || '版本二 · 关系描述'
  return v1.value?.label || '版本一 · OCR'
})

function notify(message: string, type: 'success' | 'error' | 'info' = 'info') {
  emit('notify', message, type)
}

function syncEditorsFromVersions() {
  ocrText.value = (v1.value?.source_text || '').trim()
  relationText.value = (v2.value?.source_text || '').trim()
  customText.value = (v3.value?.source_text || '').trim()
  if (customText.value.trim()) editingRelationKind.value = 'custom'
  else if (relationText.value.trim()) editingRelationKind.value = 'relation_desc'
}

async function loadVersions() {
  if (!props.familyId) return
  loadingVersions.value = true
  suppressLivePreview.value = true
  try {
    const res = await api('GET', `/families/${props.familyId}/source-versions`)
    sourceVersions.value = res.versions || []
    syncEditorsFromVersions()
  } catch {
    notify('加载原文版本失败', 'error')
  } finally {
    loadingVersions.value = false
    await nextTick()
    suppressLivePreview.value = false
    if (activeRelationText.value.trim().length >= LIVE_PREVIEW_MIN_CHARS) {
      scheduleLivePreview()
    }
  }
}

async function saveVersion(
  versionId: string | undefined,
  text: string,
  kind: 'ocr_raw' | 'relation_desc' | 'custom',
) {
  if (!props.familyId) return null
  saving.value = true
  try {
    if (versionId) {
      const res = await api('PUT', `/families/${props.familyId}/source-versions/${versionId}`, {
        source_text: text,
      })
      if (res.success) return res.version
    }
    const res = await api('POST', `/families/${props.familyId}/source-versions`, {
      source_text: text,
      version_kind: kind,
      label:
        kind === 'ocr_raw' ? '版本一 · OCR 原文' :
        kind === 'relation_desc' ? '版本二 · 关系描述' :
        '版本三 · 修正稿',
    })
    return res.version || null
  } catch {
    notify('保存失败', 'error')
    return null
  } finally {
    saving.value = false
  }
}

async function saveOcrText() {
  const version = await saveVersion(v1.value?.id, ocrText.value, 'ocr_raw')
  if (version) {
    await loadVersions()
    notify('OCR 原文已保存', 'success')
    emit('refresh')
  }
}

async function saveRelationText() {
  const version = await saveVersion(v2.value?.id, relationText.value, 'relation_desc')
  if (version) {
    await loadVersions()
    notify('版本二已保存', 'success')
    emit('refresh')
  }
}

async function saveActiveRelationAs(kind: 'relation_desc' | 'custom') {
  const text = activeRelationText.value.trim()
  if (!text) {
    notify('请先编写关系文字', 'info')
    workspaceStep.value = 'v2'
    return
  }
  if (kind === 'custom') customText.value = text
  else relationText.value = text
  const vid = kind === 'custom' ? v3.value?.id : v2.value?.id
  const version = await saveVersion(vid, text, kind)
  if (version) {
    await loadVersions()
    notify(kind === 'custom' ? '版本三已保存' : '版本二已保存', 'success')
    emit('refresh')
  }
}

async function onImageUpload(file: File) {
  try {
    const compressed = await compressImageFile(file)
    const reader = new FileReader()
    reader.onload = async (ev) => {
      sourceImageDataUrl.value = (ev.target?.result as string) || ''
      if (!props.familyId) return
      saving.value = true
      try {
        let vid = v1.value?.id
        if (!vid) {
          const created = await saveVersion(undefined, ocrText.value || ' ', 'ocr_raw')
          vid = created?.id
        }
        if (vid) {
          await api('PUT', `/families/${props.familyId}/source-versions/${vid}`, {
            image_base64: sourceImageDataUrl.value,
          })
          await loadVersions()
          sourceImageDataUrl.value = ''
          notify('扫描图已保存', 'success')
        }
      } catch {
        notify('保存原图失败', 'error')
      } finally {
        saving.value = false
      }
    }
    reader.readAsDataURL(compressed)
  } catch {
    notify('读取图片失败', 'error')
  }
}

async function imageUrlToBase64(url: string): Promise<string> {
  const res = await fetch(url)
  const blob = await res.blob()
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => {
      const data = (reader.result as string) || ''
      resolve(data.split(',')[1] || '')
    }
    reader.onerror = reject
    reader.readAsDataURL(blob)
  })
}

const isRegenerating = computed(() => regeneratingOcr.value || regeneratingRel.value)

async function loadAiStatus() {
  try {
    const res = await api('GET', '/ai/config')
    const ocrProvider = res.ocr?.provider || 'minimax'
    const parseProvider = res.parse?.provider || 'minimax'
    aiOcrReady.value = Boolean(res.keys?.[ocrProvider]?.configured)
    aiParseReady.value = Boolean(res.keys?.[parseProvider]?.configured)
  } catch {
    aiOcrReady.value = false
    aiParseReady.value = false
  }
}

function guardRegenerate(kind: 'ocr_raw' | 'relation_desc' | 'custom'): boolean {
  if (kind === 'ocr_raw') {
    if (!v1HasImage.value) {
      notify('版本一需要扫描图：请先上传族谱图片', 'info')
      workspaceStep.value = 'v1'
      return false
    }
    if (!aiOcrReady.value) {
      notify('OCR 模型未配置：请先在设置中填写 API Key', 'error')
      return false
    }
    return true
  }
  if (!ocrText.value.trim()) {
    notify('请先有版本一 OCR 文字（上传识别或粘贴后保存）', 'info')
    workspaceStep.value = 'v1'
    return false
  }
  if (!aiParseReady.value) {
    notify('关系解析模型未配置 API Key；将尝试本地规则生成（质量有限）', 'info')
  }
  return true
}

async function regenerateOcrFromImage() {
  if (!guardRegenerate('ocr_raw')) return
  if (!props.familyId) {
    notify('族谱未加载', 'error')
    return
  }
  regeneratingOcr.value = true
  versionRegenStatus.value = '正在调用 OCR 模型识别扫描图…（约 30–90 秒）'
  try {
    let base64 = ''
    if (sourceImageDataUrl.value) {
      base64 = sourceImageDataUrl.value.split(',')[1] || ''
    } else {
      base64 = await imageUrlToBase64(imageUrl.value)
    }
    if (!base64) {
      notify('读取原图失败', 'error')
      return
    }
    const res = await api('POST', '/agent/scan-ocr', { image: base64 }, API_TIMEOUT_LONG)
    if (!res.success) {
      notify(res.error || res.message || res.detail || 'OCR 失败', 'error')
      return
    }
    ocrText.value = (res.text || '').trim()
    await saveOcrText()
    notify(`版本一 OCR 已 AI 重生（${ocrText.value.length} 字）`, 'success')
  } catch (e: unknown) {
    const msg = (e as { message?: string })?.message
    notify(msg || 'OCR 请求失败', 'error')
  } finally {
    regeneratingOcr.value = false
    versionRegenStatus.value = ''
  }
}

async function generateRelationDesc(target: 'relation_desc' | 'custom' = 'relation_desc') {
  const kind = target === 'custom' ? 'custom' : 'relation_desc'
  if (!guardRegenerate(kind)) return
  regeneratingRel.value = true
  const isV3 = target === 'custom'
  const label = isV3 ? '版本三' : '版本二'
  versionRegenStatus.value = `正在调用 AI 整理${label}（含对话上下文与格式规则）…约 30–120 秒`
  try {
    const res = await api('POST', `/families/${props.familyId}/source-versions/regenerate-relation-desc`, {
      ocr_text: ocrText.value,
      target_kind: kind,
      previous_draft: isV3 ? customText.value : relationText.value,
    }, API_TIMEOUT_LONG)
    if (!res.success) {
      notify(res.message || res.detail || '生成失败', 'error')
      return
    }
    const text = (res.relation_description || '').trim()
    if (isV3) {
      customText.value = text
      editingRelationKind.value = 'custom'
    } else {
      relationText.value = text
      editingRelationKind.value = 'relation_desc'
    }
    await loadVersions()
    workspaceStep.value = isV3 ? 'v3' : 'v2'
    if (res.used_ai) {
      const ctx = res.context_turns ? `，已参考 ${res.context_turns} 条对话` : ''
      notify(res.message || `${label} 已用 AI 重生（${text.length} 字${ctx}）`, 'success')
    } else {
      notify(
        res.fallback_reason || res.message || `${label} 已用本地规则生成，请核对；建议在设置中配置 API Key`,
        'info',
      )
    }
    scheduleLivePreview()
  } catch (e: unknown) {
    const msg = (e as { message?: string })?.message
    notify(msg || 'AI 生成关系描述失败', 'error')
  } finally {
    regeneratingRel.value = false
    versionRegenStatus.value = ''
  }
}

async function regenerateVersion(kind: 'ocr_raw' | 'relation_desc' | 'custom') {
  if (isRegenerating.value) {
    notify('上一项 AI 任务仍在进行，请稍候…', 'info')
    return
  }
  if (kind === 'ocr_raw') {
    workspaceStep.value = 'v1'
    await regenerateOcrFromImage()
    return
  }
  if (kind === 'relation_desc') {
    workspaceStep.value = 'v2'
    await generateRelationDesc('relation_desc')
    return
  }
  workspaceStep.value = 'v3'
  await generateRelationDesc('custom')
}

function focusVersionStep(kind: 'ocr_raw' | 'relation_desc' | 'custom') {
  if (kind === 'ocr_raw') {
    workspaceStep.value = 'v1'
    return
  }
  if (kind === 'custom') {
    workspaceStep.value = 'v3'
    editingRelationKind.value = 'custom'
    return
  }
  workspaceStep.value = 'v2'
  editingRelationKind.value = 'relation_desc'
}

function insertRelationTemplate() {
  if (!activeRelationText.value.trim()) {
    activeRelationText.value = RELATION_TEXT_FORMAT_TEMPLATE
  } else {
    activeRelationText.value = `${activeRelationText.value.trim()}\n\n${RELATION_TEXT_FORMAT_TEMPLATE}`
  }
  scheduleLivePreview()
}

function scheduleLivePreview() {
  if (suppressLivePreview.value || loadingVersions.value) return
  if (livePreviewLoading.value) {
    livePreviewNeedsRerun = true
    return
  }
  if (livePreviewTimer) clearTimeout(livePreviewTimer)
  livePreviewTimer = setTimeout(() => {
    livePreviewTimer = null
    void runLivePreview({ silent: true })
  }, LIVE_PREVIEW_DEBOUNCE_MS)
}

async function runLivePreview(opts?: { silent?: boolean; switchToPreview?: boolean }) {
  const text = activeRelationText.value.trim()
  if (!text) {
    livePreviewStatus.value = 'empty'
    livePreviewGraph.value = { persons: [], relations: [] }
    if (!opts?.silent) {
      notify('请先编写关系描述文字', 'info')
      workspaceStep.value = 'v2'
    }
    return
  }
  if (text.length < LIVE_PREVIEW_MIN_CHARS) {
    livePreviewStatus.value = 'idle'
    return
  }

  const gen = ++livePreviewGen
  livePreviewLoading.value = true
  livePreviewStatus.value = 'loading'
  analyzing.value = !opts?.silent

  try {
    const res = await api('POST', `/families/${props.familyId}/smart-suggest`, {
      source_text: text,
      source_version_label: activeSourceVersionLabel.value || '编辑稿',
    })
    if (gen !== livePreviewGen) return

    if (!res.success) {
      livePreviewStatus.value = 'error'
      if (!opts?.silent) notify(res.error || res.detail || '分析失败', 'error')
      return
    }

    const preview = res.preview || {}
    livePreviewGraph.value = resolveViewData({
      persons: preview.persons || [],
      relations: preview.relations || [],
      structuredText: text,
    })

    if (res.plan) {
      emit('load-plan', { plan: res.plan, diff: res.diff ?? null })
      const hasChanges = planHasChanges(res.plan)
      livePreviewStatus.value = hasChanges ? 'ready' : 'empty'
      if (opts?.switchToPreview && hasChanges) workspaceStep.value = 'preview'
      if (!opts?.silent) {
        const st = res.stats || {}
        if (hasChanges) {
          notify(`预览就绪：+${st.persons_to_add || 0} 人 · +${st.relations_to_add || 0} 关系`, 'success')
        } else {
          notify(res.plan.explanation || '与主谱已基本一致', 'info')
        }
      }
    } else {
      livePreviewStatus.value = 'empty'
    }
  } catch {
    if (gen === livePreviewGen) livePreviewStatus.value = 'error'
    if (!opts?.silent) notify('预览失败，请确认后端已启动', 'error')
  } finally {
    if (gen === livePreviewGen) {
      livePreviewLoading.value = false
      analyzing.value = false
      if (livePreviewNeedsRerun) {
        livePreviewNeedsRerun = false
        scheduleLivePreview()
      }
    }
  }
}

async function analyzeFromRelationText() {
  await saveRelationText()
  await runLivePreview({ silent: false, switchToPreview: true })
}

const AGENT_ORGANIZE_HINTS: Array<{ pattern: RegExp; prompt: string; cleanSlate?: boolean }> = [
  {
    pattern: /整理(?:族谱|全谱|主谱)|从原文整理|干净整理/,
    prompt: '请根据附带的族谱原文，干净整理出完整主谱：提取所有人物、世代与父子/配偶关系，给出可应用的整理方案。',
    cleanSlate: true,
  },
  {
    pattern: /补全|缺失|缺少/,
    prompt: '对比原文与当前主谱，只补充缺失的父子/配偶关系；已有成员不要重复添加到 new_persons。',
  },
  {
    pattern: /配偶|配\s*谁|妻|夫/,
    prompt: '重点从原文中整理配偶关系（配、妻、夫），补全 relations_add，尽量不改已有父子结构。',
  },
]

async function runAiOrganize(message: string, cleanSlate = false) {
  if (!props.familyId || aiOrganizing.value) return
  aiOrganizing.value = true
  try {
    const text = activeRelationText.value.trim() || ocrText.value.trim()
    const res = await api(
      'POST',
      `/families/${props.familyId}/ai-organize`,
      {
        message,
        include_source: Boolean(text),
        source_text: text || undefined,
        source_version_id: activeSourceVersionId.value,
        clean_slate: cleanSlate,
        refresh_context: true,
      },
      API_TIMEOUT_LONG,
    )
    if (!res.success) {
      notify(res.explanation || res.error || res.detail || 'AI 整理失败', 'error')
      return false
    }
    if (res.plan) {
      emit('load-plan', { plan: res.plan, diff: res.diff ?? null })
      if (res.preview) {
        livePreviewGraph.value = resolveViewData({
          persons: res.preview.persons || [],
          relations: res.preview.relations || [],
          structuredText: text,
        })
      }
      workspaceStep.value = 'preview'
      livePreviewStatus.value = planHasChanges(res.plan) ? 'ready' : 'empty'
      notify('AI 方案已生成，请核对预览后写入主谱', 'success')
      return true
    }
    notify(res.explanation || '未产生可应用方案', 'info')
    return false
  } catch {
    notify('AI 整理请求失败', 'error')
    return false
  } finally {
    aiOrganizing.value = false
  }
}

/** 对话 / 快捷语触发整理 */
async function runFromAgent(message?: string) {
  await loadVersions()
  const msg = (message || '').trim()

  const regenOcr = /重新(?:识别|OCR|扫描)|再次(?:生成|识别).*(?:完整|OCR|原文)|OCR(?:不对|错了)|请再次生成完整/i
  const regenRel = /重新(?:生成|整理).*(?:关系|版本二)|关系(?:描述|文字)(?:不对|错了)|再次生成|自动.*填/i
  if (regenOcr.test(msg)) {
    await regenerateOcrFromImage()
    return
  }
  if (regenRel.test(msg)) {
    await generateRelationDesc()
    return
  }

  if (!ocrText.value.trim() && !activeRelationText.value.trim()) {
    workspaceStep.value = 'v1'
    notify('请先在整理页上传扫描图或粘贴 OCR 原文', 'info')
    return
  }

  const aiHint = AGENT_ORGANIZE_HINTS.find((h) => h.pattern.test(msg))
  if (aiHint) {
    const ok = await runAiOrganize(aiHint.prompt, Boolean(aiHint.cleanSlate))
    if (ok) return
  }

  if (!activeRelationText.value.trim() && ocrText.value.trim()) {
    await generateRelationDesc()
  }

  workspaceStep.value = 'preview'
  await runLivePreview({ silent: false, switchToPreview: true })
}

function focusStep(step: WorkspaceStep) {
  workspaceStep.value = step
}

async function reloadFromServer() {
  await loadVersions()
  if (activeRelationText.value.trim()) {
    scheduleLivePreview()
  } else if (ocrText.value.trim()) {
    workspaceStep.value = 'v2'
  } else {
    workspaceStep.value = 'v1'
  }
}

async function saveCustomText() {
  const version = await saveVersion(v3.value?.id, customText.value, 'custom')
  if (version) {
    await loadVersions()
    notify('版本三已保存', 'success')
    emit('refresh')
  }
}

defineExpose({
  runFromAgent,
  focusStep,
  runLivePreview,
  regenerateOcr: regenerateOcrFromImage,
  regenerateRelation: () => generateRelationDesc('relation_desc'),
  reloadFromServer,
})

watch(() => props.familyId, () => { void loadVersions() }, { immediate: true })

watch(workspaceStep, (step) => {
  if (step === 'v2') editingRelationKind.value = 'relation_desc'
  if (step === 'v3') editingRelationKind.value = 'custom'
})

watch(relationText, () => {
  if (workspaceStep.value === 'v2') scheduleLivePreview()
})

watch(customText, () => {
  if (workspaceStep.value === 'v3') scheduleLivePreview()
})

onMounted(() => {
  void loadAiStatus()
  if (!ocrText.value.trim() && !relationText.value.trim()) workspaceStep.value = 'v1'
  else if (!activeRelationText.value.trim()) workspaceStep.value = 'v2'
  else scheduleLivePreview()
})
</script>

<template>
  <div class="organize-workspace">
    <header class="organize-workspace-head">
      <div>
        <h3 class="organize-workspace-title">整理组谱</h3>
        <p class="hint organize-workspace-sub">
          分步整理：扫描 OCR → 关系描述 → 可选修正 → 预览写入。每步只对比相邻版本。
        </p>
      </div>
      <div class="organize-workspace-steps" role="tablist">
        <button
          type="button"
          role="tab"
          class="organize-workspace-step"
          :class="{ active: workspaceStep === 'v1' }"
          @click="workspaceStep = 'v1'"
        >
          ① 扫描 OCR
        </button>
        <button
          type="button"
          role="tab"
          class="organize-workspace-step"
          :class="{ active: workspaceStep === 'v2' }"
          :disabled="!v1CharCount"
          @click="workspaceStep = 'v2'"
        >
          ② 关系描述
        </button>
        <button
          type="button"
          role="tab"
          class="organize-workspace-step"
          :class="{ active: workspaceStep === 'v3' }"
          :disabled="!v2CharCount"
          @click="workspaceStep = 'v3'"
        >
          ③ 修正稿
          <span class="organize-step-optional">可选</span>
        </button>
        <button
          type="button"
          role="tab"
          class="organize-workspace-step"
          :class="{ active: workspaceStep === 'preview' }"
          :disabled="!v2CharCount && !v3CharCount"
          @click="workspaceStep = 'preview'"
        >
          ④ 预览写入
        </button>
      </div>
    </header>

    <div v-if="versionRegenStatus" class="organize-regen-banner" role="status">
      <span class="organize-regen-banner-spinner" aria-hidden="true" />
      {{ versionRegenStatus }}
    </div>

    <div
      v-else-if="!aiParseReady || !aiOcrReady"
      class="organize-regen-banner organize-regen-banner--warn"
    >
      {{ !aiOcrReady ? 'OCR 模型未配置 API Key · ' : '' }}
      {{ !aiParseReady ? '关系解析模型未配置 · 重生将降级为本地规则' : '' }}
      <button type="button" class="btn-xs" @click="emit('notify', '请在右上角打开设置配置 API Key', 'info')">
        去设置
      </button>
    </div>

    <div v-if="loadingVersions" class="organize-workspace-loading">加载原文…</div>

    <div v-else class="organize-workspace-single">
      <!-- ① 版本一：原图 + OCR（仅相邻对照，不含其它版本） -->
      <section
        v-show="workspaceStep === 'v1'"
        class="organize-workspace-pane organize-workspace-pane--v1"
      >
        <div class="organize-workspace-col-head">
          <strong>版本一 · 扫描图 ↔ OCR 原文</strong>
          <span class="hint">{{ v1CharCount ? `${v1CharCount} 字` : '上传图片后 AI 识别或手贴文字' }}</span>
        </div>
        <div class="organize-workspace-col-body">
          <OcrTextWorkspace
            v-model="ocrText"
            :image-path="imagePath"
            :image-preview="sourceImageDataUrl"
            :view-title="familyName || '族谱'"
            :prefer-pair-edit="Boolean(imageUrl)"
            minimal
            compact
            @upload-image="onImageUpload"
          />
        </div>
        <div class="organize-workspace-col-actions">
          <button type="button" class="btn-xs btn-secondary" :disabled="isRegenerating" @click="regenerateOcrFromImage">
            {{ regeneratingOcr ? 'AI 识别中…' : 'AI 重生 OCR' }}
          </button>
          <button type="button" class="btn-xs btn-primary" :disabled="saving" @click="saveOcrText">
            {{ saving ? '保存中…' : '保存版本一' }}
          </button>
          <button type="button" class="btn-xs" :disabled="!ocrText.trim()" @click="workspaceStep = 'v2'">
            下一步：关系描述 →
          </button>
        </div>
      </section>

      <!-- ② 版本二：仅与版本一对照 -->
      <section
        v-show="workspaceStep === 'v2'"
        class="organize-workspace-pane organize-workspace-pane--v2"
      >
        <div class="organize-workspace-col-head">
          <strong>版本二 · 关系描述</strong>
          <span class="hint">左 OCR 原文 · 右关系描述（只对比 1↔2）</span>
          <span v-if="livePreviewLoading" class="organize-live-status organize-live-status--loading">预览更新中…</span>
          <span v-else-if="livePreviewStatus === 'ready'" class="organize-live-status organize-live-status--ready">预览已同步</span>
        </div>
        <div class="organize-workspace-col-body">
          <SourceTextPairView
            v-model="relationText"
            :baseline-text="ocrText"
            baseline-label="版本一 · OCR 原文（只读）"
            right-label="版本二 · 关系描述"
            right-placeholder="对照 OCR 整理人物关系…"
          />
        </div>
        <div class="organize-workspace-col-actions organize-workspace-col-actions--wrap">
          <button type="button" class="btn-xs btn-secondary" :disabled="isRegenerating" @click="generateRelationDesc('relation_desc')">
            {{ regeneratingRel ? 'AI 生成中…' : 'AI 从版本一生成' }}
          </button>
          <button type="button" class="btn-xs" @click="insertRelationTemplate">插格式样板</button>
          <button type="button" class="btn-xs btn-primary" :disabled="saving" @click="saveRelationText">
            保存版本二
          </button>
          <button type="button" class="btn-xs" @click="workspaceStep = 'v3'">可选：修正稿 →</button>
          <button type="button" class="btn-xs btn-primary organize-workspace-analyze-btn" :disabled="analyzing" @click="analyzeFromRelationText">
            {{ analyzing ? '分析中…' : '刷新预览' }}
          </button>
        </div>
      </section>

      <!-- ③ 版本三：仅与版本二对照 -->
      <section
        v-show="workspaceStep === 'v3'"
        class="organize-workspace-pane organize-workspace-pane--v3"
      >
        <div class="organize-workspace-col-head">
          <strong>版本三 · 修正稿（可选）</strong>
          <span class="hint">左版本二 · 右修正稿（只对比 2↔3）</span>
        </div>
        <div class="organize-workspace-col-body">
          <SourceTextPairView
            v-model="customText"
            :baseline-text="relationText"
            baseline-label="版本二 · 关系描述（只读）"
            right-label="版本三 · 修正稿"
            right-placeholder="校对定稿，优先级高于版本二…"
          />
        </div>
        <div class="organize-workspace-col-actions organize-workspace-col-actions--wrap">
          <button type="button" class="btn-xs" @click="customText = relationText || customText">从版本二复制</button>
          <button type="button" class="btn-xs btn-secondary" :disabled="isRegenerating" @click="generateRelationDesc('custom')">
            AI 重生版本三
          </button>
          <button type="button" class="btn-xs btn-primary" :disabled="saving" @click="saveCustomText">
            保存版本三
          </button>
          <button type="button" class="btn-xs" @click="workspaceStep = 'preview'">去预览写入 →</button>
        </div>
      </section>

      <!-- ④ 预览写入 -->
      <section
        v-show="workspaceStep === 'preview'"
        class="organize-workspace-pane organize-workspace-pane--preview"
      >
        <div class="organize-workspace-col-head">
          <strong>预览 · 写入主谱</strong>
          <span class="hint">点选成员高亮相关关系；改文字后自动更新</span>
        </div>
        <div class="organize-workspace-col-body organize-workspace-col-body--scroll">
          <div v-if="livePreviewGraph.persons.length" class="organize-live-graph">
            <div class="organize-live-graph-label">谱页预览（点人高亮关系）</div>
            <GenealogyReferenceView
              mode="page"
              :persons="livePreviewGraph.persons"
              :relations="livePreviewGraph.relations"
              :structured-text="activeRelationText"
              :title="familyName || '族谱'"
              :selected-person-id="selectedPersonId"
              :fill="false"
              unbounded
              @select="emit('select-person', $event)"
            />
          </div>
          <div v-else-if="livePreviewLoading" class="organize-live-graph-empty hint">正在解析关系文字…</div>
          <div v-else class="organize-live-graph-empty hint">请先在「关系描述」步骤编写文字</div>
          <GenealogyOrganizePanel
            embedded
            :family-id="familyId"
            :member-count="memberCount"
            :selected-person-id="selectedPersonId"
            :selected-person-name="selectedPersonName || ''"
            :source-version-id="activeSourceVersionId"
            :source-version-label="activeSourceVersionLabel"
            :source-text="activeRelationText"
            :plan="plan"
            :diff="diff"
            :apply-mode="applyMode"
            :clean-slate="cleanSlate"
            @update:apply-mode="emit('update:applyMode', $event)"
            @update:clean-slate="emit('update:cleanSlate', $event)"
            @update:plan="emit('update:plan', $event)"
            @load-plan="emit('load-plan', $event)"
            @plan-edited="emit('plan-edited')"
            @applied="emit('applied', $event)"
            @cleared="emit('cleared')"
            @dismiss="emit('dismiss')"
            @notify="(msg, type) => notify(msg, type || 'info')"
          />
        </div>
      </section>
    </div>
  </div>
</template>
