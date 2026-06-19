<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { uploadImageUrl } from '../utils/uploadImageUrl'
import SourceImagePanel from './SourceImagePanel.vue'
import {
  type NameAnnotation,
  NAME_DRAG_MIME,
  annotationPayload,
  buildTextSegments,
  makeAnnotationId,
  mergeAnnotations,
  remapAnnotations,
  renameAnnotationInText,
} from '../utils/ocrAnnotations'
import {
  isValidPersonNameForMark,
  normalizeSelectedName,
  personNameHint,
  PERSON_NAME_MAX_LEN,
} from '../utils/personName'
import { API_BASE } from '../main'
import GenealogyCardTreeView from './view/GenealogyCardTreeView.vue'
import SourceSilkwormPageView from './view/SourceSilkwormPageView.vue'

export type SourceViewMode = 'pair' | 'page' | 'card' | 'edit'

const props = withDefaults(
  defineProps<{
    modelValue: string
    annotations?: NameAnnotation[]
    imagePreview?: string
    imagePath?: string
    imagePreviews?: string[]
    imagePaths?: string[]
    compact?: boolean
    relationLinkFrom?: string | null
    previewPersons?: any[]
    previewRelations?: any[]
    structuredText?: string
    viewTitle?: string
    /** 版本一 OCR 对照编辑：有图时默认打开对照模式 */
    preferPairEdit?: boolean
    /** 扫描/录入流程：隐藏谱页卡片等次要 Tab，界面更简洁 */
    minimal?: boolean
  }>(),
  {
    annotations: () => [],
    imagePreview: '',
    imagePath: '',
    imagePreviews: () => [],
    imagePaths: () => [],
    compact: false,
    relationLinkFrom: null,
    previewPersons: () => [],
    previewRelations: () => [],
    structuredText: '',
    viewTitle: '族谱',
    preferPairEdit: true,
    minimal: false,
  },
)

const emit = defineEmits<{
  'update:modelValue': [value: string]
  'update:annotations': [value: NameAnnotation[]]
  'upload-image': [file: File]
  'add-person': [payload: { name: string; source: string; start?: number; end?: number }]
  'set-link-from': [name: string]
  'create-link': [payload: { from: string; to: string }]
  'clear-link': []
}>()

const textareaRef = ref<HTMLTextAreaElement | null>(null)
const aiLoading = ref(false)
const copyHint = ref('')
const selectionHint = ref('')
const viewMode = ref<SourceViewMode>('edit')
const imageInputRef = ref<HTMLInputElement | null>(null)
const imagePanelExpanded = ref(false)

const imageSrc = computed(() => uploadImageUrl(props.imagePath, props.imagePreview))

const hasAnyImage = computed(() => {
  if (props.imagePaths?.length || props.imagePreviews?.length) return true
  return Boolean(imageSrc.value)
})

const showPairMode = computed(() => hasAnyImage.value || props.preferPairEdit)

function onImageFileChange(e: Event) {
  const file = (e.target as HTMLInputElement).files?.[0]
  if (file) emit('upload-image', file)
  if (imageInputRef.value) imageInputRef.value.value = ''
}
const dragOverTray = ref(false)
const editingAnnId = ref<string | null>(null)
const editingAnnName = ref('')
const selectedRange = ref<{ start: number; end: number; text: string } | null>(null)

const localText = computed({
  get: () => props.modelValue,
  set: (v: string) => emit('update:modelValue', v),
})

const localAnnotations = computed({
  get: () => props.annotations,
  set: (v: NameAnnotation[]) => emit('update:annotations', v),
})

const textSegments = computed(() => buildTextSegments(localText.value, localAnnotations.value))

const annotationById = computed(() => {
  const map = new Map<string, NameAnnotation>()
  for (const a of localAnnotations.value) map.set(a.id, a)
  return map
})

const uniqueNames = computed(() => {
  const seen = new Set<string>()
  const out: NameAnnotation[] = []
  for (const a of localAnnotations.value) {
    const key = `${a.name}@${a.start}`
    if (seen.has(key)) continue
    seen.add(key)
    out.push(a)
  }
  return out
})

const canMarkSelection = computed(() => {
  const t = normalizeSelectedName(selectedRange.value?.text || '')
  return isValidPersonNameForMark(t)
})

watch(localText, (next, prev) => {
  if (next === prev || !localAnnotations.value.length) return
  localAnnotations.value = remapAnnotations(next, localAnnotations.value)
})

