"""评测 Runner：串行执行 EvaluationRun 的用例并判分。

职责边界（按评审反馈明确）：
- Runner 只负责「串行跑本次 run 的全部 case」（首次入队语义）；
  "pending/failed 重跑、completed 跳过"的续跑逻辑由 POST /runs/{id}/rerun-failed
  重置状态后以 only_pending=True 调用同一 job 函数，不混在首次语义里。
- Runner 必须基于版本快照跑：run.version_id → build_config(agent_id, version_id=...)
  → 用快照配置执行 run()，绝不读 Agent 当前配置。
- 评测 trace 与正常对话区分：session_id = eval_{run_id}_{case_id}，
  metadata 带 source: "evaluation"。
"""

import time
from datetime import datetime, UTC
from uuid import UUID

from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from app.core.langgraph.graph import LangGraphAgent
from app.core.logging import logger
from app.models.agent import Agent
from app.models.evaluation import EvaluationCase, EvaluationCaseResult, EvaluationRun
from app.schemas import Message
from app.services.agent_runtime_service import agent_runtime_service
from app.services.database import database_service
from app.services.evaluation.judges import build_judge_payload


def _is_retryable(exc: BaseException) -> bool:
    """429/超时/网关抖动可重试；其他错误不重试。"""
    msg = str(exc).lower()
    return any(k in msg for k in ("429", "rate", "timeout", "timed out", "temporarily", "connection"))


