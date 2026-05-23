# 族见 - 族谱智能体 PRD（本地版 · 功能梳理）

> 见家族，见自己。  
> **本文档范围**：功能、数据、API、智能体能力（**不含 UI 交互细则**，UI 见 [`PRD-UI-交互.md`](./PRD-UI-交互.md)）。  
> **设计构想来源**：`docs/PRD/族谱智能体优化建议与设计构想.html`（下称「设计构想」）

**产品名**：族见（Genealogy Agent）  
**技术栈**：Vue3 + FastAPI + SQLite，AI 可插拔（默认 MiniMax M2.7）  
**部署**：本地优先（单机 / 局域网），与设计构想中的「私有化部署」路径对齐

---

## 1. 一句话定位

**族谱智能体 = OCR/多模态录入 + AI 解析与自动建谱 + 关系校验 + 族谱树/关系网 + 搜索 + 导出**

从「工具辅助」演进到「智能协同」：以**结构化族谱数据**为中枢，逐步叠加**主动校验、优化建议、多模态输入**（设计构想 §一）。

---

## 2. 本地 vs 设计构想：架构取舍

| 维度 | 设计构想（HTML） | 本地版决策 |
|------|------------------|------------|
| 数据库 | MongoDB → Neo4j 知识图谱 | **SQLite** 为主；关系用 `relations` + 推理引擎，**不**首期迁 Neo4j |
| 前端 | uni-app 多端 | **Vue3 单页 Web**（`src/App.vue`） |
| 账号/同步 | 微信登录、Unicloud | **单用户本地**，无账号体系 |
| 可视化 | SVG/D3、力导向、虚拟滚动 | 当前为**布局元数据 + 简易 SVG**；功能目标见 §6 |
| AI | Qwen3-VL、ReAct、RAG | **可插拔 Provider**；先强化 OCR/解析/校验，多模态按 Provider 能力渐进 |
| 语音/AR/TTS/区块链 | 生态拓展期 | **v3+ 可选**，本地版先做 Web 语音输入与口述文本入库（§8 阶段 C 子集） |

---

## 3. 当前已实现功能（代码库实况 · 2026-05）

> 以下以仓库代码为准，纠正旧版 PRD 中「未实现」的过时描述。

### 3.1 页面与能力对照

| 能力域 | 功能点 | 状态 | 实现位置（参考） |
|--------|--------|------|------------------|
| 族谱管理 | 列表 / 新建 / 编辑 / 删除 | ✅ | `main.py` families API；`App.vue` |
| 扫描建谱 | 上传图 → OCR → 解析 → 自动建谱 → 校验 | ✅ | `pipeline.py` → `genealogy_builder.py` |
| 人名质量 | 专名提取、黑名单、AI 结果后处理 | ✅ | `name_extractor.py` |
| 自动建谱 | 世代/子/女/配推理、rebuild、generate | ✅ | `genealogy_builder.py`；`/api/agent/generate` |
| 成员 CRUD | 单条 / 批量、父母配偶同步 | ✅ | `person_editor.py`；batch API |
| 关系管理 | parent_child、spouse、status、confidence | ✅ | relations API + 关系页 |
| 校正 | 待核对高亮、`review_status`、`ai_confidence` | ✅ | `review.py`；扫描结果列表 |
| 成员字段 | 字/号、县镇村、传记、审核状态 | ✅ | `db_schema.py` 迁移字段 |
| 族谱树 | 苏式 / 欧式 / 宝塔式 | ⚠️ | `tree.py` 输出 layout；**非** SVG 无限缩放 |
| 关系网图 | 按 status 区分线型 | ⚠️ | 简易展示；**非**力导向 |
| 搜索 | 关键词 | ✅ | `search.py` |
| 搜索 | 规则 NL（如「张三的弟弟」） | ✅ | `nl_search.py` |
| 导出 | JSON 导入导出 | ✅ | export/import API |
| 导出 | PDF（打印 HTML） | ✅ | `pdf_export.py`；`/export/pdf` |
| AI 设置 | 多 Provider、Key、GroupId、测试 | ✅ | `/api/ai/*` |
| 删除确认 | `confirm()` 一级确认 | ⚠️ | **无** Confirm-by-typing / 级联选项 |
| 媒体 | 图集相册、成员关联 | ❌ | 无 `media` 表 |
| 来源 | 扫描页/OCR 原文溯源 | ⚠️ | `ocr_records`；无独立 `source` 表 |
| 语音 | ASR / TTS / 对话式访谈 | ❌ | 设计构想 §二.1 |
| 批量编辑 | 框选多成员改籍贯/房支 | ❌ | 设计构想 §二.4 |
| NL 编辑 | 「将李四设为张三养父」 | ❌ | 设计构想 §二.4 |
| 智能建议 | ReAct 矛盾推理、待办提示 | ⚠️ | `validators` 规则校验；**无** ReAct 建议 API |
| 标签体系 | 四层标签、辈分诗、迁徙 JSON | ❌ | 设计构想 §三 |
| 协作 | 多人实时编辑、权限 | ❌ | 本地单用户 |
| 软删除/审计 | is_deleted、操作日志 | ❌ | 物理删除 |

