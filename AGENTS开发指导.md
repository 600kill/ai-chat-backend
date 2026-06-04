# AI Agent Development Guide 智能体开发规范

This document provides essential guidelines for AI agents working on this LangGraph FastAPI Agent project.

## Quick Commands

```bash
make install          # 安装项目所有依赖（底层用 uv 工具同步）【✅ 精简版可用】
make dev              # 启动带热重载的开发服务器（端口 8000）【✅ 核心必用！】
make lint             # 代码规范检查（用 ruff 工具扫描代码错误）
make format           # 自动格式化代码（用 ruff 统一代码风格）
make eval             # 运行大模型效果评估（交互式模式）【❌ 已删除，无用】
make eval-quick       # 快速运行大模型效果评估（默认配置）【❌ 已删除，无用】
make docker-run       # Docker 部署：启动API+数据库（开发环境）【❌ 精简版不用】
make docker-compose-up ENV=development  # Docker全栈部署：启动API+监控+可视化面板【❌ 已删除，无用】
```

## Project Structure项目结构

```
app/
  api/v1/          # 路由处理器（auth.py、chatbot.py、api.py）
  core/
    config.py      # Pydantic Settings 配置
    database.py    # 异步数据库初始化
    langgraph/     # LangGraph 智能体工作流 + 工具
    logging.py     # structlog 日志配置
    llm.py         # 带重试机制的大模型服务
    limiter.py     # 接口限流（slowapi）
    metrics.py     # Prometheus 监控指标*********
    middleware.py  # ASGI 中间件
    prompts/       # 系统提示词
  models/          # SQLModel ORM 数据模型
  schemas/         # Pydantic 请求/响应格式 + 工作流状态定义
  services/        # 业务逻辑服务
  utils/           # 公共工具函数
evals/             # 大模型效果评估框架（基于 Langfuse）
scripts/           # 环境初始化、Docker 构建脚本
```

# 项目概述
这是一个可直接用于生产环境的AI智能体应用，基于以下技术构建：
- LangGraph：用于有状态、多步骤的AI智能体工作流
- FastAPI：用于高性能异步REST API接口
- Langfuse：用于LLM可观测性与调用追踪
- PostgreSQL + pgvector：用于长时记忆存储（mem0ai）
- JWT认证：带会话管理
- Prometheus + Grafana：用于系统监控

# 快速参考：核心规则
## 导入规则
所有导入**必须**放在文件顶部 —— 禁止在函数或类内部添加导入

## 日志规则
- 所有日志使用**structlog**
- 日志事件名必须使用**小写+下划线**格式（例如：`user_login_successful`）
- structlog事件中**禁止使用f-string** —— 变量以关键字参数形式传递
- 使用`logger.exception()`而非`logger.error()`以保留异常堆栈信息
- 示例：`logger.info("chat_request_received", session_id=session.id, message_count=len(messages))`

## 重试规则
- 重试逻辑必须使用**tenacity**库
- 配置**指数退避**策略
- 示例：`@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))`

## 输出规则
- 必须启用**rich**库用于格式化控制台输出
- 使用rich实现进度条、表格、面板与格式化文本

## 缓存规则
- 仅缓存**成功响应**，绝不缓存错误
- 根据数据变化频率设置合理的缓存过期时间（TTL）

## FastAPI规则
- 所有路由必须添加**限流装饰器**
- 服务、数据库连接、认证使用**依赖注入**
- 所有数据库操作必须是**异步**的

# 代码风格规范
## Python/FastAPI
- 异步操作使用`async def`
- 所有函数签名必须添加**类型注解**
- 优先使用Pydantic模型，而非原生字典
- 使用函数式、声明式编程；仅服务和智能体允许使用类
- 文件命名：小写+下划线（例如：`user_routes.py`）
- 使用**RORO模式**（接收对象，返回对象）

## 错误处理
- 在函数**开头**处理错误
- 错误条件使用**提前返回**
- 正常逻辑放在函数最后
- 使用**守卫条件**校验前置状态
- 预期错误使用`HTTPException`并返回合适的状态码

# LangGraph & LangChain 规范
## 工作流结构
- 使用`StateGraph`构建AI智能体工作流
- 使用Pydantic模型定义清晰的状态结构（见`app/schemas/graph.py`）
- 生产环境工作流使用`CompiledStateGraph`
- 实现`AsyncPostgresSaver`用于检查点与状态持久化
- 使用`Command`控制节点间的工作流流转