class EvaluationRunner:
    """评测执行器（RQ worker 进程内使用）。"""

    def __init__(self):
        self.session_maker = database_service.get_session_maker()
        self._graph_agent: LangGraphAgent | None = None
        self._loop = None  # 持久事件循环：图内 asyncio 原语（Lock 等）跨 case 复用，不能每 case 换 loop

    def _get_loop(self):
        import asyncio

        if self._loop is None or self._loop.is_closed():
            self._loop = asyncio.new_event_loop()
        return self._loop

    def _get_graph_agent(self) -> LangGraphAgent:
        # worker 进程内独立实例（与 API 进程隔离；评测串行无并发压力）
        if self._graph_agent is None:
            self._graph_agent = LangGraphAgent()
        return self._graph_agent

    # ------------------------------------------------------------------
    # job 入口
    # ------------------------------------------------------------------
    def execute_run(self, run_id: str, only_pending: bool = False) -> None:
        """执行一次评测 run（RQ job 函数，可被子进程调用）。

        Args:
            run_id: EvaluationRun ID
            only_pending: True 时只跑 pending 状态的 case（续跑语义，completed 跳过）；
                          False 时串行跑全部 case（首次执行语义）。
        """
        with self.session_maker() as session:
            run = session.get(EvaluationRun, UUID(run_id))
            if run is None:
                logger.error("eval_run_not_found", run_id=run_id)
                return
            agent = session.get(Agent, run.agent_id)
            if agent is None:
                self._fail_run(session, run, "Agent not found")
                return

            run.status = "running"
            run.started_at = run.started_at or datetime.now(UTC)
            run.error = None
            session.commit()

            cases = (
                session.query(EvaluationCase)
                .filter(EvaluationCase.testset_id == run.testset_id)
                .order_by(EvaluationCase.order)
                .all()
            )
            if not cases:
                self._fail_run(session, run, "测试集没有用例")
                return

            # Runner 必须基于版本快照：不读 Agent 当前配置
            config = self._get_loop().run_until_complete(
                agent_runtime_service.build_config(run.agent_id, version_id=str(run.version_id))
            )
            if config is None:
                self._fail_run(session, run, f"Agent {run.agent_id} 不存在，无法构建快照配置")
                return
            logger.info(
                "eval_run_started",
                run_id=run_id,
                version_id=str(run.version_id),
                agent_model=config.model_name,
                tools=config.tool_names,
                kb_count=len(config.kb_ids or []),
                only_pending=only_pending,
            )

            graph_agent = self._get_graph_agent()
            total = success = failed = 0
            for case in cases:
                result = (
                    session.query(EvaluationCaseResult)
                    .filter(
                        EvaluationCaseResult.run_id == run.id,
                        EvaluationCaseResult.case_id == case.id,
                    )
                    .first()
                )
                if result is None:
                    result = EvaluationCaseResult(run_id=run.id, case_id=case.id, status="pending")
                    session.add(result)
                    session.commit()
                elif only_pending and result.status == "completed":
                    continue  # 续跑语义：completed 跳过
                elif result.status == "completed":
                    # 首次语义下已完成的结果行（异常恢复场景）也跳过，幂等
                    continue

                total += 1
                try:
                    self._execute_case(graph_agent, config, run, case, result, session)
                    success += 1
                except Exception as e:
                    failed += 1
                    result.status = "failed"
                    result.error = str(e)[:500]
                    session.commit()
                    logger.warning("eval_case_failed", run_id=run_id, case_id=str(case.id), error=str(e))

            # 汇总
            self._summarize(session, run, total, success, failed)

    # ------------------------------------------------------------------
    # 单 case 执行 + 判分
    # ------------------------------------------------------------------
    @retry(
        retry=retry_if_exception(_is_retryable),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=4, min=4, max=30),
        reraise=True,
    )
    def _invoke_graph(self, graph_agent: LangGraphAgent, config, run, case):
        """单次图执行（仅图调用本身重试；判分与落库在外层）。复用 runner 持久 loop。"""
        return self._get_loop().run_until_complete(
            graph_agent.run(
                [Message(role="user", content=case.question)],
                session_id=f"eval_{run.id}_{case.id}",
                config=config,
                agent_id=str(run.agent_id),
                record_metrics=True,
                persist_memory=False,  # 评测对话不写入用户记忆
                extra_metadata={"source": "evaluation"},
            )
        )

    def _execute_case(self, graph_agent, config, run, case, result, session) -> None:
        result.status = "running"
        session.commit()

        run_result = self._invoke_graph(graph_agent, config, run, case)
        if run_result.error:
            raise RuntimeError(f"Agent 执行失败：{run_result.error}")

        assistant = [m for m in run_result.messages if m.get("role") == "assistant"]
        answer = assistant[-1]["content"] if assistant else ""

        result.agent_answer = answer
        result.actual_tool_calls = [
            {"name": t.get("name"), "args": t.get("args")} for t in (run_result.tool_calls or [])
        ]
        result.actual_document_ids = list(
            {d.get("document_id") for d in (run_result.retrieved_docs or []) if d.get("document_id")}
        )
        result.latency_ms = run_result.latency_ms
        result.total_tokens = None  # token 统计以 Langfuse/本地 metrics 为准

        scores, overall = build_judge_payload(
            case,
            result,
            rag_contexts=[d.get("content", "") for d in (run_result.retrieved_docs or [])[:3]],
        )
        result.scores = scores
        result.overall_score = overall
        result.status = "completed"
        result.judged_at = datetime.now(UTC)
        session.commit()
        logger.info(
            "eval_case_completed",
            run_id=str(run.id),
            case_id=str(case.id),
            overall=overall,
            tool=scores.get("tool"),
            latency_ms=result.latency_ms,
        )

    # ------------------------------------------------------------------
    # 汇总
    # ------------------------------------------------------------------
    def _summarize(self, session, run: EvaluationRun, total: int, success: int, failed: int) -> None:
        results = (
            session.query(EvaluationCaseResult)
            .filter(EvaluationCaseResult.run_id == run.id)
            .all()
        )
        completed = [r for r in results if r.status == "completed" and r.overall_score is not None]
        scores = [r.overall_score for r in completed]
        tool_scores = [r.scores.get("tool_score") for r in completed if r.scores and r.scores.get("tool_score") is not None]
        rag_recalls = [r.scores.get("rag_recall") for r in completed if r.scores and r.scores.get("rag_recall") is not None]
        latencies = sorted(r.latency_ms for r in completed if r.latency_ms is not None)

        def p95(values):
            if not values:
                return None
            idx = max(0, int(len(values) * 0.95) - 1)
            return values[idx]

        run.stats = {
            "overall_avg": round(sum(scores) / len(scores), 4) if scores else None,
            "overall_p95": round(sorted(scores)[max(0, int(len(scores) * 0.95) - 1)], 4) if scores else None,
            "tool_exact_rate": (
                round(sum(1 for r in completed if r.scores.get("tool") == "exact") / len(tool_scores), 4)
                if tool_scores else None
            ),
            "tool_score_avg": round(sum(tool_scores) / len(tool_scores), 4) if tool_scores else None,
            "rag_recall_avg": round(sum(rag_recalls) / len(rag_recalls), 4) if rag_recalls else None,
            "avg_latency_ms": round(sum(latencies) / len(latencies)) if latencies else None,
            "p95_latency_ms": p95(latencies),
            "failure_rate": round(failed / total, 4) if total else 0.0,
            "completed": len(completed),
        }
        run.total = len(results)
        run.success = len([r for r in results if r.status == "completed"])
        run.failed = len([r for r in results if r.status == "failed"])
        run.ended_at = datetime.now(UTC)
        # 全部 case 都失败才置 run failed；部分失败算 completed（failure_rate 体现）
        if run.failed > 0 and run.success == 0:
            run.status = "failed"
            run.error = f"全部 {run.failed} 个 case 执行失败"
        else:
            run.status = "completed"
        session.commit()
        logger.info("eval_run_finished", run_id=str(run.id), status=run.status, stats=run.stats)

    def _fail_run(self, session, run: EvaluationRun, error: str) -> None:
        run.status = "failed"
        run.error = error
        run.ended_at = datetime.now(UTC)
        session.commit()
        logger.error("eval_run_failed", run_id=str(run.id), error=error)


evaluation_runner = EvaluationRunner()


def execute_run_job(run_id: str, only_pending: bool = False) -> None:
    """RQ job 入口（模块级函数）。

    RQ 用 pickle 序列化 job 引用，实例方法无法序列化；worker 进程内通过
    evaluation_runner 单例惰性初始化（首个 job 时才建图实例）。
    """
    evaluation_runner.execute_run(run_id, only_pending)