### 3.2 智能体任务（已实现）

| 任务 | AI | API | 说明 |
|------|-----|-----|------|
| scan | ✅ OCR+解析 | `POST /api/agent/scan` | 内置 `auto_build_genealogy` |
| generate | ❌ | `POST /api/agent/generate` | 纯文本/规则也可建谱 |
| validate | ❌ | `POST /api/agent/validate` | 生卒年、重名等 |
| rebuild | ❌ | `POST /api/families/{id}/rebuild` | 对已有族谱重推理关系 |
| search | 可选 | `GET/POST .../search` | `mode=keyword` / NL 规则 |
| tree | ❌ | `GET .../tree?style=su\|eu\|tower` | |
| crud / import / export | ❌ | 见 §5 | |

### 3.3 测试基线

```bash
cd E:\resee\genealogy-agent
python -m pytest tests/ -v
```

当前：**63+ 项** pytest（含 `test_name_extractor`、`test_genealogy_builder`、`test_person_edit` 等）。发版前须全绿。

---

## 4. 设计构想融入：功能映射总表

将 HTML 文档五大模块 + 标签体系 + 智能提示，映射为**本地可开发的功能需求**（UI 表现待 UI PRD）。

### 4.1 交互方式升级（设计构想 §一、§二.1）

| 构想能力 | 本地功能需求 ID | 优先级 | 说明 |
|----------|-----------------|--------|------|
| 语音录入口述历史 | F-Voice-01 | P2 | Web Speech API 或本地 ASR 容器；文本写入 `biography` / 事件 |
| 渐进式访谈脚本 | F-Voice-02 | P3 | 破冰/深入/升华题库，输出结构化字段 |
| TTS / 声线克隆 | F-Voice-03 | v3+ | 不纳入近期本地 MVP |

### 4.2 图片与多模态（设计构想 §二.2）

| 构想能力 | 本地功能需求 ID | 优先级 | 说明 |
|----------|-----------------|--------|------|
| 批量上传 / 相册导入 | F-Media-01 | P1 | 新增 `media` 表，`person_id` / `family_id` 关联 |
| 族谱页 OCR（现有） | — | ✅ | 强化 prompt + `name_extractor` |
| 多模态图文联合解析 | F-OCR-02 | P2 | Vision 模型提取姓名+布局关系；输出与 scan 同 JSON  schema |
| 老照片修复着色 | F-Media-03 | v3+ | 本地 ComfyUI 容器，可选 |
| 版面关系（上下=父子） | F-OCR-03 | P2 | 解析结果增加 `layout_hint` 供建谱引擎 |
| AR 互动 | F-AR-01 | v3+ | 不做 |