function readSelection() {
  const ta = textareaRef.value
  if (!ta) return
  const start = ta.selectionStart
  const end = ta.selectionEnd
  if (start === end) {
    selectedRange.value = null
    selectionHint.value = ''
    return
  }
  const text = localText.value.slice(start, end).trim()
  selectedRange.value = { start, end, text }
  selectionHint.value = text ? personNameHint(text) + ' — 可点「变为姓名标签」或双击' : ''
}

function markRange(start: number, end: number) {
  const name = normalizeSelectedName(localText.value.slice(start, end))
  if (!isValidPersonNameForMark(name)) {
    selectionHint.value = `请选中 1–${PERSON_NAME_MAX_LEN} 个汉字（如「王五」两字全名，或单字名「五」）`
    return false
  }
  const ann: NameAnnotation = {
    id: makeAnnotationId(name, start, end),
    name,
    start,
    end,
    source: 'manual',
  }
  localAnnotations.value = mergeAnnotations(localAnnotations.value, [ann])
  selectionHint.value = `已生成标签「${name}」，可拖动到族谱树`
  return true
}

function markSelectionAsName() {
  const ta = textareaRef.value
  if (!ta) return
  markRange(ta.selectionStart, ta.selectionEnd)
}

function onTextareaDblClick() {
  readSelection()
  if (canMarkSelection.value && selectedRange.value) {
    markRange(selectedRange.value.start, selectedRange.value.end)
  }
}

async function aiExtractNames() {
  if (!localText.value.trim()) return
  aiLoading.value = true
  try {
    const res = await fetch(`${API_BASE}/ocr/extract-names`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text: localText.value }),
    })
    const data = await res.json()
    if (!data.success) {
      selectionHint.value = data.error || data.detail || '识别失败'
      return
    }
    const incoming = (data.annotations || []) as NameAnnotation[]
    localAnnotations.value = mergeAnnotations(localAnnotations.value, incoming)
    selectionHint.value = `AI 识别 ${incoming.length} 处姓名，标签可拖动`
  } catch {
    selectionHint.value = '识别请求失败'
  } finally {
    aiLoading.value = false
  }
}

async function copyAllText() {
  try {
    await navigator.clipboard.writeText(localText.value)
    copyHint.value = '已复制'
    window.setTimeout(() => { copyHint.value = '' }, 1600)
  } catch {
    copyHint.value = '复制失败'
  }
}

function onDragStart(e: DragEvent, ann: NameAnnotation) {
  e.dataTransfer?.setData(NAME_DRAG_MIME, annotationPayload(ann))
  e.dataTransfer?.setData('text/plain', ann.name)
  if (e.dataTransfer) e.dataTransfer.effectAllowed = 'copy'
}

function onChipClick(ann: NameAnnotation, e: MouseEvent) {
  if (props.relationLinkFrom) {
    if (props.relationLinkFrom === ann.name) {
      emit('clear-link')
      return
    }
    emit('create-link', { from: props.relationLinkFrom, to: ann.name })
    return
  }
  if (e.shiftKey) {
    emit('set-link-from', ann.name)
    selectionHint.value = `关系起点「${ann.name}」，再 Shift+点击另一姓名建立父子关系`
    return
  }
  emit('add-person', {
    name: ann.name,
    source: ann.source,
    start: ann.start,
    end: ann.end,
  })
}

function onMarkClick(annotationId?: string) {
  const ann = annotationId ? annotationById.value.get(annotationId) : null
  if (ann) onChipClick(ann, new MouseEvent('click'))
}

function onMarkDragStart(e: DragEvent, annotationId?: string) {
  const ann = annotationId ? annotationById.value.get(annotationId) : null
  if (ann) onDragStart(e, ann)
}

function onTrayDragOver(e: DragEvent) {
  if (e.dataTransfer?.types.includes(NAME_DRAG_MIME)) {
    e.preventDefault()
    dragOverTray.value = true
  }
}

function onTrayDragLeave() {
  dragOverTray.value = false
}

function onTrayDrop(e: DragEvent) {
  dragOverTray.value = false
  const raw = e.dataTransfer?.getData(NAME_DRAG_MIME)
  if (!raw) return
  try {
    emit('add-person', JSON.parse(raw))
  } catch {
    /* ignore */
  }
}

