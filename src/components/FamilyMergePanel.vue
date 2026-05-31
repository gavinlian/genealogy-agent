<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { api } from '../utils/api'
import SourceFusionPanel from './SourceFusionPanel.vue'

type FamilyOption = { id: string; name: string; person_count?: number }

type MergePreview = {
  summary?: string
  stats?: {
    persons_to_add?: number
    persons_to_update?: number
    relations_to_add?: number
    source_ocr_chars?: number
  }
  preview?: {
    new_persons?: string[]
    updated_persons?: string[]
    new_relations?: Array<{ from: string; to: string; type?: string }>
  }
  source_family_name?: string
  target_family_name?: string
}

const props = defineProps<{
  familyId: string
  familyName?: string
  initialFusionText?: string
}>()

const emit = defineEmits<{
  toast: [message: string, type?: 'success' | 'error' | 'info']
  saved: []
  openOrganize: []
}>()

const importLoading = ref(false)
const importInput = ref<HTMLInputElement | null>(null)

const familyOptions = ref<FamilyOption[]>([])
const familiesLoading = ref(false)
const sourceFamilyId = ref('')
const mergePreview = ref<MergePreview | null>(null)
const previewLoading = ref(false)
const mergeLoading = ref(false)

const selectedSourceName = computed(() =>
  familyOptions.value.find((f) => f.id === sourceFamilyId.value)?.name || '',
)

function notify(message: string, type: 'success' | 'error' | 'info' = 'info') {
  emit('toast', message, type)
}

async function loadFamilyOptions() {
  if (!props.familyId) return
  familiesLoading.value = true
  try {
    const res = await api('GET', '/families/dashboard')
    const owned: FamilyOption[] = res.owned || []
    const followed: FamilyOption[] = res.followed || []
    const seen = new Set<string>()
    familyOptions.value = [...owned, ...followed].filter((f) => {
      if (!f.id || f.id === props.familyId || seen.has(f.id)) return false
      seen.add(f.id)
      return true
    })
  } catch {
    familyOptions.value = []
  } finally {
    familiesLoading.value = false
  }
}

async function loadMergePreview() {
  if (!props.familyId || !sourceFamilyId.value) {
    mergePreview.value = null
    return
  }
  previewLoading.value = true
  try {
    const res = await api(
      'GET',
      `/families/${props.familyId}/merge-preview?source_id=${encodeURIComponent(sourceFamilyId.value)}`,
    )
    if (!res.success && res.detail) {
      notify(res.detail, 'error')
      mergePreview.value = null
      return
    }
    mergePreview.value = res as MergePreview
  } catch {
    notify('合并预览失败', 'error')
    mergePreview.value = null
  } finally {
    previewLoading.value = false
  }
}

async function applyFamilyMerge() {
  if (!props.familyId || !sourceFamilyId.value) return
  mergeLoading.value = true
  try {
    const res = await api('POST', `/families/${props.familyId}/merge-from`, {
      source_family_id: sourceFamilyId.value,
    })
    if (!res.success) {
      notify(res.message || res.detail || '合并失败', 'error')
      return
    }
    notify(res.message || '族谱合并完成', 'success')
    mergePreview.value = null
    sourceFamilyId.value = ''
    emit('saved')
  } catch {
    notify('合并失败', 'error')
  } finally {
    mergeLoading.value = false
  }
}

function buildRelationsFromExport(
  persons: Array<{ id?: string; name?: string }>,
  relations: Array<{ from_person_id?: string; to_person_id?: string; relation_type?: string; type?: string }>,
) {
  const idToName = new Map<string, string>()
  for (const p of persons) {
    if (p.id && p.name) idToName.set(p.id, p.name)
  }
  return relations
    .map((r) => {
      const from = idToName.get(r.from_person_id || '') || r.from_person_id
      const to = idToName.get(r.to_person_id || '') || r.to_person_id
      if (!from || !to) return null
      return {
        from,
        to,
        type: r.relation_type || r.type || 'parent_child',
      }
    })
    .filter(Boolean) as Array<{ from: string; to: string; type: string }>
}

async function mergeImportJson(file: File) {
  if (!props.familyId) return
  importLoading.value = true
  try {
    const text = await file.text()
    const data = JSON.parse(text)
    const archive = data.archive || data
    const persons =
      (archive.persons || data.persons || []).map((p: { native?: Record<string, unknown> } & Record<string, unknown>) =>
        p.native || p,
      )
    const rawRelations = archive.relations || data.relations || []
    const relations = rawRelations.map((r: { native?: Record<string, unknown> } & Record<string, unknown>) => {
      const row = r.native || r
      return {
        from_person_id: row.from_person_id,
        to_person_id: row.to_person_id,
        relation_type: row.relation_type || row.type,
      }
    })

    if (!persons.length) {
      notify('文件中没有可合并的成员数据', 'error')
      return
    }

    const res = await api('POST', '/persons/batch', {
      family_id: props.familyId,
      merge: true,
      persons,
      relations: buildRelationsFromExport(persons, relations),
    })

    if (!res.success) {
      notify(res.message || res.detail || '合并导入失败', 'error')
      return
    }

    notify(
      `已合并导入：${res.count || persons.length} 人 · 新增/补全 ${res.relation_count || 0} 条关系`,
      'success',
    )
    emit('saved')
  } catch {
    notify('JSON 解析或合并失败，请确认文件格式', 'error')
  } finally {
    importLoading.value = false
    if (importInput.value) importInput.value.value = ''
  }
}

