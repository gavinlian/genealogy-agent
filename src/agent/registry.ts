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
    placeholderWorkspace: '说「整理族谱」「搜索张三」「补全关系」…',
    welcomeHome:
      '你好，我是族见家族智能体 —— 身具智能，用对话即可操作族谱与家族相关功能。\n'
      + '见家族，见自己（ReSee）。\n'
      + '· 说族谱名称 → 打开或自动创建\n'
      + '· 说「扫描建谱」→ 拍照/OCR 录入\n'
      + '· 不必先点按钮，直接跟我说',
    welcomeWorkspace: ({ familyName }) =>
      `已打开「${familyName || '族谱'}」。推荐：\n`
      + '1. 点底部「整理」→ 图↔字 → 关系文字 → 实时预览 → 写入主谱\n'
      + '2. 直接说「整理族谱」「重新识别扫描图」「重新生成关系描述」\n'
      + '3. OCR/关系文字不对时不必手打，对话即可 AI 重生并自动写入版本\n'
      + '4. 查人、改资料、切页，继续对话即可',
  },
}

export const DEFAULT_AGENT_ID = 'genealogy'

export function getAgent(id: string = DEFAULT_AGENT_ID): AgentDefinition {
  return AGENT_REGISTRY[id] ?? AGENT_REGISTRY[DEFAULT_AGENT_ID]
}
