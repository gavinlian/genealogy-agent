<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import SourceImageZoom from './SourceImageZoom.vue'
import {
  buildPageList,
  getPageText,
  setPageText,
  splitPagedText,
} from '../utils/sourcePages'
import { uploadImageUrl } from '../utils/uploadImageUrl'

export type PageWorkbenchMode = 'v1' | 'v2'

const props = withDefaults(
  defineProps<{
    mode?: PageWorkbenchMode
    ocrText: string
    relationText?: string
    imagePaths?: string[]
    imagePreviews?: string[]
    imagePath?: string
    imagePreview?: string
    readonly?: boolean
    /** 整理组谱：原图占主屏，文字区收在下方 */
    imagePrimary?: boolean
  }>(),
  {
    mode: 'v1',
    relationText: '',
    imagePaths: () => [],
    imagePreviews: () => [],
    imagePath: '',
    imagePreview: '',
    readonly: false,
    imagePrimary: false,
  },
)

const emit = defineEmits<{
  'update:ocrText': [value: string]
  'update:relationText': [value: string]
  'regenerate-page': [page: number]
}>()

const pageIndex = ref(0)

const paths = computed(() =>
  props.imagePaths?.length
    ? props.imagePaths
    : props.imagePath
      ? [props.imagePath]
      : [],
)

const previews = computed(() =>
  props.imagePreviews?.length
    ? props.imagePreviews
    : props.imagePreview
      ? [props.imagePreview]
      : [],
)

const pages = computed(() =>
  buildPageList(props.ocrText, props.relationText || '', paths.value, previews.value),
)

const currentPage = computed(() => pages.value[pageIndex.value] || pages.value[0] || null)

const currentImageSrc = computed(() => {
  const p = currentPage.value
  if (!p) return ''
  return uploadImageUrl(p.imagePath, p.imagePreview)
})

const modeLabel = computed(() => (props.mode === 'v1' ? '版本一 · OCR 原文' : '版本二 · 关系描述'))

const currentEditorText = computed({
  get: () => {
    const p = currentPage.value
    if (!p) return ''
    return props.mode === 'v1' ? p.ocrText : p.relationText
  },
  set: (v: string) => {
    const p = currentPage.value
    if (!p) return
    if (props.mode === 'v1') {
      emit('update:ocrText', setPageText(props.ocrText, p.page, v))
    } else {
      emit('update:relationText', setPageText(props.relationText || '', p.page, v))
    }
  },
})

const currentOcrBaseline = computed(() => currentPage.value?.ocrText || '')

watch(
  () => pages.value.length,
  (len) => {
    if (pageIndex.value >= len) pageIndex.value = Math.max(0, len - 1)
  },
)

watch(
  () => [props.ocrText, props.relationText] as const,
  () => {
    if (!pages.value.length) pageIndex.value = 0
  },
)

function selectPage(index: number) {
  pageIndex.value = index
}

function emitRegeneratePage() {
  const p = currentPage.value
  if (p) emit('regenerate-page', p.page)
}
</script>

