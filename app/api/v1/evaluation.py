"""评测模块 API：测试集 / 用例 / 运行 / 对比。

权限：测试集与 run 为 owner 私有资源（admin 可访问全部）。
"""

import asyncio
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from app.models.agent import Agent
from app.models.evaluation import (
    EvaluationCase,
    EvaluationCaseResult,
    EvaluationRun,
    EvaluationTestSet,
)
from app.models.version import AgentVersion
from app.services.database import database_service
from app.tasks.evaluation_worker import enqueue_evaluation_run
from app.utils.permissions import (
    NotFoundError,
    PermissionError,
    ValidationError,
    get_current_user,
)

router = APIRouter(prefix="/evaluation", tags=["evaluation"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
class TestSetCreateRequest(BaseModel):
    name: str = Field(max_length=100)
    description: Optional[str] = None


class CaseItem(BaseModel):
    type: str = Field(default="answer", pattern="^(answer|tool|rag)$")
    question: str
    expected_answer: Optional[str] = None
    expected_tool: Optional[str] = None
    expected_arguments: Optional[dict] = None
    expected_document_ids: Optional[List[str]] = None
    order: int = Field(default=0)


class CaseBatchCreateRequest(BaseModel):
    cases: List[CaseItem] = Field(min_length=1, max_length=200)


class RunCreateRequest(BaseModel):
    agent_id: UUID
    version_id: UUID
    testset_id: UUID


def _session():
    return database_service.get_session_maker()()


def _to_dict(obj, exclude_snapshot: bool = False) -> dict:
    data = {}
    for k, v in obj.__dict__.items():
        if k.startswith("_"):
            continue
        if isinstance(v, UUID):
            v = str(v)
        data[k] = v
    return data


def _require_testset(session, testset_id: UUID, user) -> EvaluationTestSet:
    ts = session.get(EvaluationTestSet, testset_id)
    if ts is None:
        raise NotFoundError("测试集不存在")
    if ts.owner_id != user.id and user.role != "admin":
        raise PermissionError("无权访问该测试集")
    return ts


def _require_run(session, run_id: UUID, user) -> EvaluationRun:
    run = session.get(EvaluationRun, run_id)
    if run is None:
        raise NotFoundError("评测 run 不存在")
    if run.created_by != user.id and user.role != "admin":
        raise PermissionError("无权访问该评测 run")
    return run


# ---------------------------------------------------------------------------
# 测试集
# ---------------------------------------------------------------------------
@router.post("/test-sets")
async def create_test_set(request: TestSetCreateRequest, user=Depends(get_current_user)):
    with _session() as session:
        ts = EvaluationTestSet(name=request.name, description=request.description, owner_id=user.id)
        session.add(ts)
        session.commit()
        session.refresh(ts)
        return {"code": 200, "message": "success", "data": _to_dict(ts)}


@router.get("/test-sets")
async def list_test_sets(user=Depends(get_current_user)):
    with _session() as session:
        query = session.query(EvaluationTestSet)
        if user.role != "admin":
            query = query.filter(EvaluationTestSet.owner_id == user.id)
        items = [ _to_dict(ts) for ts in query.order_by(EvaluationTestSet.created_at.desc()).all() ]
        return {"code": 200, "message": "success", "data": {"items": items, "total": len(items)}}


@router.delete("/test-sets/{testset_id}")
async def delete_test_set(testset_id: UUID, user=Depends(get_current_user)):
    with _session() as session:
        ts = _require_testset(session, testset_id, user)
        session.query(EvaluationCase).filter(EvaluationCase.testset_id == ts.id).delete()
        session.query(EvaluationTestSet).filter(EvaluationTestSet.id == ts.id).delete()
        session.commit()
        return {"code": 200, "message": "success", "data": {"id": str(ts.id)}}


@router.post("/test-sets/{testset_id}/cases")
async def batch_create_cases(testset_id: UUID, request: CaseBatchCreateRequest, user=Depends(get_current_user)):
    with _session() as session:
        ts = _require_testset(session, testset_id, user)
        created = []
        for item in request.cases:
            case = EvaluationCase(
                testset_id=ts.id,
                type=item.type,
                question=item.question,
                expected_answer=item.expected_answer,
                expected_tool=item.expected_tool,
                expected_arguments=item.expected_arguments,
                expected_document_ids=item.expected_document_ids,
                order=item.order,
            )
            session.add(case)
            created.append(case)
        session.commit()
        ts.case_count = session.query(EvaluationCase).filter(EvaluationCase.testset_id == ts.id).count()
        session.commit()
        return {"code": 200, "message": "success", "data": {"created": len(created)}}


@router.get("/test-sets/{testset_id}/cases")
async def list_cases(testset_id: UUID, user=Depends(get_current_user)):
    with _session() as session:
        _require_testset(session, testset_id, user)
        cases = (
            session.query(EvaluationCase)
            .filter(EvaluationCase.testset_id == testset_id)
            .order_by(EvaluationCase.order)
            .all()
        )
        return {"code": 200, "message": "success", "data": {"items": [_to_dict(c) for c in cases], "total": len(cases)}}


# ---------------------------------------------------------------------------
# 评测 run
# ---------------------------------------------------------------------------
@router.post("/runs")
async def create_run(request: RunCreateRequest, user=Depends(get_current_user)):
    """发起评测：agent_id + version_id + testset_id → 校验归属 → 入队。

    校验（跨 agent 拒绝）：version_id 必须属于传入的 agent_id。
    """
    with _session() as session:
        ts = _require_testset(session, request.testset_id, user)
        agent = session.get(Agent, request.agent_id)
        if agent is None:
            raise NotFoundError("Agent 不存在")
        if agent.owner_id != user.id and user.role != "admin":
            raise PermissionError("无权对该 Agent 发起评测")
        version = session.get(AgentVersion, request.version_id)
        if version is None or version.agent_id != request.agent_id:
            raise ValidationError("version_id 不属于该 agent_id（禁止跨 Agent 跑评测）")
        case_count = session.query(EvaluationCase).filter(EvaluationCase.testset_id == ts.id).count()
        if case_count == 0:
            raise ValidationError("测试集没有用例")

        from app.core.config import settings as app_settings

        run = EvaluationRun(
            testset_id=ts.id,
            agent_id=request.agent_id,
            version_id=request.version_id,
            judge_model=app_settings.JUDGE_MODEL,
            status="pending",
            total=case_count,
            created_by=user.id,
        )
        session.add(run)
        session.commit()
        session.refresh(run)

        cases = session.query(EvaluationCase).filter(EvaluationCase.testset_id == ts.id).all()
        for case in cases:
            session.add(EvaluationCaseResult(run_id=run.id, case_id=case.id, status="pending"))
        session.commit()

        job_id = enqueue_evaluation_run(str(run.id), only_pending=False)
        return {
            "code": 200,
            "message": "success",
            "data": {"run_id": str(run.id), "job_id": job_id, "status": "pending", "total": case_count},
        }


@router.get("/runs")
async def list_runs(testset_id: Optional[UUID] = Query(default=None), user=Depends(get_current_user)):
    with _session() as session:
        query = session.query(EvaluationRun)
        if testset_id:
            query = query.filter(EvaluationRun.testset_id == testset_id)
        if user.role != "admin":
            query = query.filter(EvaluationRun.created_by == user.id)
        runs = query.order_by(EvaluationRun.created_at.desc()).all()
        return {"code": 200, "message": "success", "data": {"items": [_to_dict(r) for r in runs], "total": len(runs)}}


@router.get("/runs/{run_id}")
async def get_run(run_id: UUID, user=Depends(get_current_user)):
    """run 汇总报告（状态 + stats）。"""
    with _session() as session:
        run = _require_run(session, run_id, user)
        return {"code": 200, "message": "success", "data": _to_dict(run)}


@router.get("/runs/{run_id}/cases")
async def get_run_cases(
    run_id: UUID,
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    user=Depends(get_current_user),
):
    """case 级详情（含判分 scores）。"""
    with _session() as session:
        run = _require_run(session, run_id, user)
        query = (
            session.query(EvaluationCaseResult, EvaluationCase)
            .join(EvaluationCase, EvaluationCase.id == EvaluationCaseResult.case_id)
            .filter(EvaluationCaseResult.run_id == run.id)
            .order_by(EvaluationCase.order)
        )
        total = query.count()
        rows = query.offset((page - 1) * size).limit(size).all()
        items = []
        for result, case in rows:
            items.append(
                {
                    "case_id": str(case.id),
                    "type": case.type,
                    "question": case.question,
                    "expected_answer": case.expected_answer,
                    "status": result.status,
                    "agent_answer": result.agent_answer,
                    "actual_tool_calls": result.actual_tool_calls,
                    "scores": result.scores,
                    "overall_score": result.overall_score,
                    "latency_ms": result.latency_ms,
                    "error": result.error,
                }
            )
        return {
            "code": 200,
            "message": "success",
            "data": {"items": items, "total": total, "page": page, "size": size},
        }


@router.post("/runs/{run_id}/rerun-failed")
async def rerun_failed(run_id: UUID, user=Depends(get_current_user)):
    """续跑：重置 pending/failed 的 case 后单独入队（completed 跳过）。"""
    with _session() as session:
        run = _require_run(session, run_id, user)
        if run.status == "running":
            raise BadRequestError("run 正在执行中")
        rows = (
            session.query(EvaluationCaseResult)
            .filter(EvaluationCaseResult.run_id == run.id)
            .all()
        )
        to_retry = 0
        for r in rows:
            if r.status in ("pending", "failed"):
                r.status = "pending"
                r.error = None
                to_retry += 1
        if to_retry == 0:
            raise ValidationError("没有需要重跑的 case（全部 completed）")
        run.status = "running"
        run.error = None
        session.commit()
        job_id = enqueue_evaluation_run(str(run.id), only_pending=True)
        return {
            "code": 200,
            "message": "success",
            "data": {"run_id": str(run.id), "job_id": job_id, "retry": to_retry, "skipped": len(rows) - to_retry},
        }


@router.get("/compare")
async def compare_runs(run_a: UUID, run_b: UUID, user=Depends(get_current_user)):
    """两 run 指标并排对比（强制同一测试集）。"""
    with _session() as session:
        ra = _require_run(session, run_a, user)
        rb = _require_run(session, run_b, user)
        if ra.testset_id != rb.testset_id:
            raise BadRequestError("两个 run 必须基于同一测试集")
        return {
            "code": 200,
            "message": "success",
            "data": {
                "testset_id": str(ra.testset_id),
                "run_a": _to_dict(ra),
                "run_b": _to_dict(rb),
            },
        }
