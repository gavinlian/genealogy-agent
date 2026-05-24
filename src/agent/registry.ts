import type { AgentDefinition } from './types'

/** 已注册智能体；后续新增智能体在此登记，共用 AgentChatPane / Shell 布局 */
export const AGENT_REGISTRY: Record<string, AgentDefinition> = {
  genealogy: {
    id: 'genealogy',
    name: '家族智能体',
    shortName: '家族',
    icon: '见',
    tagline: '身具智能 · 见家族，见自己 · ReSee',
    placeholderHome: '用对话建谱、打开族谱、扫描录入…',
    placeholderWorkspace: '对话操作族谱：查人、填资料、切页面、整理…',
    welcomeHome:
      '你好，我是族见家族智能体 —— 身具智能，用对话即可操作族谱与家族相关功能。\n'
      + '见家族，见自己（ReSee）。\n'
      + '· 说族谱名称 → 打开或自动创建\n'
      + '· 说「扫描建谱」→ 拍照/OCR 录入\n'
      + '· 不必先点按钮，直接跟我说',
    welcomeWorkspace: ({ familyName }) =>
      `已打开「${familyName || '族谱'}」。我是身具智能的家族智能体，用对话操作本谱及后续家族能力：\n`
      + '· 描述成员资料 → 自动填入（如「张三字子明第三世」）\n'
      + '· 查关系、搜人、看原文、整理方案\n'
      + '· 说「打开树图/成员/文字版」即可切页',
  },
}

export const DEFAULT_AGENT_ID = 'genealogy'

export function getAgent(id: string = DEFAULT_AGENT_ID): AgentDefinition {
  return AGENT_REGISTRY[id] ?? AGENT_REGISTRY[DEFAULT_AGENT_ID]
}
