# KnowBase · AI 知识库问答系统

面向中小企业的私有知识库问答系统：上传文档（PDF/Word/Markdown/Excel），自动解析、切片、向量化，基于大模型进行检索增强问答（RAG），回答附带**引用溯源**（可查看原文片段）。

**在线演示**：http://8.216.24.166 （阿里云香港轻量服务器，Docker + systemd + nginx 部署）

> 技术栈：Python 3.12 + FastAPI + MySQL + Redis + Qdrant + React 18 + Ant Design

## 功能亮点

- 多知识库隔离，支持注册/登录（JWT）
- 文档解析流水线：PDF / DOCX / Markdown / TXT / XLSX，解析状态可视（pending → parsing → ready / failed）
- 切片向量化入库，切片内容可预览
- RAG 问答：向量召回 top-k + 大模型流式生成（SSE）
- **引用溯源**：回答中的 `[1][2]` 标注可展开查看原文出处
- 大模型可插拔：OpenAI 兼容接口，DeepSeek / GLM / Qwen / SiliconFlow 均可通过 `.env` 切换

## 架构

```
React (Vite + AntD)
   │  REST / SSE
FastAPI ──── MySQL      （用户 / 知识库 / 文档 / 会话元数据）
   │    └── Redis       （缓存 / 会话状态）
   └──────── Qdrant     （向量检索）
        │
        └── LLM API（OpenAI 兼容，可插拔）
```

## 快速开始

```bash
# 1. 启动基础设施（MySQL / Redis / Qdrant）
docker compose up -d

# 2. 后端
cd backend
pip install -r requirements.txt
cp .env.example .env   # 填入 LLM_API_KEY 等
uvicorn app.main:app --reload --port 8000

# 3. 前端
cd frontend
npm install
npm run dev            # http://localhost:5173
```

## 开发进度

- [x] M1 项目骨架 / 用户认证 / 知识库 CRUD（后端冒烟测试 9/9 通过，前后端端到端联调完成）
- [x] M2 文档解析 - 切片 - 向量化流水线（真实 API 链路冒烟 7/7 通过：上传→ready→切片可查，含失败状态机）
- [x] M3 RAG 检索问答 + SSE 流式 + 引用溯源（8/8 通过：答案带引用、消息持久化、越界拒答）
- [ ] M3 RAG 检索问答 + SSE 流式 + 引用溯源
- [ ] M4 前端打磨 / 部署上线 / 截图文档

详细设计见 [docs/design.md](docs/design.md)。
