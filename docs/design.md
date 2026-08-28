# KnowBase 架构设计

## 1. 目标

一个可部署、可演示、代码质量能代表个人水平的全栈 + AI 作品：

1. **程序员客栈签约作品**：完整可运行、有在线演示地址、有截图、有详细描述。
2. **AI 落地服务获客 demo**：向中小企业演示"知识库问答"的最短落地路径。
3. **接单标杆**：后续接"知识库 / 客服机器人 / RAG"类需求时直接复用。

## 2. 角色与场景

- 普通用户：注册登录，创建多个知识库，上传文档，向单个知识库提问。
- 演示场景：上传一份《产品手册.pdf》→ 解析完成后提问 → 回答带引用 → 点击引用查看原文片段。

## 3. 技术选型理由

| 组件 | 选择 | 理由 |
|---|---|---|
| 后端框架 | FastAPI | AI 生态最全、原生支持 SSE 流式、异步性能好 |
| 主数据库 | MySQL 8 | 结构化元数据；接单市场认知度最高 |
| 缓存 | Redis 7 | 会话状态、解析任务状态、后续限流 |
| 向量库 | Qdrant | 单容器部署、过滤检索、生产可用 |
| 大模型 | OpenAI 兼容 API | DeepSeek/GLM/Qwen/SiliconFlow 全兼容，可插拔是卖点 |
| 前端 | React 18 + Vite + TS + AntD | 国内接单主流后台栈，AntD 出活快、观感专业 |

## 4. 数据模型（MySQL）

```
user          (id, email, password_hash, created_at)
knowledge_base (id, user_id, name, description, created_at)
document       (id, kb_id, filename, file_type, size, status, chunk_count, error, created_at)
               status: pending | parsing | ready | failed
chunk          (id, document_id, kb_id, seq, content, page, vector_id, created_at)
conversation   (id, kb_id, user_id, title, created_at)
message        (id, conversation_id, role, content, citations_json, created_at)
```

Qdrant 侧：每个知识库一个 collection，`chunk` 表的 `vector_id` 对应 Qdrant point id，point payload 冗余 `kb_id/document_id/chunk_id` 用于过滤删除。

## 5. RAG 流程

**入库（异步）**：上传 → 保存文件 → document(pending) → 后台任务解析（按文件类型提取文本 + 页码）→ 切片（500 字，重叠 50）→ 调 embedding API → 写入 Qdrant + chunk 表 → document(ready)。

**问答**：问题 → embedding → Qdrant 检索 top_k=5（按 kb_id 过滤）→ 组装带编号来源的 prompt → LLM 流式生成（SSE）→ 前端渲染 `[1][2]` 引用，点击展示对应原文片段（来自 chunk 表）。

Prompt 约定：只依据提供的资料回答，资料不足时明确说明，引用标注使用 `[n]`。

## 6. API 一览

```
POST /api/auth/register        注册
POST /api/auth/login           登录，返回 JWT
GET  /api/kbs                  我的知识库列表
POST /api/kbs                  创建知识库
DELETE /api/kbs/{id}           删除知识库（级联清理向量）
POST /api/kbs/{id}/documents   上传文档（multipart）
GET  /api/documents/{id}       文档状态 / 元信息
GET  /api/documents/{id}/chunks切片预览
DELETE /api/documents/{id}     删除文档（级联清理向量）
POST /api/kbs/{id}/chat        问答，SSE 流式返回
GET  /api/conversations/{id}/messages
GET  /health                   健康检查
```

## 7. 里程碑

| 阶段 | 内容 | 预估 |
|---|---|---|
| M1 | 骨架 + docker-compose + 认证 + 知识库 CRUD | 2-3 天 |
| M2 | 文档解析/切片/向量化流水线 + 状态机 | 3-4 天 |
| M3 | 检索问答 + SSE + 引用溯源 | 2-3 天 |
| M4 | 前端打磨 + 部署上线 + README 截图 + 开源整理 | 1-2 天 |

## 8. 部署

- 演示环境：一台轻量云服务器（2C4G 起即可），docker compose 全家桶 + 前端 build 产物由 nginx 托管。
- 演示域名 + HTTPS（Let's Encrypt），保证"有效链接"可长期访问（签约审核要求）。

## 9. 后续扩展（面试/接单谈资，不急于实现）

- 混合检索（BM25 + 向量 + 重排序 bge-reranker）
- 企微 / 公众号 / 网页挂件接入（接单时的付费增项）
- 多租户与配额、用量计费
