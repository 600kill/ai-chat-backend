# AI Chat Backend

基于 FastAPI + LangGraph 构建的企业级 AI 聊天机器人后端服务。

## 项目简介

轻量级 AI 对话后端项目，集成 LangGraph 智能体工作流、长时记忆、多模型自动降级、JWT 认证、接口限流等生产级特性，支持流式响应和图表生成工具调用。

## 技术栈

| 类别 | 技术 |
|------|------|
| Web 框架 | FastAPI 0.115.0 |
| AI 工作流 | LangGraph 0.2.0 |
| 数据库 | PostgreSQL 16 + pgvector |
| ORM | SQLModel 2.0.0 |
| 缓存 | Redis 5.0.0（支持降级到内存） |
| 认证 | JWT (python-jose) |
| 限流 | slowapi |
| 数据迁移 | Alembic 1.13.0 |
| 容器化 | Docker + Docker Compose |

## 项目目录结构

```
zhuanyexiangmu/
├── app/
│   ├── api/v1/              # REST API 接口层
│   │   ├── auth.py          # 用户认证（注册/登录/会话管理）
│   │   ├── chatbot.py       # 聊天接口（普通/流式/图片获取）
│   │   └── api.py           # 路由聚合
│   ├── core/                # 核心配置与组件
│   │   ├── config.py        # 环境配置管理（多环境支持）
│   │   ├── langgraph/       # LangGraph 智能体核心
│   │   │   ├── graph.py     # 工作流定义与状态管理
│   │   │   └── tools/       # 工具调用（图表生成/搜索）
│   │   ├── prompts/         # 提示词模板
│   │   ├── cache.py         # 缓存服务（Redis/内存降级）
│   │   ├── limiter.py       # 接口限流配置
│   │   └── logging.py       # 结构化日志
│   ├── models/              # 数据库模型
│   │   ├── user.py          # 用户模型
│   │   ├── session.py       # 会话模型
│   │   └── base.py          # 基础模型
│   ├── schemas/             # Pydantic 数据校验
│   │   ├── auth.py          # 认证相关 Schema
│   │   ├── chat.py          # 聊天相关 Schema
│   │   └── base.py          # 基础响应模型
│   ├── services/            # 业务服务层
│   │   ├── database.py      # 数据库操作服务
│   │   ├── memory.py        # 长时记忆服务
│   │   ├── session_naming.py # 会话自动命名
│   │   └── llm/             # LLM 服务（重试+降级）
│   └── utils/               # 工具函数
│       ├── auth.py          # JWT 令牌工具
│       └── sanitization.py  # 输入清洗
├── alembic/                 # 数据库迁移
│   └── versions/            # 迁移脚本
├── tests/                   # 单元测试
│   └── test_api.py          # API 接口测试
├── frontend/                # 前端页面
│   └── index.html           # 聊天界面
├── .env                     # 环境变量配置
├── .gitignore               # Git 忽略规则
├── Dockerfile               # 容器镜像构建
├── docker-compose.yml       # 容器编排配置
├── requirements.txt         # Python 依赖
├── alembic.ini              # Alembic 配置
└── main.py                  # 项目入口
```

## 本地开发运行教程

### 1. 环境准备

```bash
# 创建虚拟环境
python -m venv .venv

# 激活虚拟环境
# Windows:
.venv\Scripts\Activate.ps1
# Linux/Mac:
source .venv/bin/activate

# 安装依赖
pip install -r requirements.txt
```

### 2. 数据库配置

确保 PostgreSQL 已启动，修改 `.env` 文件：

```env
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=app_db
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres

# AI 模型配置
DASHSCOPE_API_KEY=your-api-key
DEFAULT_LLM_MODEL=qwen-turbo

# JWT 密钥
JWT_SECRET_KEY=your-secret-key
```

### 3. 数据库迁移

```bash
# 初始化迁移
alembic upgrade head
```

### 4. 启动服务

```bash
# 开发模式（热重载）
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# 生产模式
uvicorn main:app --host 0.0.0.0 --port 8000
```

### 5. 访问服务

- API 文档：http://localhost:8000/docs
- 前端界面：http://localhost:8000/frontend/index.html

## Docker 部署教程

### 1. 一键启动

```bash
# 启动所有服务（数据库 + 应用）
docker-compose up -d

# 查看日志
docker-compose logs -f app
```

### 2. 数据库迁移

```bash
# 进入应用容器
docker-compose exec app bash

# 执行迁移
alembic upgrade head

# 退出容器
exit
```

### 3. 停止服务

```bash
# 停止所有服务
docker-compose down

# 停止并删除数据卷（谨慎使用）
docker-compose down -v
```

### 4. 环境变量配置

确保 `.env` 文件配置正确，docker-compose 会自动读取：

```env
POSTGRES_HOST=db
POSTGRES_PORT=5432
POSTGRES_DB=app_db
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres

DASHSCOPE_API_KEY=your-api-key
```

## 单元测试

### 1. 运行测试

```bash
# 运行所有测试
pytest tests/ -v

# 运行测试并生成覆盖率报告
pytest tests/ --cov=app --cov-report=html
```

### 2. 测试覆盖范围

当前测试覆盖以下核心接口：

| 测试函数 | 测试目标 |
|----------|----------|
| `test_root_endpoint` | 验证根接口返回项目信息 |
| `test_health_endpoint` | 验证健康检查接口 |
| `test_user_register_and_login` | 验证用户注册、登录、创建会话完整流程 |

## 项目亮点 / 优化点

### 1. 工程化架构

- **分层清晰**：API 层 / 服务层 / 模型层分离，职责明确
- **配置管理**：支持多环境配置（development/staging/production），环境变量统一管理
- **容器化部署**：Docker + Docker Compose 一键部署，便于 CI/CD 集成

### 2. 稳定性保障

- **多模型降级**：LLM 服务支持自动重试和模型降级，提升可用性
- **缓存降级**：Redis 不可用时自动降级到内存缓存，确保服务不中断
- **接口限流**：基于 slowapi 实现接口级限流，防止恶意请求

### 3. 安全性设计

- **JWT 认证**：用户认证与会话管理分离，令牌自动过期
- **输入清洗**：所有用户输入经过 sanitization 处理，防止注入攻击
- **密码加密**：使用 bcrypt 加密存储，符合安全最佳实践

### 4. 可观测性

- **结构化日志**：基于 structlog 实现结构化日志，支持请求追踪
- **健康检查**：提供 `/health` 接口，便于监控系统状态
- **错误处理**：全局异常处理，返回友好错误信息

## 项目总结

本项目是一个生产级 AI 聊天后端服务，采用 FastAPI + LangGraph 技术栈，具备完整的用户认证、会话管理、长时记忆、工具调用等核心功能。项目遵循工程化规范，支持 Docker 容器化部署，具备良好的可扩展性和稳定性，适合作为实习项目展示或实际业务场景落地。