# AI Agent 开发、运行与评测平台

基于 **FastAPI + LangGraph + PostgreSQL/pgvector + RQ + Langfuse** 构建的企业级 AI Agent 平台：
可配置 Agent（提示词/模型/工具/知识库）、RAG 知识库、Agent 版本快照与回滚、
LLM-as-Judge 自动化评测、全链路 Langfuse trace 观测。

## 功能全景

| 模块 | 说明 |
|------|------|
| Agent 运行时 | LangGraph ReAct 图（chat ⇄ tool_call），Human-in-the-loop 审批中断，流式响应 |
| 多模型网关 | 全部 LLM 调用经 OpenAI 兼容网关（LiteLLM Proxy），对话/记忆/Judge 统一入口 |
| RAG 知识库 | 文档上传（txt/md/pdf）→ 切片 → embedding（本地 bge 或远程 OpenAI 兼容）→ pgvector HNSW 余弦检索，作为图节点自动注入 |
| 工具 | calculator、document_search（封装知识库检索）、搜索、图表、人工确认 |
| 版本管理 | 配置快照（工具存完整定义，自包含）、软回滚（新建版本留审计）、按 v1/v2/v3 复现运行 |
| 评测 | 测试集/用例 → RQ 异步串行执行 → 三档工具判分 + RAG recall + LLM Judge 三维打分 → 版本对比报告 |
| 可观测性 | Langfuse trace 树（agent/retriever/tool/llm），本地 metrics 表，结构化日志（structlog） |
| 基础 | JWT 认证、RBAC（user/admin）、slowapi 限流、mem0 长时记忆 |

## 技术栈

| 类别 | 技术 |
|------|------|
| Web 框架 | FastAPI |
| AI 编排 | LangGraph + LangChain |
| 数据库 | PostgreSQL 16 + pgvector（HNSW） |
| ORM / 迁移 | SQLModel / Alembic（迁移 01-09） |
| 任务队列 | Redis + RQ（评测异步执行） |
| Embedding | sentence-transformers（本地 bge-small-zh，512 维）/ OpenAI 兼容接口 |
| 观测 | Langfuse v4（自托管） |
| 容器 | Docker Compose（db / redis / app / worker） |

## 目录结构

工作区根目录（AIRAG/）布局：

```
AIRAG/
├── main_project/                # 本项目（核心，旧名 zhuanyexiangmu）
├── experiments/                 # 实验/学习代码（agent实验、LangGraph练习、PGVector练习、RAG-Knowledge-Chat、rag项目）
├── configs/                     # 工作区级配置
├── scripts/                     # 工作区级脚本
├── docs/                        # 工作区级文档
├── .venv/                       # Python 虚拟环境（已 gitignore）
└── logs/
```

`main_project/` 内部结构：

```
main_project/
├── app/
│   ├── api/v1/                  # REST 接口层（统一复数/语义化命名）
│   │   ├── agents.py / my.py    # Agent 管理（公共/私有），含知识库绑定
│   │   ├── agent_services.py    # 会话与对话（支持 version_no/version_id 按版本运行）
│   │   ├── knowledge.py         # 知识库/文档/检索/绑定 API
│   │   ├── versions.py          # 版本发布/列表/详情/软回滚
│   │   ├── evaluation.py        # 测试集/用例/评测 run/续跑/对比
│   │   ├── admin.py             # 管理端接口（复用 v1 鉴权，挂在 /api/v1/admin）
│   │   └── router.py            # 路由聚合
│   ├── core/
│   │   ├── config.py            # 全部环境变量（settings）
│   │   ├── langgraph/
│   │   │   ├── graph.py         # ReAct 图：retrieve_knowledge → chat ⇄ tool_call
│   │   │   └── tools/           # calculator / document_search / ...
│   │   └── observability/       # Langfuse handler（可开关，业务零埋点）
│   ├── models/                  # SQLModel：user/agent/rag/version/evaluation/metrics...
│   ├── schemas/                 # Pydantic 校验
│   ├── services/
│   │   ├── llm/                 # 模型注册表（三级：Agent 配置→网关→默认）
│   │   ├── embedding.py         # 双 provider embedding（local/openai）
│   │   ├── rag_service.py       # 文档解析/切片/embedding/pgvector 检索
│   │   ├── version_service.py   # 快照发布与软回滚
│   │   ├── agent_runtime_service.py  # build_config：当前配置 或 版本快照还原
│   │   ├── memory.py            # mem0 长时记忆
│   │   └── evaluation/
│   │       ├── judges.py        # 三档工具判分 / LLM Judge / RAG recall
│   │       └── runner.py        # 串行执行评测 case（按版本快照）
│   └── tasks/
│       └── evaluation_worker.py # RQ 入队 + worker 入口（含 Windows 兼容模式）
├── alembic/versions/            # 01 init … 07 RAG / 08 版本 / 09 评测
├── docs/                        # API 与模块文档
├── docker-compose.yml           # db + redis + app + worker（项目名固定为 zhuanyexiangmu）
└── main.py                      # 入口（lifespan 初始化 Langfuse）
```