### 4.3 可视化网络（设计构想 §二.3）— 功能侧

| 构想能力 | 本地功能需求 ID | 优先级 | 说明 |
|----------|-----------------|--------|------|
| SVG 矢量树、无限缩放 | F-Vis-01 | P1 | 替换/增强树渲染；**UI 交互细则见 UI PRD** |
| 瀑布 / 水平 / 力导向 | F-Vis-02 | P1 | 与现有 `su/eu/tower` 对齐并扩展 `force` |
| 悬停详情、展开收起 | F-Vis-03 | P1 | 依赖树组件事件 API |
| 节点拖拽重排 | F-Vis-04 | P2 | 仅改 `parent_id` / 关系，需冲突校验 |
| 千人级惰性加载 | F-Vis-05 | P2 | 按世代分页拉取 `GET .../tree?from_gen=&to_gen=` |
| IndexedDB 子图缓存 | F-Vis-06 | P3 | 前端缓存策略，属 UI/性能 PRD |

### 4.4 编辑与删除（设计构想 §二.4、§二.5）

| 构想能力 | 本地功能需求 ID | 优先级 | 说明 |
|----------|-----------------|--------|------|
| 节点快速编辑（姓名/生卒） | F-Edit-01 | P1 | 已有弹窗；需内联/API  PATCH 优化 |
| 批量编辑公共属性 | F-Edit-02 | P2 | `PUT /api/persons/batch` |
| NL 指令改关系 | F-Edit-03 | P2 | 复用 `nl_search` 解析 + `person_editor` 写库 |
| 删除二次确认（输入姓名） | F-Del-01 | P1 | 后端校验 `confirm_name` 字段 |
| 删除范围（仅本人 / 含后代） | F-Del-02 | P1 | `DELETE ...?cascade=children` |
| 软删除 + deleted_at | F-Del-03 | P2 | persons/relations 增加字段 |
| 操作审计日志 | F-Del-04 | P2 | `audit_logs` 表 |
| JWT 权限 | — | 不做 | 本地单用户 |

### 4.5 数据库标签体系（设计构想 §三）— 本地 SQLite 扩展

**原则**：不一期上 Neo4j；用**字段 + 枚举 + JSON 列**表达标签，供校验与搜索。

| 标签层 | 构想 | 本地字段/API 规划 |
|--------|------|-------------------|
| 血缘 | relation_subtype、过继、兼祧 | `relations.relation_subtype`；`persons.is_adopted` |
| 代际 | generation_index、辈分诗、昭穆 | `families.ancestral_verse`；`persons.zhaomu_rank` |
| 地域 | birth_place、residence_history | `persons.birth_place_json`；`residence_history_json` |
| 四层架构 | 基础/关系/事件/预测 | 事件表 `life_events`；预测层 v3+ 仅预留 |

**已有可复用**：`persons.generation`、`generation_name`、`courtesy_name`、`art_name`、`county/town/village`。

### 4.6 智能提示与 ReAct 建议（设计构想 §五）

| 构想能力 | 本地功能需求 ID | 优先级 | 说明 |
|----------|-----------------|--------|------|
| 字段缺失待办 | F-AI-01 | P1 | 扩展 `validate` → `suggestions[]` |
| 年龄/辈分矛盾预警 | F-AI-02 | P1 | 规则 + 可选 LLM 解释 |
| 生命周期提醒 | F-AI-03 | P3 | 需生日字段完整度 |
| 历史背景关联 | F-AI-04 | v3+ | |
| ReAct 优化建议 API | F-AI-05 | P2 | `POST /api/agent/advise`；输入族谱快照，输出可执行建议 |
| 人机协同置信度 | — | ⚠️ | 已有 `ai_confidence` / `review_status` |

---

## 5. API 一览（现有 + 规划）

### 5.1 已实现

