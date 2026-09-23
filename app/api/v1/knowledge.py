"""知识库 API：知识库/文档管理 + 检索测试 + Agent 绑定。

权限模型（与 Agent 一致）：
- 读（详情/文档列表/检索）：owner 或 admin，公开知识库所有人可读
- 写（改/删/上传/绑定）：仅 owner 或 admin
"""

import asyncio
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile

from app.core.config import settings
from app.models.rag import KnowledgeBase
from app.models.user import User
from app.schemas.knowledge import (
    AgentKbBindRequest,
    KnowledgeBaseCreate,
    KnowledgeBaseUpdate,
    KnowledgeSearchRequest,
)
from app.services.rag_service import ALLOWED_EXTENSIONS, rag_service
from app.utils.permissions import NotFoundError, PermissionError, get_current_user

router = APIRouter(tags=["knowledge"])


def _get_owned_or_404(kb_id: UUID) -> KnowledgeBase:
    kb = rag_service.get_kb(kb_id)
    if kb is None:
        raise NotFoundError("Knowledge base not found")
    return kb


def _require_read(kb: KnowledgeBase, user: User) -> None:
    if kb.is_public or user.role == "admin" or kb.owner_id == user.id:
        return
    raise PermissionError("Not authorized to access this knowledge base")


def _require_write(kb: KnowledgeBase, user: User) -> None:
    if user.role == "admin" or kb.owner_id == user.id:
        return
    raise PermissionError("Only owner or admin can modify this knowledge base")


# ==================== 知识库 CRUD ====================

@router.post("/knowledge-bases")
async def create_knowledge_base(
    request: KnowledgeBaseCreate,
    user: User = Depends(get_current_user),
):
    """创建知识库。"""
    overlap = request.chunk_overlap
    if request.chunk_size is not None and overlap is not None and overlap >= request.chunk_size:
        raise HTTPException(status_code=400, detail="chunk_overlap 必须小于 chunk_size")
    kb = await asyncio.to_thread(
        rag_service.create_kb,
        owner_id=user.id,
        name=request.name,
        description=request.description,
        is_public=request.is_public,
        chunk_size=request.chunk_size,
        chunk_overlap=request.chunk_overlap,
        top_k=request.top_k,
    )
    return {"code": 200, "message": "创建成功", "data": {"id": kb.id, "name": kb.name}}


@router.get("/knowledge-bases")
async def list_knowledge_bases(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    search: str | None = Query(None),
    mine_only: bool = Query(False, description="仅返回我创建的"),
    user: User = Depends(get_current_user),
):
    """列出知识库（默认含公开库；mine_only=true 仅本人）。"""
    result = await asyncio.to_thread(
        rag_service.list_kbs,
        user.id,
        not mine_only,
        page,
        size,
        search,
    )
    return {"code": 200, "message": "success", "data": result}


@router.get("/knowledge-bases/{kb_id}")
async def get_knowledge_base(
    kb_id: UUID,
    user: User = Depends(get_current_user),
):
    """知识库详情。"""
    kb = _get_owned_or_404(kb_id)
    _require_read(kb, user)
    docs = await asyncio.to_thread(rag_service.list_documents, kb_id)
    return {
        "code": 200,
        "message": "success",
        "data": {
            "id": kb.id,
            "name": kb.name,
            "description": kb.description,
            "is_public": kb.is_public,
            "owner_id": kb.owner_id,
            "chunk_size": kb.chunk_size or settings.RAG_CHUNK_SIZE,
            "chunk_overlap": kb.chunk_overlap or settings.RAG_CHUNK_OVERLAP,
            "top_k": kb.top_k or settings.RAG_TOP_K,
            "documents": docs,
            "created_at": kb.created_at,
        },
    }


@router.put("/knowledge-bases/{kb_id}")
async def update_knowledge_base(
    kb_id: UUID,
    request: KnowledgeBaseUpdate,
    user: User = Depends(get_current_user),
):
    """更新知识库元数据（不影响已索引分片）。"""
    kb = _get_owned_or_404(kb_id)
    _require_write(kb, user)
    overlap = request.chunk_overlap if request.chunk_overlap is not None else kb.chunk_overlap
    chunk_size = request.chunk_size if request.chunk_size is not None else kb.chunk_size
    if chunk_size and overlap is not None and overlap >= chunk_size:
        raise HTTPException(status_code=400, detail="chunk_overlap 必须小于 chunk_size")
    for field in ("name", "description", "is_public", "chunk_size", "chunk_overlap", "top_k"):
        value = getattr(request, field)
        if value is not None:
            setattr(kb, field, value)
    from app.services.database import database_service

    with database_service.get_session_maker()() as session:
        session.add(kb)
        session.commit()
    return {"code": 200, "message": "更新成功", "data": {"id": kb.id}}


