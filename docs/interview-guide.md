# KnowBase 项目全解：设计理念 · 架构 · 难点 · 面审 Q&A

> 用途：程序员客栈签约审核 / 客户面谈的准备手册。
> 原则：所有内容与线上真实系统一致（演示：http://8.216.24.166 ，开源：github.com/JamesByte2/knowbase），可现场演示、可现场翻代码。

---

## 一、项目概述

**一句话**：面向中小企业的私有知识库问答系统——把企业的文档（产品手册、员工手册、制度、说明书）传上去，员工用自然语言提问，系统基于文档内容回答，**每句话都带引用来源，可点开看原文**。

**解决的真实痛点**：中小企业文档一堆（Word/PDF 散落在各处），员工找个答案要翻半天，问同事又打断别人。传统方案两条路都不好走：买大厂知识库产品贵且数据出域；自己做 RAG 门槛高。KnowBase 给出第三条路：**开源自部署 + 数据不出域 + 按需可插拔模型**。

**目标用户**：有 20-500 篇内部文档、想要一个"内部百度"的中小企业。

**演示数据**（面审可主动报出的数字）：
- 后端 FastAPI + MySQL 8.4 + Redis 7 + Qdrant；前端 React 18 + TypeScript + Ant Design 5
- 向量模型 BAAI/bge-m3（1024 维）；对话模型 Qwen3-8B（免费档），全链路 OpenAI 兼容接口
- 切片策略 500 字 / 重叠 50；检索 top_k=5
- 三套自动化冒烟测试：M1 认证与知识库 9/9、M2 入库流水线 7/7、M3 RAG 问答 8/8
- 生产部署：阿里云香港轻量服务器（1GB 内存），Docker + systemd + nginx，月成本约 0 增量（模型 API 全免费档）

---

## 二、设计理念

### 1. 可溯源压倒一切（anti-hallucination first）
知识库产品的生死线是"可信"。企业场景里一次编造（比如把保修 2 年说成 1 年）就会让用户永久失去信任。所以三个设计决策都围绕它：
- 回答强制基于检索片段，prompt 明确"资料不足就直接说没有，不要编造"；
- 回答中用 `[n]` 标注引用，前端可展开看**原文片段 + 文档名 + 页码**；
- 空检索（top_k 无结果）时不调用生成，直接返回"知识库中没有相关内容"。

### 2. 模型可插拔（OpenAI 兼容接口）
对话模型和向量模型都走 OpenAI 兼容协议，改 `.env` 两行即可从免费的 Qwen3-8B 切到 DeepSeek/GLM/通义，未来也能切到本地私有模型（vLLM/Ollama 同样兼容）。**这正是卖给客户的卖点**：客户问"模型用什么、数据会不会泄露"，答案是"随你换，还能整体私有化"。

### 3. 工程状态机，不让任务静默死亡
文档入库是异步长任务（解析→切片→向量化→写向量库），任何一步都可能失败。设计为显式状态机 `pending → parsing → ready | failed`，**任何异常都会落到 failed 并把原因写进数据库**，前端可视化展示。这条在线上真的救过场：一次服务器内存风暴把流水线打断，重启后该文档正确显示"失败 + 原因"，而不是永远"解析中"。

### 4. 为部署环境妥协，但不牺牲架构
线上跑在 1GB 内存的轻量服务器上，为此做了容器内存上限（MySQL 380M / Qdrant 420M）、2G swap、MySQL 关闭 performance_schema 等调优——但架构上没有降级：数据服务仍容器化隔离、后端仍 systemd 托管、数据库仍只绑 127.0.0.1 不暴露公网。**穷有穷的部署法，但边界一样严谨。**

---

## 三、架构解析

### 3.1 分层图