<template>
  <div
    class="genealogy-page-workbench"
    :class="{ 'genealogy-page-workbench--image-primary': imagePrimary }"
  >
    <div v-if="pages.length > 1" class="genealogy-page-workbench-tabs" role="tablist" aria-label="谱页">
      <button
        v-for="(pg, index) in pages"
        :key="pg.page"
        type="button"
        role="tab"
        class="genealogy-page-workbench-tab"
        :class="{ active: index === pageIndex }"
        :aria-selected="index === pageIndex"
        @click="selectPage(index)"
      >
        第 {{ pg.page }} 页
        <span v-if="mode === 'v1' && pg.ocrText.trim()" class="genealogy-page-workbench-tab-dot" title="已有 OCR" />
        <span v-else-if="mode === 'v2' && pg.relationText.trim()" class="genealogy-page-workbench-tab-dot genealogy-page-workbench-tab-dot--rel" title="已有关系描述" />
      </button>
    </div>

    <!-- 大图主屏：上图 · 下字（整理组谱） -->
    <div
      v-if="imagePrimary"
      class="genealogy-page-workbench-stack"
    >
      <div
        v-if="mode === 'v1' || currentImageSrc"
        class="genealogy-page-workbench-image genealogy-page-workbench-image--hero"
      >
        <div class="genealogy-page-workbench-image-head">
          <strong>扫描原图</strong>
          <span v-if="pages.length > 1" class="hint">第 {{ currentPage?.page || 1 }} / {{ pages.length }} 页</span>
          <span v-else-if="mode === 'v2'" class="hint">对照原图编写关系描述</span>
        </div>
        <SourceImageZoom
          v-if="currentImageSrc"
          :src="currentImageSrc"
          :alt="`族谱第 ${currentPage?.page || 1} 页`"
        />
        <div v-else class="genealogy-page-workbench-image-empty">
          本页暂无原图。上传或扫描后，AI 将对照大图识别 OCR 并生成关系描述。
        </div>
      </div>

      <div
        v-if="mode === 'v1'"
        class="genealogy-page-workbench-text genealogy-page-workbench-text--dock"
      >
        <div class="genealogy-page-workbench-text-head">
          <strong>{{ modeLabel }}</strong>
          <span class="hint">{{ currentEditorText.trim().length }} 字</span>
        </div>
        <textarea
          v-model="currentEditorText"
          class="genealogy-page-workbench-editor"
          :readonly="readonly"
          placeholder="本页 OCR 原文，对照上方原图逐行修改…"
          spellcheck="false"
        />
      </div>

      <div
        v-else
        class="genealogy-page-workbench-split genealogy-page-workbench-split--text genealogy-page-workbench-split--under-image"
      >
        <div class="genealogy-page-workbench-left-ocr">
          <div class="genealogy-page-workbench-image-head">
            <strong>版本一 · OCR 原文</strong>
            <span class="hint">{{ currentOcrBaseline.trim().length }} 字</span>
          </div>
          <pre class="genealogy-page-workbench-baseline-body genealogy-page-workbench-baseline-body--pane">{{ currentOcrBaseline.trim() || '（本页暂无 OCR，请先在版本一识别或粘贴）' }}</pre>
        </div>
        <div class="genealogy-page-workbench-text">
          <div class="genealogy-page-workbench-text-head">
            <strong>{{ modeLabel }}</strong>
            <span class="hint">{{ currentEditorText.trim().length }} 字</span>
          </div>
          <textarea
            v-model="currentEditorText"
            class="genealogy-page-workbench-editor"
            :readonly="readonly"
            placeholder="本页关系描述（RDL 格式：一行一人，配/子/女/父/母写进行内）…"
            spellcheck="false"
          />
          <div class="genealogy-page-workbench-actions">
            <button type="button" class="btn-xs btn-secondary" @click="emitRegeneratePage">
              AI 重生本页关系描述
            </button>
            <span class="hint">对照上方原图 · 按页生成更准</span>
          </div>
        </div>
      </div>
    </div>

    <!-- 经典双栏：左图/左 OCR · 右编辑 -->
    <div
      v-else
      class="genealogy-page-workbench-split"
      :class="{ 'genealogy-page-workbench-split--text': mode === 'v2' }"
    >
      <div v-if="mode === 'v1'" class="genealogy-page-workbench-image">
        <div class="genealogy-page-workbench-image-head">
          <strong>原图</strong>
          <span v-if="pages.length > 1" class="hint">第 {{ currentPage?.page || 1 }} / {{ pages.length }} 页</span>
        </div>
        <SourceImageZoom
          v-if="currentImageSrc"
          :src="currentImageSrc"
          :alt="`族谱第 ${currentPage?.page || 1} 页`"
          compact
        />
        <div v-else class="genealogy-page-workbench-image-empty">
          本页暂无原图。多图扫描后会与页码一一对应。
        </div>
      </div>

      <div v-else class="genealogy-page-workbench-left-ocr">
        <div class="genealogy-page-workbench-image-head">
          <strong>版本一 · OCR 原文</strong>
          <span class="hint">{{ currentOcrBaseline.trim().length }} 字</span>
        </div>
        <pre class="genealogy-page-workbench-baseline-body genealogy-page-workbench-baseline-body--pane">{{ currentOcrBaseline.trim() || '（本页暂无 OCR，请先在版本一识别或粘贴）' }}</pre>
      </div>

      <div class="genealogy-page-workbench-text">
        <div class="genealogy-page-workbench-text-head">
          <strong>{{ modeLabel }}</strong>
          <span class="hint">{{ currentEditorText.trim().length }} 字</span>
        </div>

        <textarea
          v-model="currentEditorText"
          class="genealogy-page-workbench-editor"
          :readonly="readonly"
          :placeholder="mode === 'v1'
            ? '本页 OCR 原文，对照左侧原图逐行修改…'
            : '本页关系描述（RDL 格式：一行一人，配/子/女/父/母写进行内）…'"
          spellcheck="false"
        />

        <div v-if="mode === 'v2'" class="genealogy-page-workbench-actions">
          <button type="button" class="btn-xs btn-secondary" @click="emitRegeneratePage">
            AI 重生本页关系描述
          </button>
          <span class="hint">左 OCR · 右 RDL；按页生成比整本合并更准</span>
        </div>
      </div>
    </div>

    <p v-if="!imagePrimary && mode === 'v1' && pages.length <= 1 && !currentImageSrc" class="hint genealogy-page-workbench-foot">
      版本一：左图右字。上传多张图片后将出现页签，逐页对照 OCR。
    </p>
    <p v-else-if="!imagePrimary && mode === 'v2'" class="hint genealogy-page-workbench-foot">
      版本二：左版本一 OCR · 右关系描述（文字对照，不含原图；改 OCR 请切回版本一）。
    </p>
  </div>
</template>
