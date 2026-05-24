# 族见 · V1 交付清单（实现版 PRD）

> **文档版本**：v1.0 · 2026-05-24  
> **分支**：`feat/conversational-agent`  
> **与愿景文档关系**：[`PRD-对话式族谱智能体.md`](./PRD-对话式族谱智能体.md) 描述 **产品方向**；本文档描述 **第一版必须交付什么、怎么验收**。  
> **原则**：先做出可用的 V1，愿景 PRD 后续再补细节，不阻塞开发。

---

## 1. 结论：原 PRD 哪里「不够」

原 PRD **方向没问题**，问题在于三类内容混在一起，缺少 **V1 切线**：

| 问题 | 表现 | 导致 |
|------|------|------|
| 愿景 vs 交付未分层 | Phase 1 勾了 ✅，但 4.3 要求「嵌入 v1 完整组件」 | 开发不知道 V1 要不要上垂丝图 |
| UI 只有 wireframe | 4.1 有布局图，无像素级状态（未选族谱、空谱、展开对话） | 实现时各自理解 |
| 能力清单过大 | §5 列了 15+ 工具，Phase 1 只做了读谱 + UI | 看起来「全做了」实际只做了子集 |

**不需要重写愿景 PRD**。需要.authentic V1 清单 = **开发对齐用的「完成定义」**。

---

## 2. V1 产品定义（一句话）

**打开应用 = 对话式工作台**：上方是当前页面，下方是常驻对话抽屉，底部 Tab 切页；能用对话 **查谱、切页、搜人**；建谱/改谱/整理 **走经典编辑或 V1.1 接入**，不阻塞 V1 发布。

---

## 3. V1 必须交付（In Scope）

### 3.1 入口与壳（`FamilyChatShell`）

| # | 要求 | 验收 |
|---|------|------|
| E1 | 打开 Web 即进入对话壳，**无**「智能体打开」二次入口 | 首屏可见对话输入框 |
| E2 | 布局符合 PRD 4.1：**顶栏 → 页面区 → 对话抽屉 → Tab** | 手机竖屏目测与 wireframe 一致 |
| E3 | 顶栏：**族谱名 · 我在谱中 · 设置**（未选族谱时：族见 + 设置） | 顶栏无多余主按钮 |
| E4 | 未选族谱：页面区 = 族谱列表；对话可用（选谱/扫描/新建） | 不选谱也能发消息 |
| E5 | 对话抽屉：默认显示最近 2 条，可上滑展开 | 点击拖拽条可展开/收起 |
| E6 | 输入栏：**输入框 + 拍照 + 发送**（语音按钮占位 disabled） | 拍照跳转 OCR |
| E7 | 底部 Tab：🌳 📜 👤 ⚖ ✨（仅已选族谱时显示） | 点击切换页面区 |
| E8 | 大屏 ≥960px：页面左、对话右 | 浏览器拉宽可见分栏 |
| E9 | 「经典编辑」为次要入口（页面内或空态链接），非主路径 | 不挡对话主流程 |

### 3.2 Agent 后端（读谱 + UI，规则引擎即可）

| # | 要求 | 验收 |
|---|------|------|
| A1 | `POST /api/families/{id}/agent/chat` | 返回 reply + 可选 ui_actions |
| A2 | `GET/PUT /api/families/{id}/agent/state` | messages / tab / anchor / selected 持久化 |
| A3 | 上下文随请求传递：`active_tab` · `anchor_person_id` · `selected_person_id` | 切 Tab 后对话仍带上下文 |
| A4 | 读谱：搜索、亲属查询、两人关系、成员详情 | 见 §4 对话样例 |
| A5 | UI 指令：`switch_tab` · `focus_person` | 说「打开原文」自动切 Tab |
| A6 | `anchor_person_id` 顶栏可选并持久化 | 「我的堂兄弟」以锚点人为准 |
| A7 | **LLM 选工具**（复用 parse 模型配置）；失败/无 Key **回退规则** | `used_llm` 字段；设置里配 Key 后自然语言可用 |
| A8 | **写操作须确认**：`propose_person_patch` · `propose_sync_person_details` · `propose_organize_plan` | 对话内确认卡片 → `POST .../agent/confirm` |

### 3.3 各 Tab 页面区（V1 可简化，不可缺失）

| Tab | V1 最低要求 | 完整 v1 组件 |
|-----|-------------|--------------|
| 🌳 树图 | 成员列表/简化节点，可点选 | 垂丝图 Canvas（V1.1） |
| 📜 原文 | 只读展示 `source_text` | OcrTextWorkspace 可编辑（V1.1） |
| 👤 成员 | 选中成员卡片（姓名/字/号/传） | PersonDetail 表单（V1.1） |
| ⚖ 对比 | 空态 +「经典编辑」入口 | SourceCompareDialog（V2） |
| ✨ 整理 | 空态 +「经典编辑」入口 | GenealogyOrganizePanel（V2） |