```
浏览器（React + AntD）
   │  REST（登录/知识库/文档管理） + SSE（问答流式）
nginx :80 ──静态资源──▶ React 构建产物
   │ /api/ 反代（SSE 关闭缓冲）
   ▼
FastAPI (uvicorn, systemd, 127.0.0.1:8000)
   │                │                │
   ▼                ▼                ▼
MySQL 8.4       Qdrant          Redis
(元数据/切片/   (向量检索,      (预留:缓存/队列)
 会话消息)      每库一collection)
   ▲
   └── 入库/问答时调用 SiliconFlow（OpenAI 兼容：bge-m3 向量化 + Qwen3-8B 生成）
```

### 3.2 数据模型（MySQL 六张表）

```
user(id, email, password_hash, created_at)
knowledge_base(id, user_id, name, description, created_at)
document(id, kb_id, filename, stored_name, file_type, size,
         status[pending|parsing|ready|failed], chunk_count, error, created_at)
chunk(id, document_id, kb_id, seq, content, page, vector_id, created_at)
conversation(id, kb_id, user_id, title, created_at)
message(id, conversation_id, role, content, citations_json, created_at)
```

要点：
- **chunk 同时存 MySQL 和 Qdrant**：MySQL 存原文（引用溯源要展示原文），Qdrant 只存向量和 payload 索引（kb_id/document_id/chunk_id/page）。
- **Qdrant 每个知识库一个 collection**（`kb_{id}`），检索时按 kb_id 过滤，隔离清晰、删除知识库即删 collection。
- message 的 citations_json 把当次回答的引用快照下来——**用户半年后翻历史会话，看到的引用还是当时的**，不受文档后续修改影响。

### 3.3 链路一：文档入库流水线（异步）

```
上传(multipart, ≤50MB, 白名单 pdf/docx/xlsx/md/txt)
  → 落盘（uuid 存储名，防路径问题）
  → document(pending)，后台线程启动流水线
  → 解析 parser.py：PDF 按页提取(页码保留)；docx 合并段落；xlsx 按工作表转行文本；md/txt 直读
  → 切片 chunk_text：先按段落聚簇成 ≤500 字的块，超长段落硬切，相邻块间保留 50 字重叠
  → 向量化 embed_texts：bge-m3，batch=32
  → 先 db.flush() 让 chunk 拿到自增 id
  → Qdrant upsert（payload: kb_id/document_id/chunk_id/seq/page）
  → document(ready, chunk_count=N)
任一步异常 → document(failed, error=原因)
```

**为什么先 flush 再 upsert**：Qdrant 的 point payload 里要冗余 chunk 的 MySQL 自增 id，用于检索后反查原文。如果不先 flush，id 还是 None，检索结果的引用就断了——这是一个真实踩过的 bug（详见难点 5.1）。

### 3.4 链路二：RAG 问答（SSE 流式）

```
POST /api/kbs/{id}/chat {question, conversation_id?}
  1. 鉴权 + 会话归属校验；用户消息落库
  2. 问题向量化（bge-m3）
  3. Qdrant query_points：top_k=5，filter kb_id
  4. 用 payload.chunk_id 反查 MySQL，联出 filename/page/content（RetrievedChunk）
  5. 组装 prompt：SYSTEM（仅依据编号资料回答 + [n] 标注 + 资料不足明说）+ 编号资料 + 问题
  6. SSE 依次推送事件：
     meta(conversation_id) → token*N（逐字）→ citations(快照) → done
     异常 → error 事件（前端也能优雅展示）
  7. 流结束后助手回答 + 引用 JSON 落库
```

### 3.5 API 面（12 个端点）

```
POST /api/auth/register|login          JWT 认证（HS256 + pbkdf2 密码哈希）
GET/POST/DELETE /api/kbs[...]          知识库 CRUD（删除级联清切片+向量）
GET/POST /api/kbs/{id}/documents       文档列表/上传（触发流水线）
DELETE /api/documents/{id}             删文档（同步删向量）
GET /api/documents/{id}/chunks         切片预览
POST /api/kbs/{id}/chat                RAG 问答（SSE）
GET /api/kbs/{id}/conversations        会话列表
GET /api/conversations/{id}/messages   历史消息（含引用快照）
GET /health                            健康检查
```

---

## 四、亮点设计（面审主动讲的五张牌）