## 追踪
- 使用Langfuse提供的LangChain CallbackHandler追踪所有LLM调用
- 所有LLM操作**必须**开启Langfuse追踪

## 记忆（mem0ai）
- 使用`AsyncMemory`进行语义记忆存储
- 按`user_id`存储记忆，实现个性化体验
- 使用异步方法：`add()`、`get()`、`search()`、`delete()`

# 认证与安全
- 使用JWT令牌进行认证
- 实现基于会话的用户管理（见`app/api/v1/auth.py`）
- 受保护接口使用`get_current_session`依赖
- 敏感数据存储在环境变量中
- 所有用户输入使用Pydantic模型校验

# 数据库操作
- 使用SQLModel作为ORM模型（整合SQLAlchemy + Pydantic）
- 模型定义在`app/models/`目录
- 使用`asyncpg`执行异步数据库操作
- 智能体检查点持久化使用LangGraph的`AsyncPostgresSaver`

# 性能指南
- 最小化阻塞I/O操作
- 所有数据库与外部API调用使用异步
- 对高频访问数据实现缓存
- 使用数据库连接池
- 通过流式响应优化LLM调用

# 可观测性
- 所有智能体操作集成Langfuse进行LLM追踪
- 导出Prometheus指标用于API性能监控
- 使用带上下文绑定的结构化日志（`request_id`、`session_id`、`user_id`）
- 监控LLM推理耗时、Token用量与成本

# 测试与评估
- 为LLM输出实现基于指标的评估（见`evals/`目录）
- 在`evals/metrics/prompts/`中以markdown文件创建自定义评估指标
- 使用Langfuse追踪作为评估数据源
- 生成包含成功率的JSON报告

# 配置管理
- 使用环境专属配置文件（`.env.development`、`.env.staging`、`.env.production`）
- 使用Pydantic Settings实现类型安全配置（见`app/core/config.py`）
- **绝不硬编码**密钥或API密钥

# 核心依赖
- FastAPI：Web框架
- LangGraph：智能体工作流编排
- LangChain：LLM抽象与工具
- Langfuse：LLM可观测性与追踪
- Pydantic v2：数据校验与配置管理
- structlog：结构化日志
- mem0ai：长时记忆管理
- PostgreSQL + pgvector：数据库与向量存储
- SQLModel：数据库ORM
- tenacity：重试逻辑
- rich：终端格式化
- slowapi：接口限流
- prometheus-client：指标采集

# 项目十诫
1. 所有路由必须添加限流装饰器
2. 所有LLM操作必须开启Langfuse追踪
3. 所有异步操作必须有完善的错误处理
4. 所有日志必须遵循结构化格式，事件名使用小写+下划线
5. 所有重试必须使用tenacity库
6. 所有控制台输出应使用rich格式化
7. 所有缓存仅存储成功响应
8. 所有导入必须放在文件顶部
9. 所有数据库操作必须是异步的
10. 所有接口必须有完善的类型注解与Pydantic模型

# 需避免的常见错误
❌ 在structlog事件中使用f-string
❌ 在函数内部添加导入
❌ 路由忘记添加限流装饰器
❌ LLM调用缺少Langfuse追踪
❌ 缓存错误响应
❌ 异常处理使用`logger.error()`而非`logger.exception()`
❌ 未使用异步执行阻塞I/O操作
❌ 硬编码密钥或API密钥
❌ 函数签名缺少类型注解

# 修改代码时
修改代码前：
1. 先阅读现有实现
2. 检查代码库中相关的实现模式
3. 确保与现有代码风格保持一致
4. 添加符合结构化格式的日志
5. 包含带提前返回的错误处理
6. 添加类型注解与Pydantic模型
7. 确认LLM调用已开启Langfuse追踪

# 参考资料
- LangGraph文档：https://langchain-ai.github.io/langgraph/
- LangChain文档：https://python.langchain.com/docs/
- FastAPI文档：https://fastapi.tiangolo.com/
- Langfuse文档：https://langfuse.com/docs

---

## 翻译说明
1. **完全保留原文含义、结构、专业术语**
2. **严格对应原文段落、标题、列表、示例**
3. **技术术语统一（如LLM、JWT、async、缓存、追踪等不随意修改）**
4. **适合你学习、背诵、写文档、面试使用**
