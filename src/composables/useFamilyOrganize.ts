import { ref, watch, type Ref } from 'vue'
import { api } from '../utils/api'
import {
  type OrganizePlan,
  type OrganizeDiff,
  planHasChanges,
  pickDefaultApplyMode,
} from '../types/organize'

type NotifyFn = (message: string, type?: 'success' | 'error' | 'info') => void

export function useFamilyOrganize(
  familyId: Ref<string | null | undefined>,
  memberCount: Ref<number>,
  options?: { onNotify?: NotifyFn },
) {
  const plan = ref<OrganizePlan | null>(null)
  const diff = ref<OrganizeDiff | null>(null)
  const applyMode = ref<'merge' | 'replace'>('merge')
  const cleanSlate = ref(false)
  let planEditTimer: ReturnType<typeof setTimeout> | null = null

  function notify(message: string, type: 'success' | 'error' | 'info' = 'info') {
    options?.onNotify?.(message, type)
  }

  async function loadState(id?: string) {
    const fid = id || familyId.value
    if (!fid) {
      plan.value = null
      diff.value = null
      return
    }
    try {
      const res = await api('GET', `/families/${fid}/ai-organize/state`)
      if (!res.success) return
      plan.value = res.pending_plan || null
      diff.value = res.pending_diff ?? null
      applyMode.value = res.apply_mode === 'replace' ? 'replace' : 'merge'
      cleanSlate.value = Boolean(res.clean_slate)
    } catch {
      /* ignore */
    }
  }

  async function saveState() {
    if (!familyId.value) return
    try {
      await api('PUT', `/families/${familyId.value}/ai-organize/state`, {
        pending_plan: plan.value,
        pending_diff: diff.value,
        apply_mode: applyMode.value,
        clean_slate: cleanSlate.value,
      })
    } catch {
      /* ignore */
    }
  }

  async function refreshDiff() {
    if (!familyId.value || !plan.value) return
    try {
      const res = await api('POST', `/families/${familyId.value}/ai-organize/refresh-diff`, {
        plan: plan.value,
        clean_slate: cleanSlate.value,
      })
      if (res.success) {
        plan.value = res.plan || plan.value
        diff.value = res.diff || null
        if (memberCount.value <= 0) {
          applyMode.value = 'replace'
        } else if (applyMode.value !== 'merge') {
          applyMode.value = pickDefaultApplyMode(
            { plan: plan.value, diff: diff.value },
            { memberCount: memberCount.value },
          )
        }
        await saveState()
      }
    } catch {
      /* ignore */
    }
  }

  function onPlanPatch(next: OrganizePlan) {
    plan.value = next
  }

  function onPlanEdited() {
    if (planEditTimer) clearTimeout(planEditTimer)
    planEditTimer = setTimeout(() => {
      void refreshDiff()
    }, 450)
  }

  function onLoadPlan(payload: { plan: OrganizePlan | null; diff: OrganizeDiff | null }) {
    plan.value = payload.plan
    diff.value = payload.diff
    if (payload.plan && planHasChanges(payload.plan)) {
      applyMode.value = pickDefaultApplyMode(payload, { memberCount: memberCount.value })
      notify('整理方案已就绪，请核对关系卡片', 'success')
    }
    void saveState()
  }

  async function dismissPlan() {
    plan.value = null
    diff.value = null
    await saveState()
  }

  async function onApplied(stats?: Record<string, number>) {
    plan.value = null
    diff.value = null
    applyMode.value = 'merge'
    await saveState()
    const added = stats?.persons_added ?? 0
    const rels = stats?.relations_added ?? 0
    const diag = stats?.diagnostics as {
      unmatched_names?: string[]
      skipped_relation_count?: number
    } | undefined
    let msg = added || rels
      ? `主谱已更新（+${added} 人，+${rels} 关系）`
      : '主谱已更新'
    if (diag?.unmatched_names?.length) {
      msg += `；未匹配姓名：${diag.unmatched_names.slice(0, 5).join('、')}`
    } else if (diag?.skipped_relation_count) {
      msg += `；${diag.skipped_relation_count} 条关系未写入`
    }
    notify(msg, 'success')
  }

  async function onCleared() {
    cleanSlate.value = true
    applyMode.value = 'replace'
    if (plan.value && planHasChanges(plan.value)) {
      await refreshDiff()
      notify('主谱已清空，可点「替换写入主谱」直接写入方案', 'success')
    } else {
      notify('主谱已清空，可从原文或 AI 方案重建', 'success')
    }
  }

  const hasPendingPlan = () => Boolean(plan.value && planHasChanges(plan.value))

  watch(familyId, (id) => {
    void loadState(id || undefined)
  })

  watch([applyMode, cleanSlate], () => {
    void saveState()
  })

  return {
    plan,
    diff,
    applyMode,
    cleanSlate,
    loadState,
    saveState,
    refreshDiff,
    onPlanPatch,
    onPlanEdited,
    onLoadPlan,
    dismissPlan,
    onApplied,
    onCleared,
    hasPendingPlan,
    planHasChanges,
  }
}
