export type OrganizePlan = {
  explanation?: string
  clean_slate?: boolean
  relations_add?: Array<{ from: string; to: string; type?: string }>
  relations_remove?: Array<{ from: string; to: string; type?: string }>
  new_persons?: Array<{ name: string }>
  person_updates?: Array<{ name: string; fields?: string[] }>
}

export type OrganizeDiff = {
  before?: { person_count?: number; relation_count?: number }
  after?: { person_count?: number; relation_count?: number }
  persons_to_add?: string[]
  persons_to_update?: Array<{ name: string; fields?: string[] }>
  relations_to_add?: Array<{ from: string; to: string; type?: string }>
  relations_to_remove?: Array<{ from: string; to: string; type?: string }>
  extra_persons?: string[]
  extra_relations?: Array<{ from: string; to: string; type?: string }>
  merge_change_count?: number
  replace_extra_count?: number
  has_replace_impact?: boolean
  clean_slate?: boolean
  hints?: string[]
}

export function planSummary(plan: OrganizePlan | null) {
  if (!plan) return null
  return {
    addRel: plan.relations_add?.length || 0,
    removeRel: plan.relations_remove?.length || 0,
    newPerson: plan.new_persons?.length || 0,
    updatePerson: plan.person_updates?.length || 0,
  }
}

export function planHasChanges(plan: OrganizePlan | null) {
  const s = planSummary(plan)
  if (!s) return false
  return s.addRel + s.removeRel + s.newPerson + s.updatePerson > 0
}

export function pickDefaultApplyMode(
  res: { plan?: OrganizePlan | null; diff?: OrganizeDiff | null },
  options?: { memberCount?: number },
) {
  if ((options?.memberCount ?? 0) > 0) {
    return 'merge' as const
  }
  if (res.plan?.clean_slate || res.diff?.clean_slate || res.diff?.has_replace_impact) {
    return 'replace' as const
  }
  return 'merge' as const
}

export function relLabel(r: { from: string; to: string; type?: string }) {
  const t = r.type === 'spouse' ? '配偶' : '父子'
  return `${r.from} → ${r.to}（${t}）`
}