| 方法 | 路径 | 说明 |
|------|------|------|
| GET/POST | /api/families | 族谱列表/创建 |
| PUT/DELETE | /api/families/{id} | 更新/删除 |
| GET | /api/families/{id}/persons | 成员列表 |
| GET | /api/persons/{id} | 成员详情 |
| POST/PUT/DELETE | /api/persons、/api/persons/{id} | 成员 CRUD |
| POST | /api/persons/batch | 批量入库 |
| GET/POST/PUT/DELETE | /api/relations | 关系 CRUD |
| GET | /api/families/{id}/tree | 族谱树 |
| GET/POST | /api/families/{id}/search | 搜索 |
| GET | /api/families/{id}/export、/export/pdf | 导出 |
| POST | /api/import | 导入 |
| POST | /api/agent/scan、/generate、/validate | 智能体 |
| POST | /api/families/{id}/rebuild | 重推理 |
| GET/POST | /api/ai/* | AI 配置 |

### 5.2 规划（融入设计构想）

| 方法 | 路径 | 需求 ID |
|------|------|---------|
| POST | /api/media/upload | F-Media-01 |
| GET | /api/families/{id}/media | F-Media-01 |
| PUT | /api/persons/batch | F-Edit-02 |
| DELETE | /api/persons/{id}?cascade=&confirm_name= | F-Del-01/02 |
| POST | /api/agent/advise | F-AI-05 |
| POST | /api/agent/edit-by-text | F-Edit-03 |
| GET | /api/families/{id}/tree | 扩展分页参数 F-Vis-05 |

---

## 6. 数据模型

### 6.1 现有表

| 表 | 说明 |
|----|------|
| families | 族谱 |
| persons | 成员（含字/号/籍贯/传记/审核/置信度） |
| relations | 关系（type、status、confidence） |
| ocr_records | 扫描记录 |
| ai_provider_keys、ai_settings | AI 配置 |

### 6.2 规划表/字段（对应 §4.5、§4.2、§4.4）

```text
media          — id, family_id, person_id?, path, mime, caption, created_at
audit_logs     — id, action, entity_type, entity_id, payload_json, created_at
life_events    — id, person_id, event_type, year, place_json, note
families       + ancestral_verse TEXT
persons        + is_deleted, deleted_at, is_adopted, birth_place_json, zhaomu_rank
relations      + relation_subtype TEXT
```

---

## 7. 智能体架构（目标态）

```
用户 → Vue 前端
     → FastAPI
         → Agent Engine
             ├─ scan_pipeline      （OCR → parse → name_extractor → auto_build → validate）
             ├─ genealogy_builder  （规则建谱 / rebuild）
             ├─ validators + advise  （矛盾检测 / 建议生成）  ← 设计构想 §五
             ├─ nl_search / edit-by-text
             └─ Tools: tree, search, CRUD, export, media
     → SQLite
     → 可插拔 AI（MiniMax / 其他 Vision+Text）
```

**扫描流水线（保持）**：

```
上传图片 → OCR → AI/规则解析 → refine_persons_list → auto_build_genealogy
         → validate + annotate_review → 用户确认 → batch 入库
```

---

## 8. 版本与实施路线（功能向，不含 UI）

与 design 文档「基础增强 → 智能跃迁 → 生态拓展」对齐，**压缩为本地可交付三期**：

### 8.1 v1.2 — 基础增强（≈设计构想 基础增强期 · 本地子集）

| 项 | 需求 ID | 交付物 |
|----|---------|--------|
| 删除安全 | F-Del-01/02 | API + 后端级联逻辑 |
| 媒体基础 | F-Media-01 | 表 + 上传/关联 API |
| 校验与待办 | F-AI-01/02 | advise 规则版（无 ReAct 亦可） |
| 树数据分页 | F-Vis-05 | 大树 API 分页 |
| 批量改成员 | F-Edit-02 | batch update API |

**依赖**：UI PRD 定稿后做 F-Vis-01/03 的前端（本阶段后端可先就绪）。

### 8.2 v1.3 — 智能跃迁（≈设计构想 智能跃迁期 · 本地子集）

| 项 | 需求 ID | 交付物 |
|----|---------|--------|
| 多模态扫描 | F-OCR-02/03 | Vision prompt + 版面关系字段 |
| 标签字段 | §4.5 | 迁移 + 校验规则（过继/辈分诗） |
| NL 改关系 | F-Edit-03 | edit-by-text |
| ReAct 建议 | F-AI-05 | advise API（LLM 可选） |
| 软删除+审计 | F-Del-03/04 | |

### 8.3 v2.0+ — 生态拓展（按需）

语音克隆、AR、区块链、Neo4j、预测层 — **仅作路线图，不阻塞 v1.2/v1.3**。

---

## 9. 测试策略

| 套件 | 覆盖 |
|------|------|
| test_name_extractor | 人名黑名单、行解析、AI 清洗 |
| test_genealogy_builder | 自动建谱、scan mock、generate API |
| test_pipeline | 扫描流水线 |
| test_person_edit | 父母配偶同步 |
| test_tree / test_search | 树与搜索 |
| test_api / test_genealogy_mvp | 端到端 API |

**新增需求时**：每个 `F-*` 功能至少 1 条 pytest 或 API 集成测试。

---

## 10. 交付标准（更新）

1. 无 AI 可手动建谱、浏览、导出 JSON/PDF  
2. 有 AI 可扫描老族谱，**人名误识别率可测**（`test_name_extractor`）  
3. 族谱树按**父子关系**展示，支持三版式（可视化增强随 UI PRD）  
4. 搜索支持关键词 + 规则 NL  
5. 删除高危操作具备**姓名确认 + 级联选项**（v1.2）  
6. `pytest` 全绿后发版  

---

## 11. 与旧 plans / 设计构想的关系

| 文档 | 关系 |
|------|------|
| `C:\Users\20870\.cursor\plans\` 五份计划 | MVP 8 页与数据模型源头；本地已覆盖核心链路约 **75%**（较旧 PRD 60–70% 上调） |
| `族谱智能体优化建议与设计构想.html` | **功能扩展蓝图**；§4、§8 为融入本地的需求分解 |
| 后续 **UI PRD** | **见 [`PRD-UI-交互.md`](./PRD-UI-交互.md)**：当前实现的页面结构、抽屉/弹窗分工、差异确认流程；**不重复定义业务规则** |

---

## 12. 待用户输入（下一步）

1. **UI 交互 PRD**：已见 [`PRD-UI-交互.md`](./PRD-UI-交互.md)；后续迭代 F-Vis-*、校正拖拽等在此文档增补。  
2. **优先级确认**：v1.2 是否先做「删除安全 + 媒体」还是「可视化 + 删除」并行。  
3. **多模态 Provider**：是否固定 MiniMax Vision 或增加 Qwen-VL 等（影响 F-OCR-02 排期）。

---

## 附录 A：设计构想章节 → 本地章节对照

| 设计构想 HTML 章节 | 本地 PRD |
|--------------------|----------|
| 一、总体优化方向 | §1、§2 |
| 二、关键功能模块（1–5） | §4.1–4.4 |
| 三、数据库标签体系 | §4.5、§6.2 |
| 四、实施路线图 | §8 |
| 五、智能提示与 ReAct | §4.6、§7 |

---

## 附录 B：品牌色（功能 PRD 保留，细节以 UI PRD 为准）

| 颜色 | 色值 | 用途 |
|------|------|------|
| 暖棕 | #8B6F47 | 主色、男系 |
| 金棕 | #C9A961 | 辅色、连线 |
| 琥珀橙 | #D48C4A | 强调、女系 |
| 米白 | #F9F5F0 | 背景 |
| 深棕灰 | #4A3F35 | 文字 |

（设计构想 HTML 使用蓝色系 Tailwind 主题；**落地时以族见品牌色为准**，UI PRD 统一定稿。）
