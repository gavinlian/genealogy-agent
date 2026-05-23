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
