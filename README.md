# 族见 · 本地版（genealogy-agent）

> 见家族，见自己。

本地优先的族谱智能体：**Vue 3 + Vite** 前端，**FastAPI + SQLite** 后端。数据在本地，可备份、可迁移。

与云端 uni-app 版的关系见：[gavinlian/resee](https://github.com/gavinlian/resee)（小程序 / H5 / Unicloud）。

## 技术栈

| 层级 | 技术 |
|------|------|
| 前端 | Vue 3、Vite、TypeScript |
| 后端 | Python、FastAPI、SQLite |
| AI | 可配置 OCR / 关系解析模型（MiniMax、硅基流动等） |

## 目录

```
genealogy-agent/
├── src/           前端源码
├── backend/       API 与智能体
├── tests/         测试
├── docs/          文档（含 PRD）
└── scripts/       工具脚本
```

## 快速开始

```bash
# 前端
npm install
npm run dev          # http://localhost:3000

# 后端（另开终端）
cd backend
python main.py       # http://localhost:8080
```

```bash
# 测试
python -m pytest tests/
npm run build
```

## 文档

- 功能 PRD：`docs/PRD/PRD.md`
- 界面交互 PRD：`docs/PRD/PRD-UI-交互.md`

## License

MIT

## Git 与远程仓库

本目录为**独立仓库**（`main` 分支），与 [gavinlian/resee](https://github.com/gavinlian/resee)（uni-app 云端版，`e:\resee\uiapp`）分开管理。

**不会提交到 Git 的内容**：`node_modules/`、`dist/`、`backend/genealogy.db`、`.env`、`backend/uploads/` 内实际上传文件。

首次推送到 GitHub（在网页新建空仓库 `genealogy-agent` 后）：

```bash
git remote add origin git@github.com:gavinlian/genealogy-agent.git
git push -u origin main
```

日常提交：

```bash
git add -A
git status   # 确认无 .env / .db
git commit -m "feat: 简述改动"
```