function removeAnnotation(id: string) {
  localAnnotations.value = localAnnotations.value.filter((a) => a.id !== id)
  if (editingAnnId.value === id) {
    editingAnnId.value = null
    editingAnnName.value = ''
  }
}

function startEditAnnotation(ann: NameAnnotation) {
  editingAnnId.value = ann.id
  editingAnnName.value = ann.name
}

function commitEditAnnotation() {
  const id = editingAnnId.value
  if (!id) return
  const next = editingAnnName.value.trim()
  if (!next) {
    removeAnnotation(id)
    editingAnnId.value = null
    return
  }
  const { text, annotations } = renameAnnotationInText(localText.value, localAnnotations.value, id, next)
  localText.value = text
  localAnnotations.value = annotations
  editingAnnId.value = null
  editingAnnName.value = ''
  selectionHint.value = `已修正姓名为「${next}」`
}
</script>

<template>
  <div class="ocr-text-workspace" :class="{ compact, 'ocr-text-workspace--pair': viewMode === 'pair' }">
    <div class="ocr-text-main">
      <div class="ocr-text-toolbar ocr-view-toolbar">
        <div class="ocr-view-mode-group" role="tablist" aria-label="查看模式">
          <button
            v-if="showPairMode"
            type="button"
            role="tab"
            class="ocr-view-mode-btn"
            :class="{ active: viewMode === 'pair' }"
            @click="viewMode = 'pair'"
          >
            对照
          </button>
          <template v-if="!minimal">
            <button type="button" role="tab" class="ocr-view-mode-btn" :class="{ active: viewMode === 'page' }" @click="viewMode = 'page'">谱页</button>
            <button type="button" role="tab" class="ocr-view-mode-btn" :class="{ active: viewMode === 'card' }" @click="viewMode = 'card'">卡片</button>
          </template>
          <button type="button" role="tab" class="ocr-view-mode-btn" :class="{ active: viewMode === 'edit' }" @click="viewMode = 'edit'">纯文字</button>
        </div>
        <template v-if="viewMode === 'pair' || viewMode === 'edit'">
          <button type="button" class="btn-xs" @click="copyAllText">{{ copyHint || '复制全文' }}</button>
          <button type="button" class="btn-xs btn-primary" :disabled="!canMarkSelection" @click="markSelectionAsName">变为姓名标签</button>
          <button type="button" class="btn-xs" :disabled="aiLoading || !localText.trim()" @click="aiExtractNames">{{ aiLoading ? 'AI 识别中…' : 'AI 识别人名' }}</button>
          <button type="button" class="btn-xs" @click="imageInputRef?.click()">{{ hasAnyImage ? '更换原图' : '上传原图' }}</button>
          <input ref="imageInputRef" type="file" accept="image/*" class="ocr-image-file-input" @change="onImageFileChange" />
        </template>
        <span v-if="(viewMode === 'pair' || viewMode === 'edit') && selectionHint" class="ocr-text-hint">{{ selectionHint }}</span>
      </div>

      <div v-if="viewMode === 'pair'" class="ocr-pair-split" :class="{ 'ocr-pair-split--image-open': imagePanelExpanded && hasAnyImage }">
        <SourceImagePanel
          v-if="hasAnyImage"
          v-model:expanded="imagePanelExpanded"
          :image-path="imagePath"
          :image-paths="imagePaths"
          :image-preview="imagePreview"
          :image-previews="imagePreviews"
          alt="版本一对照原图"
          compact
        />
        <div class="ocr-pair-editor">
          <p class="ocr-text-tip ocr-pair-tip">左侧原图与右侧<strong>版本一 OCR 原文</strong>一一对应校对；改字后请点「保存原文」。</p>
          <textarea
            ref="textareaRef"
            v-model="localText"
            class="ocr-text-editor ocr-text-editor--pair"
            placeholder="版本一 OCR 原文，对照左侧图片逐行修改…"
            spellcheck="false"
            @mouseup="readSelection"
            @keyup="readSelection"
            @dblclick="onTextareaDblClick"
          />
          <div v-if="textSegments.length" class="ocr-text-preview">
            <div class="ocr-text-preview-label">标注预览（高亮姓名可拖动）</div>
            <div class="ocr-text-preview-body">
              <template v-for="seg in textSegments" :key="seg.key">
                <mark
                  v-if="seg.type === 'name'"
                  class="name-highlight name-highlight-draggable"
                  draggable="true"
                  :title="'拖动「' + seg.text + '」到族谱'"
                  @dragstart="onMarkDragStart($event, seg.annotationId)"
                  @click="onMarkClick(seg.annotationId)"
                >{{ seg.text }}</mark>
                <span v-else>{{ seg.text }}</span>
              </template>
            </div>
          </div>
        </div>
      </div>

      <SourceSilkwormPageView
        v-else-if="viewMode === 'page'"
        :persons="previewPersons"
        :relations="previewRelations"
        :structured-text="structuredText"
        :raw-text="localText"
        :image-preview="imagePreview"
        :title="viewTitle"
      />

      <GenealogyCardTreeView
        v-else-if="viewMode === 'card'"
        :persons="previewPersons"
        :relations="previewRelations"
        :structured-text="structuredText"
        :raw-text="localText"
        :title="viewTitle"
      />

      <template v-else>
        <SourceImagePanel
          v-if="hasAnyImage"
          v-model:expanded="imagePanelExpanded"
          :image-path="imagePath"
          :image-paths="imagePaths"
          :image-preview="imagePreview"
          :image-previews="imagePreviews"
          alt="版本一对照原图"
          compact
        />
        <p class="ocr-text-tip">提示：可选 1–4 字 — 两字全名（姓+单字名如「王五」）、单字名、或复姓；双击或点「变为姓名标签」</p>
        <textarea
          ref="textareaRef"
          v-model="localText"
          class="ocr-text-editor"
          placeholder="OCR 文字可编辑。可选 1–4 字：两字姓名（如王五）、单字名、复姓；选中后双击标注。"
          spellcheck="false"
          @mouseup="readSelection"
          @keyup="readSelection"
          @dblclick="onTextareaDblClick"
        />
        <div v-if="textSegments.length" class="ocr-text-preview">
          <div class="ocr-text-preview-label">标注预览（高亮姓名可拖动）</div>
          <div class="ocr-text-preview-body">
            <template v-for="seg in textSegments" :key="seg.key">
              <mark
                v-if="seg.type === 'name'"
                class="name-highlight name-highlight-draggable"
                draggable="true"
                :title="'拖动「' + seg.text + '」到族谱'"
                @dragstart="onMarkDragStart($event, seg.annotationId)"
                @click="onMarkClick(seg.annotationId)"
              >{{ seg.text }}</mark>
              <span v-else>{{ seg.text }}</span>
            </template>
          </div>
        </div>
      </template>
    </div>

    <div
      v-if="viewMode === 'pair' || viewMode === 'edit'"
      class="ocr-name-tray"
      :class="{ 'drag-over': dragOverTray }"
      @dragover="onTrayDragOver"
      @dragleave="onTrayDragLeave"
      @drop="onTrayDrop"
    >
      <div class="ocr-name-tray-header">
        <strong>姓名标签</strong>
        <span class="hint">{{ uniqueNames.length }} 个</span>
        <span v-if="relationLinkFrom" class="link-mode-badge">连线中：{{ relationLinkFrom }}</span>
      </div>
      <div v-if="!uniqueNames.length" class="ocr-name-tray-empty">选中文字生成标签；点 ✎ 可改错字姓名</div>
      <div v-else class="ocr-name-chips">
        <template v-for="ann in uniqueNames" :key="ann.id">
          <div v-if="editingAnnId === ann.id" class="name-chip-edit">
            <input
              v-model="editingAnnName"
              class="name-chip-input"
              maxlength="8"
              @keydown.enter.prevent="commitEditAnnotation"
              @keydown.esc.prevent="editingAnnId = null"
            />
            <button type="button" class="btn-xs" @click="commitEditAnnotation">确定</button>
          </div>
          <button
            v-else
            type="button"
            class="name-chip"
            :class="['source-' + ann.source, { 'link-active': relationLinkFrom === ann.name }]"
            draggable="true"
            :title="'拖动到族谱；✎ 改姓名'"
            @dragstart="onDragStart($event, ann)"
            @click="onChipClick(ann, $event)"
          >
            <span class="name-chip-text">{{ ann.name }}</span>
            <span class="name-chip-badge">{{ ann.source === 'ai' ? 'AI' : '手' }}</span>
            <span class="name-chip-edit-btn" @click.stop="startEditAnnotation(ann)">✎</span>
            <span class="name-chip-remove" @click.stop="removeAnnotation(ann.id)">×</span>
          </button>
        </template>
      </div>
    </div>
  </div>
</template>