## 本地开发

### 1. 依赖与配置

```bash
python -m venv .venv
.venv\Scripts\Activate.ps1        # Windows
pip install -r requirements.txt

copy .env.example .env            # 填入网关 key、数据库、Langfuse 等
```

前置服务：

- **PostgreSQL + pgvector**：`docker compose up -d db`
- **Redis**（评测队列）：`docker compose up -d redis`
- **LLM 网关**：本地 LiteLLM Proxy（OpenAI 兼容），配 `GATEWAY_*`
- **Langfuse**（可选）：`langfuse/` 目录 `docker compose up -d`，配 `LANGFUSE_*`

### 2. 数据库迁移

```bash
alembic upgrade head              # 建表至 09（含 vector 扩展与 HNSW 索引）
```

首次使用需初始化内置工具：

```bash
python -m app.cli.init_tools
```

### 3. 启动 API 与评测 worker

```bash
# API
uvicorn main:app --host 127.0.0.1 --port 8000

# 评测 worker（二选一）
python -m app.tasks.evaluation_worker                    # Windows：SimpleWorker 同进程串行
rq worker evaluations --url redis://localhost:6379/0     # Linux/Docker：标准多进程 worker
```

- API 文档：http://localhost:8000/docs
- 前端页面：http://localhost:8000/frontend/index.html

### 4. Embedding provider 切换

默认本地模型（离线、免费、512 维）：

```env
RAG_EMBEDDING_PROVIDER=local
RAG_LOCAL_EMBEDDING_MODEL=BAAI/bge-small-zh-v1.5
RAG_EMBEDDING_DIM=512
```

切远程 OpenAI 兼容接口时改 `.env` 对应块（如 1536 维）。**向量维度建表时固化，切换维度需重建 knowledge_chunk 表。**

## 核心链路速览

1. **对话**：`POST /api/v1/agent-sessions/{id}/chat`，请求体可带 `version_no`/`version_id` 按历史版本运行（响应带 `warnings` 提示快照中已删除的工具/知识库）。
2. **知识库**：建库 → 上传文档 → `/knowledge-bases/{id}/search` 验证 → 绑定到 Agent → 对话时自动检索注入。
3. **版本**：`POST /agents/{id}/versions` 发布；`POST .../versions/{n}/rollback` 软回滚（生成 "Rollback from vN" 新版本）。
4. **评测**：建测试集 → 批量导 case（answer/tool/rag 三类）→ `POST /evaluation/runs`（校验 version 归属 agent）→ worker 串行执行 → `GET /runs/{id}` 看 stats、`/cases` 看明细、`POST /runs/{id}/rerun-failed` 续跑、`GET /compare` 版本对比。
   - 评测 trace 独立：session_id 为 `eval_{run_id}_{case_id}`，metadata `source: "evaluation"`。

## Docker 部署

```bash
docker compose up -d db redis          # 基础设施
docker compose run --rm app alembic upgrade head
docker compose up -d app worker        # API + 评测 worker
```

## 测试

```bash
pytest tests/ -v
```

## 可观测性

- **Langfuse UI**：trace 树展示 `agent-run → retrieve_knowledge → knowledge_retriever`、
  `chat → ChatOpenAI`、工具 span；评测 trace 用 `eval_` 会话前缀与 `source=evaluation` 区分。
- **本地 metrics**：LLM/工具调用/向量检索延迟与状态落库，供管理端统计页消费。
- 关闭 trace：`LANGFUSE_TRACING_ENABLED=false`（业务无感知）。
