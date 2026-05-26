# PRD · 原文查看模式（参考族谱 App）

> 设计参考：`docs/reference/zupu-mobile/` 内两张截图（cn.zupu.familytree）

## 1. 目标

**编辑**与**查看**分离：用户录入/校对仍用文本框；**查看**按参考 App 还原两种族谱阅读体验，面向手机竖屏。

| 模式 | 参考图 | 适用场景 |
|------|--------|----------|
| **卡片世代** | `screenshot_20260525_083822_*.jpg` | 已解析人物关系，按「代」浏览，头像卡片 + 连线 |
| **谱页世系** | `screenshot_20260525_084155_*.jpg` | 对照旧谱阅读，宣纸框 + 右侧世系 + 竖排名 + 分叉线 |

底层数据不变：UTF-8 原文 + 人物/关系 JSON。查看模式只读，不写库。

## 2. 信息架构

```
OcrTextWorkspace
├── 工具栏：[卡片] [谱页] | [编辑]
├── 查看区（只读）
│   ├── GenealogyCardTreeView   ← 参考图 1
│   └── SourceSilkwormPageView  ← 参考图 2
└── 编辑区（现有 textarea + 标注）
```

数据优先级：

1. `previewPersons` + `previewRelations`（解析/主谱）
2. 否则从 `structuredText`（版本二关系描述）规则解析
3. 否则从 `modelValue`（版本一 OCR）解析

## 3. 参考图 1 · 卡片世代

### 视觉规范

- 背景：浅米色纹理（`#f5efe0` + noise）
- 左侧固定栏宽 **52px**，竖排「第 N 代」
- 人物卡片 **72×108px**：白底、细金边、剪影头像（男蓝/女橙）、**竖排姓名**
- 夫妻：两卡并排，中间横线
- 父子：上一代单元底部中心 → 竖线 → 下一代横枝 → 各子女

### 布局

- 按 `generation` 分行，`y` 递增
- 行内按配偶合并为 `unit`，再横向排列
- SVG 层画 `spouse` / `parent-child` 连线（白色/浅棕，参考 App）

## 4. 参考图 2 · 谱页世系

### 视觉规范

- 外框：双线金边 + 宣纸渐变
- 顶栏：谱名 / 人数（简化，无搜索）
- 右侧 **世系** 栏：黑底白字竖排「N 世」徽章
- 主区：竖排姓名（`writing-mode: vertical-rl`），**右主左支**（主线靠右，兄弟向左叉开）
- 节点：小圆点 + 黑色连线
- 底栏（可选）：页码占位 `1/1`（后续多页扩展）

### 布局

- 由 `parent_child` 建树，根取最小世代无父者
- Reingold 简化：子树宽度累加，兄弟从左到右（展示时 `row-reverse` 使主线在右）
- 世代 `y` 固定步长 **96px**，节点宽 **32px**

## 5. 组件清单

| 文件 | 职责 |
|------|------|
| `utils/genealogyViewData.ts` | 类型、文本→人物、API 映射 |
| `utils/cardTreeLayout.ts` | 卡片坐标 + 连线 |
| `utils/silkwormPageLayout.ts` | 谱页坐标 + 连线 |
| `components/view/GenealogyCardTreeView.vue` | 参考图 1 渲染 |
| `components/view/SourceSilkwormPageView.vue` | 参考图 2 渲染 |

## 6. 迭代计划

- **V1（本次）**：双查看模式 + 编辑切换；基于解析结果或关系描述稿
- **V2**：扫描图持久化，谱页模式左半对照原图
- **V3**：多页 `source_page[]`、翻页箭头
- **V4**：图↔字区域高亮

## 7. 验收

- [ ] 手机宽度下可横向滑动卡片行、纵向滚动世代
- [ ] 谱页竖排 + 右侧世系栏与参考图结构一致
- [ ] 有解析人物时连线正确；仅 OCR 文本时仍能按「N 世」分行展示
- [ ] 点「编辑」回到原文 textarea，标注功能不受影响