function onImportPick(e: Event) {
  const file = (e.target as HTMLInputElement).files?.[0]
  if (file) void mergeImportJson(file)
}

watch(sourceFamilyId, () => {
  void loadMergePreview()
})

watch(
  () => props.familyId,
  () => {
    sourceFamilyId.value = ''
    mergePreview.value = null
    void loadFamilyOptions()
  },
)

onMounted(() => {
  void loadFamilyOptions()
})
</script>

<template>
  <div class="family-merge-panel">
    <header class="family-merge-head">
      <h3>合并整理</h3>
      <p class="hint">
        把 OCR、关系描述、修正稿与族谱关系合并成统一文字；或把另一份族谱 / JSON 增量合并进「{{ familyName || '当前族谱' }}」。
      </p>
    </header>

    <div class="family-merge-cards">
      <section class="family-merge-card">
        <h4>① 多版原文合并</h4>
        <p class="hint">合并版本一 OCR、版本二关系描述、版本三修正稿与族谱关系，生成逐步融合稿。</p>
        <SourceFusionPanel
          :family-id="familyId"
          :initial-text="initialFusionText"
          @toast="(msg, kind) => notify(msg, kind || 'info')"
          @saved="emit('saved')"
        />
      </section>

      <section class="family-merge-card">
        <h4>② 合并另一份族谱</h4>
        <p class="hint">
          把账号里另一份族谱合并进来：同名成员更新字段，新成员与关系追加，OCR 原文按页拼接（不删现有数据）。
        </p>
        <div class="family-merge-actions family-merge-actions--stack">
          <label class="family-merge-select-label">
            源族谱
            <select
              v-model="sourceFamilyId"
              class="family-merge-select"
              :disabled="familiesLoading || mergeLoading"
            >
              <option value="">— 选择要合并的族谱 —</option>
              <option v-for="f in familyOptions" :key="f.id" :value="f.id">
                {{ f.name }}（{{ f.person_count ?? 0 }} 人）
              </option>
            </select>
          </label>
          <p v-if="familiesLoading" class="hint">加载族谱列表…</p>
          <p v-else-if="!familyOptions.length" class="hint">暂无其他可合并的族谱（需先创建或关注另一份族谱）。</p>

          <div v-if="previewLoading" class="hint">生成合并预览…</div>
          <div v-else-if="mergePreview" class="family-merge-preview">
            <p class="family-merge-preview-summary">{{ mergePreview.summary }}</p>
            <ul v-if="mergePreview.stats" class="family-merge-preview-stats">
              <li>新增成员 {{ mergePreview.stats.persons_to_add ?? 0 }} 人</li>
              <li>更新成员 {{ mergePreview.stats.persons_to_update ?? 0 }} 人</li>
              <li>追加关系 {{ mergePreview.stats.relations_to_add ?? 0 }} 条</li>
              <li v-if="mergePreview.stats.source_ocr_chars">
                合并 OCR 约 {{ mergePreview.stats.source_ocr_chars }} 字
              </li>
            </ul>
            <details v-if="mergePreview.preview?.new_persons?.length" class="family-merge-preview-details">
              <summary>新增成员预览</summary>
              <p>{{ mergePreview.preview.new_persons.join('、') }}</p>
            </details>
          </div>

          <button
            type="button"
            class="btn-primary btn-sm"
            :disabled="!sourceFamilyId || previewLoading || mergeLoading || !mergePreview"
            @click="applyFamilyMerge"
          >
            {{ mergeLoading ? '合并中…' : `合并「${selectedSourceName || '源族谱'}」进当前族谱` }}
          </button>
        </div>
      </section>

      <section class="family-merge-card">
        <h4>③ 导入 JSON 合并进族谱</h4>
        <p class="hint">同名成员会更新字段，新成员与关系会追加（不会删除现有数据）。</p>
        <div class="family-merge-actions">
          <button
            type="button"
            class="btn-secondary btn-sm"
            :disabled="importLoading"
            @click="importInput?.click()"
          >
            {{ importLoading ? '合并中…' : '选择 JSON 归档合并' }}
          </button>
          <input
            ref="importInput"
            type="file"
            accept=".json,application/json"
            class="ocr-image-file-input"
            @change="onImportPick"
          />
        </div>
      </section>

      <section class="family-merge-card family-merge-card--compact">
        <h4>④ 合并后整理写入</h4>
        <p class="hint">融合稿保存后，在「整理组谱」预览差异，再一键写入族谱结构。</p>
        <button type="button" class="btn-primary btn-sm" @click="emit('openOrganize')">
          打开整理组谱 · 预览写入
        </button>
      </section>
    </div>
  </div>
</template>
