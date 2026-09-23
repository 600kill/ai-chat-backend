# Agent 管理平台 - API 接口清单

## 已完成接口列表

### 1. Agent 管理

| 接口 | 方法 | 路径 | 功能 |
|------|------|------|------|
| 查询 Agent 列表 | GET | `/api/v1/agents` | 支持搜索、状态筛选、分页 |
| 创建 Agent | POST | `/api/v1/agents` | 创建新 Agent |
| 获取 Agent 详情 | GET | `/api/v1/agents/{id}` | 获取 Agent 详细信息 |
| 更新 Agent | PUT | `/api/v1/agents/{id}` | 更新 Agent 信息 |
| 删除 Agent | DELETE | `/api/v1/agents/{id}` | 删除 Agent |
| 批量操作 | POST | `/api/v1/agents/batch` | 批量启用/停用/删除 |
| 获取工作流 | GET | `/api/v1/agents/{id}/workflow` | 获取 Mermaid 流程图数据 |

### 2. 工具库管理

| 接口 | 方法 | 路径 | 功能 |
|------|------|------|------|
| 查询工具列表 | GET | `/api/v1/agents/tools` | 支持搜索、状态筛选、分页 |
| 创建工具 | POST | `/api/v1/agents/tools` | 创建新工具 |
| 获取工具详情 | GET | `/api/v1/agents/tools/{id}` | 获取工具详细信息 |
| 更新工具 | PUT | `/api/v1/agents/tools/{id}` | 更新工具信息 |
| 删除工具 | DELETE | `/api/v1/agents/tools/{id}` | 删除工具 |
| 测试工具 | POST | `/api/v1/agents/tools/{id}/test` | 在线测试工具调用 |

### 3. Agent 测试会话

| 接口 | 方法 | 路径 | 功能 |
|------|------|------|------|
| 创建测试会话 | POST | `/api/v1/agent-sessions` | 创建 Agent 测试会话 |
| 查询会话列表 | GET | `/api/v1/agent-sessions` | 获取会话列表 |
| 获取会话详情 | GET | `/api/v1/agent-sessions/{id}` | 获取会话详细信息 |
| 发送消息 | POST | `/api/v1/agent-sessions/{id}/chat` | 与 Agent 对话 |
| 删除会话 | DELETE | `/api/v1/agent-sessions/{id}` | 删除会话 |

---

## 数据模型

### Agent 模型
```python
{
    "id": "UUID",
    "name": "Agent 名称",
    "description": "功能描述",
    "graph_config": "LangGraph 配置 (JSON)",
    "status": "active/inactive/draft",
    "created_by": "创建人 ID",
    "created_at": "创建时间"
}
```

### Tool 模型
```python
{
    "id": "UUID",
    "name": "工具名称",
    "description": "功能说明",
    "function_name": "Python 函数名",
    "input_schema": "入参定义 (JSON Schema)",
    "output_schema": "出参定义 (JSON Schema)",
    "example": "调用示例",
    "status": "enabled/disabled"
}
```

### Session 模型
```python
{
    "id": "会话 ID",
    "agent_id": "Agent ID",
    "user_id": "用户 ID",
    "name": "会话名称",
    "status": "active/ended",
    "created_at": "创建时间"
}
```

### ExecutionLog 模型
```python
{
    "id": "UUID",
    "session_id": "会话 ID",
    "node_name": "节点名称",
    "node_type": "节点类型",
    "input_data": "输入数据",
    "output_data": "输出数据",
    "tool_calls": "工具调用记录",
    "status": "success/failed/running",
    "error_message": "错误信息",
    "execution_time": "执行时间 (ms)"
}
```

---

## 核心服务

### AgentService
- Agent 增删改查
- Tool 增删改查
- Agent-Tool 关联管理
- 批量操作

### WorkflowService
- 解析 LangGraph 配置
- 生成 Mermaid 流程图
- 提取节点和边信息

### ToolInitializer
- 从 LangGraph tools 目录提取工具
- 自动生成 JSON Schema
- 注册到数据库

---

## 待完成功能

### Phase 3: 工作流可视化
- [ ] 前端 Mermaid 渲染组件
- [ ] 实时节点高亮
- [ ] WebSocket 推送执行轨迹

### Phase 4: 测试会话增强
- [ ] 集成 LangGraph 执行引擎
- [ ] 流式响应支持
- [ ] 执行轨迹记录
- [ ] 工具调用可视化

### Phase 5: 权限管理
- [ ] RBAC 权限控制
- [ ] 操作日志记录
- [ ] 敏感信息脱敏

---

## 使用示例

### 1. 初始化工具到数据库
```bash
python -m app.cli.init_tools
```

### 2. 创建 Agent
```bash
curl -X POST http://localhost:8000/api/v1/agents \
  -H "Content-Type: application/json" \
  -d '{
    "name": "订单助手",
    "description": "处理订单查询、创建",
    "status": "active",
    "tool_ids": []
  }'
```

### 3. 测试工具
```bash
curl -X POST http://localhost:8000/api/v1/agents/tools/{tool_id}/test \
  -H "Content-Type: application/json" \
  -d '{
    "chart_type": "line",
    "x": "1月,2月,3月",
    "y": "100,200,150",
    "title": "销售趋势"
  }'
```

### 4. 获取工作流
```bash
curl http://localhost:8000/api/v1/agents/{agent_id}/workflow
```

---

## 数据库迁移

### 执行迁移
```bash
alembic upgrade head
```

### 回滚迁移
```bash
alembic downgrade -1
```

---

## 测试

### 运行单元测试
```bash
pytest tests/test_agent_api.py -v
```

### 测试覆盖率
```bash
pytest tests/ --cov=app --cov-report=html
```

---

**文档版本**: v1.0  
**更新时间**: 2026-06-15  
**适用项目**: 企业内部 Agent 测试管理助手平台