@router.delete("/knowledge-bases/{kb_id}")
async def delete_knowledge_base(
    kb_id: UUID,
    user: User = Depends(get_current_user),
):
    """删除知识库（含全部文档与分片）。"""
    kb = _get_owned_or_404(kb_id)
    _require_write(kb, user)
    await asyncio.to_thread(rag_service.delete_kb, kb_id)
    return {"code": 200, "message": "删除成功", "data": None}


# ==================== 文档 ====================

@router.post("/knowledge-bases/{kb_id}/documents")
async def upload_document(
    kb_id: UUID,
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
):
    """上传文档（txt/md/pdf），上传后立即切片索引。"""
    kb = _get_owned_or_404(kb_id)
    _require_write(kb, user)

    filename = file.filename or "untitled"
    ext = f".{filename.rsplit('.', 1)[-1].lower()}" if "." in filename else ""
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件类型 {ext}；仅支持 {sorted(ALLOWED_EXTENSIONS)}",
        )

    raw = await file.read()
    max_bytes = settings.RAG_MAX_UPLOAD_MB * 1024 * 1024
    if len(raw) > max_bytes:
        raise HTTPException(
            status_code=400,
            detail=f"文件过大：{len(raw)} bytes，上限 {settings.RAG_MAX_UPLOAD_MB}MB",
        )

    try:
        doc = await asyncio.to_thread(rag_service.add_document, kb_id, filename, raw)
    except ValueError as exc:
        # 去重冲突 / 无文本 / 解析失败
        status_code = 409 if "Duplicate" in str(exc) else 400
        raise HTTPException(status_code=status_code, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"文档索引失败：{exc}")

    return {
        "code": 200,
        "message": "文档索引完成",
        "data": {
            "id": doc.id,
            "filename": doc.filename,
            "status": doc.status,
            "chunk_count": doc.chunk_count,
            "char_count": doc.char_count,
        },
    }


@router.get("/knowledge-bases/{kb_id}/documents")
async def list_documents(
    kb_id: UUID,
    user: User = Depends(get_current_user),
):
    """列出知识库下的文档。"""
    kb = _get_owned_or_404(kb_id)
    _require_read(kb, user)
    docs = await asyncio.to_thread(rag_service.list_documents, kb_id)
    return {"code": 200, "message": "success", "data": docs}


@router.delete("/knowledge-bases/{kb_id}/documents/{doc_id}")
async def delete_document(
    kb_id: UUID,
    doc_id: UUID,
    user: User = Depends(get_current_user),
):
    """删除文档及其分片。"""
    kb = _get_owned_or_404(kb_id)
    _require_write(kb, user)
    ok = await asyncio.to_thread(rag_service.delete_document, doc_id)
    if not ok:
        raise NotFoundError("Document not found")
    return {"code": 200, "message": "删除成功", "data": None}


# ==================== 检索测试 ====================

@router.post("/knowledge-bases/{kb_id}/search")
async def search_knowledge_base(
    kb_id: UUID,
    request: KnowledgeSearchRequest,
    user: User = Depends(get_current_user),
):
    """在单个知识库内做语义检索（调试/预览用）。"""
    kb = _get_owned_or_404(kb_id)
    _require_read(kb, user)
    results = await asyncio.to_thread(
        rag_service.retrieve,
        [kb_id],
        request.query,
        request.top_k,
        request.score_threshold,
    )
    return {
        "code": 200,
        "message": "success",
        "data": {"query": request.query, "results": results},
    }


# ==================== Agent 绑定 ====================

@router.put("/agents/{agent_id}/knowledge-bases")
async def bind_agent_knowledge_bases(
    agent_id: UUID,
    request: AgentKbBindRequest,
    user: User = Depends(get_current_user),
):
    """全量覆盖 Agent 绑定的知识库。"""
    from app.models.agent import Agent

    from app.services.database import database_service

    with database_service.get_session_maker()() as session:
        agent = session.get(Agent, agent_id)
        if agent is None:
            raise NotFoundError("Agent not found")
        if not (user.role == "admin" or agent.owner_id == user.id):
            raise PermissionError("Only owner or admin can bind knowledge bases")

    try:
        await asyncio.to_thread(
            rag_service.set_agent_kbs, agent_id, [str(k) for k in request.kb_ids], user.id
        )
    except ValueError as exc:
        if str(exc).startswith("KB_NOT_ACCESSIBLE"):
            raise PermissionError("Knowledge base not accessible")
        raise NotFoundError(str(exc))
    return {"code": 200, "message": "绑定成功", "data": {"kb_count": len(request.kb_ids)}}


@router.get("/agents/{agent_id}/knowledge-bases")
async def list_agent_knowledge_bases(
    agent_id: UUID,
    user: User = Depends(get_current_user),
):
    """查询 Agent 绑定的知识库 ID 列表。"""
    kb_ids = await asyncio.to_thread(rag_service.get_agent_kb_ids, agent_id)
    return {"code": 200, "message": "success", "data": {"kb_ids": kb_ids}}
