# 评测模块 API 说明

面向 Agent 的离线评测：组织测试用例 → 按**版本快照**异步执行 → 自动判分 → 版本对比。

- 路由前缀：`/api/v1/evaluation`
- 鉴权：JWT（`Authorization: Bearer <token>`）；测试集与 run 为 owner 私有，admin 可访问全部
- 异步执行：`POST /runs` 仅入队（Redis + RQ），结果轮询 `GET /runs/{id}`
- worker 启动：`python -m app.tasks.evaluation_worker`（Windows）或 `rq worker evaluations`（Linux）

## 1. 测试集

### POST /test-sets
创建测试集。

```json
{ "name": "人事问答回归集", "description": "answer/tool/rag 三类" }
```

### GET /test-sets
当前用户的测试集列表（admin 返回全部）。

### DELETE /test-sets/{testset_id}
删除测试集及其全部用例。

## 2. 测试用例

### POST /test-sets/{testset_id}/cases
批量导入用例（1-200 条）。

| 字段 | 类型 | 说明 |
|------|------|------|
| type | string | `answer` / `tool` / `rag` |
| question | string | 提问（必填） |
| expected_answer | string | 参考答案（answer/tool/rag 均可有，供 LLM Judge） |
| expected_tool | string | 期望工具名（function_name，如 `calculator`） |
| expected_arguments | object | 期望关键参数，按**子集**匹配（见判分口径） |
| expected_document_ids | string[] | RAG 期望命中文档 ID |
| order | int | 执行顺序 |

```json
{
  "cases": [
    { "type": "answer", "question": "入职满一年有几天年假？", "expected_answer": "5 个工作日", "order": 1 },
    { "type": "tool", "question": "算一下 (128+96)*13", "expected_tool": "calculator",
      "expected_arguments": { "expression": "(128 + 96) * 13" }, "order": 2 },
    { "type": "rag", "question": "差旅住宿标准？",
      "expected_document_ids": ["11e46270-44d6-4d83-b90c-94dacf12b0f2"], "order": 3 }
  ]
}
```

### GET /test-sets/{testset_id}/cases
用例列表（按 order 排序）。

## 3. 评测运行

### POST /runs
发起评测（入队即返回）。

```json
{ "agent_id": "<uuid>", "version_id": "<uuid>", "testset_id": "<uuid>" }
```

校验与语义：

- **version_id 必须属于 agent_id**，否则 400（禁止跨 Agent 跑评测）
- 执行严格基于版本快照（`build_config(version_id=...)`），不读 Agent 当前配置
- 测试集为空 → 400

返回：

```json
{ "code": 200, "data": { "run_id": "...", "job_id": "...", "status": "pending", "total": 3 } }
```

### GET /runs?testset_id={uuid}
运行列表（可按测试集过滤）。

### GET /runs/{run_id}
汇总报告：`status`（pending/running/completed/failed）、`total/success/failed`、`stats`。

stats 字段：

| 字段 | 含义 |
|------|------|
| overall_avg / overall_p95 | 综合分均值 / P95 |
| tool_exact_rate | 工具判分 exact 占比 |
| tool_score_avg | 工具分均值（exact=1 / partial=0.5 / miss=0） |
| rag_recall_avg | RAG 期望文档命中率均值 |
| avg_latency_ms / p95_latency_ms | 延迟均值 / P95 |
| failure_rate | 失败率（全部 case 失败时 run 置 failed） |

### GET /runs/{run_id}/cases?page=1&size=20
case 级明细：问题、Agent 回答、实际工具调用、`scores`、`overall_score`、延迟、错误。

### POST /runs/{run_id}/rerun-failed
续跑：重置 pending/failed 的 case 并入队，**completed 跳过**；返回 `{retry, skipped}`。
全部 completed 时调用返回 400。run 执行中（running）返回 400。

### GET /compare?run_a={uuid}&run_b={uuid}
两个 run 的指标并排对比；**强制同一 testset_id**，否则 400。典型用途：同一测试集、不同版本对比回归。

## 4. 判分口径

- **工具判分（三档）**
  - `exact`：工具名匹配且全部期望关键参数命中（值按字符串比较）
  - `partial`：工具名匹配但仅部分关键参数命中
  - `miss`：未调用期望工具，或调用了错误工具
  - 未声明 expected_arguments 时，工具名匹配即 exact
- **RAG 判分**：`rag_recall = 命中的期望文档数 / 期望文档总数`
- **回答判分（LLM-as-Judge）**：`factuality` / `instruction` / `completeness` 各 0-10 分 + rationale；
  Judge 模型取自 settings（`JUDGE_MODEL/JUDGE_BASE_URL/JUDGE_API_KEY`，走 LLM 网关）。
  Judge 调用失败时三维分为 null 并记录原因，不阻断 run
- **综合分 overall**：answer 型=回答归一化均分；tool/rag 型=规则分 50% + 回答分 50%

## 5. Trace 隔离

评测执行与正常对话在 Langfuse 中可区分：

- session_id：`eval_{run_id}_{case_id}`
- metadata：`source: "evaluation"`
- 评测对话不写入 mem0 长时记忆（`persist_memory=False`）
- 429/超时自动重试 3 次（指数退避 4-30s）
