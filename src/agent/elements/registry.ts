/** 对话内 Generative UI 组件注册表（Phase 1） */
import type { Component } from 'vue'
import CreateFamilyPreview from '../components/agent/elements/CreateFamilyPreview.vue'
import PersonCard from '../components/agent/elements/PersonCard.vue'
import FieldDiff from '../components/agent/elements/FieldDiff.vue'

export type AgentElementDefinition = {
  type: string
  label: string
  description: string
  component?: Component
}

export const AGENT_ELEMENT_REGISTRY: AgentElementDefinition[] = [
  {
    type: 'create_family_preview',
    label: '建谱预览',
    description: '展示从对话提取的族谱名称、姓氏、简介',
    component: CreateFamilyPreview,
  },
  {
    type: 'person_card',
    label: '成员卡片',
    description: '展示成员姓名、字号、世代、生卒、原文节选',
    component: PersonCard,
  },
  {
    type: 'field_diff',
    label: '字段变更',
    description: '展示从对话提取或待确认的字段 diff',
    component: FieldDiff,
  },
  {
    type: 'search_results',
    label: '搜索结果',
    description: '多人匹配时的成员列表',
  },
  {
    type: 'text',
    label: '文本',
    description: '普通回复文字',
  },
]

export function getElementDefinition(type: string) {
  return AGENT_ELEMENT_REGISTRY.find((e) => e.type === type)
}