### 4.1 引用溯源是产品级实现，不是 demo 级
不是"回答里写个来源"就算——而是：检索时保留 score 和页码 → 回答后**引用快照随消息持久化** → 前端可展开原文片段 → 历史会话里的引用永不失效。这条链路横跨检索、生成、存储、前端四层。

### 4.2 免费模型是有测评的选型，不是白嫖
用同一组 RAG 测试题对比了 SiliconFlow 三个免费模型：**Qwen2.5-7B 把"保修 2 年"答成"保修 1 年"（量化小模型幻觉），直接否决**；Qwen3-8B 与 14B 都正确且引用规范，最终选 8B（速度/质量平衡）。这个过程说明：免费 ≠ 随便用，小模型在 RAG 场景下的幻觉必须实测。

### 4.3 一致性边界清晰：MySQL 是事实源，Qdrant 是索引
所有删除操作（删文档/删知识库）都是先删 MySQL（事务）再清 Qdrant（按 filter 或整 collection）。检索后用 chunk_id 反查 MySQL，**反查不到的向量结果防御性跳过**——即使出现双写不一致（向量残留），系统也只是召回少一条，不会 500 或引用错乱。

### 4.4 安全边界不做样子
- 数据服务只绑 127.0.0.1，公网扫描不到 3306/6379/6333；
- 密码 pbkdf2-HMAC-SHA256 十万轮加盐；JWT HS256 72h 过期；
- 所有资源访问都校验归属（`_owned_kb`：kb 不存在和"存在但不属于你"统一返回 404，不泄露存在性）；
- ORM 参数化，无裸 SQL 拼接；上传有类型白名单 + 50MB 上限 + uuid 存储名。

### 4.5 全链路自动化测试进仓库
`scripts/smoke_m1.py / smoke_m2.py / smoke_m3.py` 对运行中的系统做真实链路验证（不是 mock 单元测试）：注册→上传→**真实调用向量 API**→检索→流式生成→引用校验→越界拒答校验→清理。部署完服务器后同样的脚本对公网再跑一遍。**敢把"对真实系统跑"的测试写进仓库，是对稳定性的自信。**

---

## 五、难点拆解（踩坑实录，每条都是真实发生的）

### 5.1 双写一致性：向量库 payload 里 chunk_id 为 None
**现象**：入库成功、检索召回 0 条。排查发现 Qdrant payload 里 `chunk_id: None`——写向量时 Chunk 还没落库，拿不到自增 id。
**修复**：先 `db.add_all + db.flush()`（拿到 id）再 `qdrant.upsert`，最后 commit。
**引申答法**：任何"关系库 + 外部索引"双写都有顺序问题，我的原则是**先让事实源（MySQL）拿到完整标识，再写索引**；并留了防御（反查不到就跳过）。

### 5.2 1GB 内存服务器的部署调优
**现象**：全部组件直接跑会被内存抖动拖进 swap 风暴（真实发生：一次流水线 + 容器初始化叠加，SSH 都无响应）。
**处置**：2G swapfile 兜底；容器内存硬限（MySQL 380M / Qdrant 420M / Redis 64M）；MySQL 关 performance_schema、buffer pool 压到 48M、max_connections=30；带内存监视器重跑验证，空闲 606M 稳定。
**引申答法**：小机器部署的核心不是"能跑"，而是**给每个组件画内存红线 + 让故障可观测**（状态机 + 监视日志），风暴后能定位、能恢复。

### 5.3 SSE 穿过 nginx 的坑
SSE（`text/event-stream`）会被 nginx 默认缓冲攒够一块才下发，前端就失去"打字机"效果。解法：`proxy_buffering off; proxy_cache off;` + `proxy_read_timeout 300s`；前端用 `fetch + ReadableStream` 手写 SSE 解析（axios 不支持流式），按 `\n\n` 分帧处理半包粘包。

### 5.4 免费小模型的幻觉实测
5.2 已述。补充方法论：**选模型不能看排行榜，要用自己业务的最小用例集测**——同一个"保修几年"的问题，三个免费模型两对一错。