> **明确**：V1 页面区是 **占位 + 只读预览**，不是删掉能力；完整编辑在「经典编辑」或后续版本嵌入。

### 3.4 经典编辑（保留）

| # | 要求 | 验收 |
|---|------|------|
| C1 | 从对话壳可进入 v1 完整工作区 | 「经典编辑」按钮可用 |
| C2 | OCR / 解析对比 / 整理 / 成员 CRUD 在经典模式可用 | 与 main 分支能力不退化 |
| C3 | 从经典可回到对话模式 | 「对话模式」按钮可用 |

---

## 4. V1 对话验收样例

在**已选族谱、已设 anchor、已选成员**前提下：

| 用户输入 | 期望 |
|----------|------|
| 搜索张三 | 返回匹配列表；唯一命中时 focus 到成员页 |
| 打开文字版 / 去看原文 | 切到 📜 Tab |
| 我的堂兄弟有谁 | 以 anchor 为基准列堂表亲 |
| 他和李四什么关系 | 以 selected 为「他」，查与李四路径 |
| 扫描建谱（未选谱） | 跳转 OCR 流程 |

---

## 5. V1 明确不做（Out of Scope）

以下写在愿景 PRD 里，**不属于 V1 完成标准**：

- LLM function calling 全自动选工具
- 对话内 diff / organize 确认卡片
- 语音输入（按钮占位即可）
- UniApp / 微信小程序
- GEDCOM 导入导出
- 各 Tab 嵌入完整 v1 组件（垂丝图、原文编辑器等）
- 云部署、用户登录、多族谱权限
- `agent_tool_log` 审计表（可选，不挡 V1）

---

## 6. 当前实现状态（2026-05-24）

| 模块 | 状态 | 备注 |
|------|------|------|
| GraphStore + 读谱工具 | ✅ | |
| agent/state + agent/chat API | ✅ | 规则引擎 |
| FamilyChatShell 布局 | 🟡 | 已按 4.1 重构，待真机验收 |
| 默认入口（无二次打开） | ✅ | App.vue 默认 chat |
| Tab 简化页面 | 🟡 | 树图为节点网格，非垂丝图 |
| 经典编辑回退 | ✅ | |
| OCR 经拍照按钮 | ✅ | emit scan |
| Agent 后端 LLM + 确认 | ✅ | JSON 选工具；写操作 token 确认 |
| 对话确认卡片 UI | ✅ | FamilyChatShell |
| OCR/对比入库走 Agent | ❌ | 仍走经典/OCR 流程 |
| 语音输入 | ❌ | Phase 3 |

---

## 7. V1 剩余工作（按优先级）

### P0 — 挡发布

1. **真机/浏览器走一遍 §3.1 验收表**（E1–E9）
2. **§4 对话样例全部跑通**（含 anchor / selected 边界：未设 anchor 时给提示）
3. **经典 ↔ 对话切换**不丢当前族谱、不白屏

### P1 — V1 体验补齐（可跟 P0 同批）

4. 树图 Tab：至少展示世代/姓名，选中态与 `selected_person_id` 同步
5. 原文 Tab：拉取当前确认版（有 source_versions 时）
6. 未选谱首页：对话「打开 XX 族谱」匹配族谱名

### P2 — V1.1（V1 发布后）

7. 各 Tab 逐步嵌入 v1 组件（先树图，再原文只读→可编）
8. Agent 接 LLM + function calling
9. 写工具 + 确认卡片（OCR diff、整理 apply）

### P3 — 小程序（并行准备）

10. Agent API 契约文档化（OpenAPI 或 markdown）
11. UniApp 空壳 + 同一套 chat/state API

---

## 8. 文件与职责（V1）

| 路径 | 职责 |
|------|------|
| `src/components/FamilyChatShell.vue` | V1 主 UI 壳 |
| `src/App.vue` | 默认 chat；classic 为副模式 |
| `backend/agent/graph_store.py` | 图查询 |
| `backend/agent/agent_runtime.py` | 规则 Agent |
| `backend/agent/agent_tools.py` | 工具执行 |
| `backend/agent_store.py` | 会话状态 |
| `backend/main.py` | agent API 路由 |

---

## 9. 发布检查

```text
[ ] npm run build 通过
[ ] pytest tests/test_graph_store.py tests/test_agent_chat.py 通过
[ ] 本地 backend :8080 + frontend :3000 联调
[ ] §3.1 E1–E9 人工勾选
[ ] §4 对话样例 5 条通过
[ ] 经典编辑 OCR/整理/成员保存  smoke test
```

---

## 10. 修订记录

| 日期 | 说明 |
|------|------|
| 2026-05-24 | v1.0：从愿景 PRD 拆出 V1 切线与验收标准 |