### 5.5 生产事故：状态机的价值
一次入库赶上服务器初始化叠加，进程被打断。因为有状态机，重启后该文档显示 `failed + 原因`，用户可以重新上传；如果当初用"日志里打一下"的做法，这条文档就永远卡在"解析中"。

### 5.6 其他工程细节
- **认证与资源隔离**：404 统一返回，避免水平越权探测；
- **级联删除**：删知识库 = 事务删 chunks/documents + 删 Qdrant collection；
- **文件存储名用 uuid**：防中文文件名/路径穿越/重名；
- **模型切换**：从 7B 换 8B 只改了 `.env` 一行——可插拔设计直接兑现。

---

## 六、面审 Q&A 预案

**Q1：为什么用 Qdrant？为什么不用 pgvector / Milvus / ES？**
A：选型标准是"单机部署成本 + 过滤检索能力 + 运维复杂度"。pgvector 能省一个组件，但把向量负载压进主库，且当时团队（个人）对 MySQL 生态更熟，不想为了向量换 PG；Milvus 面向大规模分布式，单机知识库场景太重；ES 混合检索强但 JVM 内存吃不消（1G 机器）。Qdrant 单二进制、支持 payload 过滤（kb_id 隔离正好用上）、有官方 Python 客户端。**补一句边界**：如果客户已有 PostgreSQL，我会直接换 pgvector 方案，架构不变只换存储层。

**Q2：切片为什么是 500 字重叠 50？怎么评估效果？**
A：500 字约对应一段完整语义（几个段落），同时 embedding 模型（bge-m3 支持 8192 token）不会截断；50 字重叠保证跨块的句子在至少一个块里完整。实现上不是无脑硬切：先按段落聚簇成 ≤500 字的簇，只有单段超长才硬切，避免把语义切碎。**评估**：当前用固定测试题做定性回归（smoke_m3 里的保修/年假问题），诚实说没有做系统的召回率指标；改进方向是建一个小标注集算 hit@k，以及加 BM25 混合检索。

**Q3：怎么防止大模型幻觉？**
A：四层：① prompt 硬约束"仅依据编号资料回答，资料不足明说"；② 空检索直接拒答，不进生成；③ 引用标注 [n]，前端可溯源；④ 温度压到 0.3。并做过实测：用小模型时幻觉真实出现（2 年答成 1 年），所以换成了实测过关的 Qwen3-8B。**补边界**：无法 100% 消除，所以引用溯源让用户可核验——这是工程上对幻觉的务实态度。

**Q4：SSE 为什么不用 WebSocket？**
A：问答是"一问一答的单向流"，SSE 基于 HTTP 就够：穿过 nginx/CDN 更简单、自带断线语义、实现量小。WebSocket 适合双向高频场景（协同编辑）。另外 SSE 事件里设计了类型（meta/token/citations/done/error），协议比"裸文本流"更可维护。

**Q5：MySQL 和 Qdrant 双写，一致性怎么保证？**
A：写路径顺序 = 先 flush MySQL 拿 id，再写 Qdrant，最后统一 commit；失败路径 = 状态机标 failed，残留向量靠"检索后反查 MySQL，查不到跳过"兜底（宁少召回不错乱）。删除路径 = 先删 MySQL 再删向量，同样兜底。**诚实说**：没有做分布式事务，但知识库场景允许最终一致 + 防御式读取，这是性价比最高的方案；要更严可以加对账任务。

**Q6：并发上传会怎样？瓶颈在哪？**
A：当前流水线是"每文档一个后台线程"，demo 和小团队没问题；瓶颈在三个地方：线程无上限、embedding 串行 batch、单 worker。改进路线（按序）：入队到 Redis 队列 + 固定 worker 数（Redis 已在架构里预留）→ 上传改为分块续传 → 超大 PDF 拆页并行。**这题的答法是承认边界 + 给出演进路径**，当前定位是 20-500 篇文档的中小企业，不是文档工厂。

**Q7：支持多轮对话吗？**
A：会话和消息已持久化（含引用快照），前端按会话续问；**生成侧目前每轮独立检索、不携带历史**——这是刻意的第一版取舍：RAG 场景里历史混入容易把检索意图带偏。演进方向：先用查询改写（把"那第二种呢？"改写成独立问题）再检索，而不是简单拼历史。

**Q8：数据安全怎么考虑？**
A：四层：传输（HTTP 时仅内网组件通信，公网建议配 https，域名就绪即可开）；认证（pbkdf2 十万轮 + JWT）；隔离（数据服务只绑 127.0.0.1，资源归属校验防水平越权）；可私有化（模型接口可切本地 vLLM，数据全程不出企业内网）——最后一点是接单时的核心卖点。

**Q9：为什么自己写而不用 Dify/MaxKB？**
A：两个理由。做产品：低代码平台的溢价点在"知识治理、系统集成、持续运营"，这些恰恰需要自有代码才能做到（比如引用快照、双写一致性、小内存调优）；做工程：这个项目本身就是交付能力的证明——从切片算法、SSE 协议、双写一致性到 1G 内存调优，每一层都能讲清楚。**且不冲突**：客户已买 Dify 时，我可以做 Dify 的二开和运维。

**Q10：项目成本和后续商业化？**
A：当前线上运行零模型成本（免费档），服务器约 30-40 元/月。商业化按"搭建费 + 月度运维费"：标准交付 1-2 周（文档整理、部署、企微/公众号接入为增项），运维费覆盖知识库运营（坏文档处理、效果调优）。技术 roadmap：混合检索 + 重排序、Excel/Q&A 对增强解析、企微机器人接入、多租户。

**Q11（可能的压力题）：这项目 AI 写的吧？**
A：大方承认工作流：**AI 辅助编码 + 我做架构决策、选型、验收和运维**，这本身就是我的生产力卖点——并给出只有"真Owners"才答得上来的证据：三次线上故障的处置（chunk_id 断链、swap 风暴、模型幻觉实测）、每个模块的取舍原因、三套冒烟测试的用例设计。代码在 GitHub 全公开，欢迎任意深挖。

---

## 七、诚实清单（自己知道、别等审核问）

| 项 | 现状 | 计划 |
|---|---|---|
| Redis | 容器已跑，代码预留未使用 | 接任务队列（Q6 路线） |
| https | 未配（无域名） | 买域名 + Let's Encrypt，半小时 |
| 登录后偶发不自动跳转 | 前端状态小 bug，刷新即正常 | 修 |
| 检索评估 | 定性回归测试 | 建标注集算 hit@k |
| 并发上传 | 线程无上限 | Redis 队列 |
| 多轮上下文 | 每轮独立检索 | 查询改写 |
| i18n / 权限角色 | 无 | 客户需求驱动 |

> 面审心法：主动讲"取舍"和"边界"，被问到没做的就说"当前版本没做，因为 X；要做的话路线是 Y"。**审核淘汰的是吹牛的人，不是有 roadmap 的人。**

---

## 八、速记卡（面审前 10 分钟看这个）

- 演示：http://8.216.24.166 （账号可现场注册，或用演示库"产品演示库"直接问）
- 代码：github.com/JamesByte2/knowbase（8+ commits，M1→M4 全记录）
- 栈：FastAPI / MySQL 8.4 / Redis 7 / Qdrant / React18+TS+AntD5 / Docker+systemd+nginx
- 模型：Qwen3-8B（免费）+ bge-m3（免费，1024 维），OpenAI 兼容可插拔
- 关键参数：切片 500/50，top_k=5，JWT 72h，上传 ≤50MB 白名单 5 类
- 测试：smoke_m1 9/9、m2 7/7、m3 8/8（真实链路冒烟，进仓库）
- 三个可讲的故障：chunk_id 断链（双写顺序）、swap 风暴（1G 调优）、7B 幻觉实测（模型选型）
- 一句话定位：**给中小企业一个"带引用、可溯源、能私有化"的内部知识库，两周交付，月费运维。**
