"""RAG 知识库服务：知识库/文档 CRUD、文档切片向量化、语义检索。

沿用项目既有风格：方法声明为普通同步函数，内部使用同步 SQLAlchemy Session；
async API 层通过 asyncio.to_thread 调用。
"""

import hashlib
import io
from typing import Optional
from uuid import UUID, uuid4

from langchain_text_splitters import RecursiveCharacterTextSplitter
from sqlalchemy import delete

from app.core.config import settings
from app.core.logging import logger
from app.models.rag import (
    AgentKnowledgeBase,
    KnowledgeBase,
    KnowledgeChunk,
    KnowledgeDocument,
)
from app.services.database import database_service
from app.services.embedding import embedding_service

# 支持的上传格式
ALLOWED_EXTENSIONS = {".txt", ".md", ".pdf"}
# 文档切片批量 embedding 的批大小
_EMBED_BATCH_SIZE = 16


class RagService:
    """知识库领域服务。"""

    def __init__(self) -> None:
        self.session_maker = database_service.get_session_maker()

    # ==================== 知识库 ====================

    def create_kb(
        self,
        owner_id: int,
        name: str,
        description: Optional[str] = None,
        is_public: bool = False,
        chunk_size: Optional[int] = None,
        chunk_overlap: Optional[int] = None,
        top_k: Optional[int] = None,
    ) -> KnowledgeBase:
        with self.session_maker() as session:
            kb = KnowledgeBase(
                id=uuid4(),
                name=name.strip(),
                description=description,
                is_public=is_public,
                owner_id=owner_id,
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
                top_k=top_k,
            )
            session.add(kb)
            session.commit()
            session.refresh(kb)
            logger.info("knowledge_base_created", kb_id=str(kb.id), owner_id=owner_id)
            return kb

    def get_kb(self, kb_id: str | UUID) -> Optional[KnowledgeBase]:
        with self.session_maker() as session:
            return session.get(KnowledgeBase, UUID(str(kb_id)))

    def list_kbs(
        self,
        owner_id: Optional[int] = None,
        include_public: bool = True,
        page: int = 1,
        size: int = 20,
        search: Optional[str] = None,
    ) -> dict:
        """列出知识库：默认返回本人拥有 + 公开的库。"""
        with self.session_maker() as session:
            query = session.query(KnowledgeBase)
            conditions = []
            if include_public:
                conditions.append(KnowledgeBase.is_public.is_(True))
            if owner_id is not None:
                conditions.append(KnowledgeBase.owner_id == owner_id)
            query = query.filter(_or_conditions(conditions))
            if search:
                query = query.filter(KnowledgeBase.name.ilike(f"%{search}%"))
            total = query.count()
            rows = (
                query.order_by(KnowledgeBase.created_at.desc())
                .offset((page - 1) * size)
                .limit(size)
                .all()
            )
            items = []
            for kb in rows:
                doc_count = (
                    session.query(KnowledgeDocument)
                    .filter(
                        KnowledgeDocument.kb_id == kb.id,
                        KnowledgeDocument.status == "ready",
                    )
                    .count()
                )
                items.append(
                    {
                        "id": kb.id,
                        "name": kb.name,
                        "description": kb.description,
                        "is_public": kb.is_public,
                        "owner_id": kb.owner_id,
                        "top_k": kb.top_k or settings.RAG_TOP_K,
                        "document_count": doc_count,
                        "created_at": kb.created_at,
                    }
                )
            return {"items": items, "total": total, "page": page, "size": size}

    def delete_kb(self, kb_id: str | UUID) -> bool:
        """删除知识库及其全部文档/分片/Agent 绑定。"""
        kb_uuid = UUID(str(kb_id))
        with self.session_maker() as session:
            kb = session.get(KnowledgeBase, kb_uuid)
            if kb is None:
                return False
            doc_ids = [
                row[0]
                for row in session.query(KnowledgeDocument.id)
                .filter(KnowledgeDocument.kb_id == kb_uuid)
                .all()
            ]
            if doc_ids:
                session.execute(
                    delete(KnowledgeChunk).where(KnowledgeChunk.document_id.in_(doc_ids))
                )
            session.execute(
                delete(KnowledgeDocument).where(KnowledgeDocument.kb_id == kb_uuid)
            )
            session.execute(
                delete(AgentKnowledgeBase).where(AgentKnowledgeBase.kb_id == kb_uuid)
            )
            session.delete(kb)
            session.commit()
            logger.info("knowledge_base_deleted", kb_id=str(kb_uuid))
            return True

    # ==================== 文档 ====================

    def add_document(
        self, kb_id: str | UUID, filename: str, raw: bytes
    ) -> KnowledgeDocument:
        """上传并索引一个文档（解析 → 切片 → embedding → 落库）。

        状态机：processing -> ready / failed；同知识库内 sha256 去重。
        """
        kb_uuid = UUID(str(kb_id))
        with self.session_maker() as session:
            kb = session.get(KnowledgeBase, kb_uuid)
            if kb is None:
                raise ValueError("Knowledge base not found")

            ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
            if f".{ext}" not in ALLOWED_EXTENSIONS:
                raise ValueError(
                    f"Unsupported file type .{ext}; allowed: {sorted(ALLOWED_EXTENSIONS)}"
                )

            file_hash = hashlib.sha256(raw).hexdigest()
            exists = (
                session.query(KnowledgeDocument)
                .filter(
                    KnowledgeDocument.kb_id == kb_uuid,
                    KnowledgeDocument.file_hash == file_hash,
                )
                .first()
            )
            if exists is not None:
                raise ValueError(f"Duplicate file (already uploaded as {exists.filename})")

            doc = KnowledgeDocument(
                id=uuid4(),
                kb_id=kb_uuid,
                filename=filename,
                file_hash=file_hash,
                status="processing",
            )
            session.add(doc)
            session.commit()

            try:
                text = self._extract_text(f".{ext}", raw)
                if not text.strip():
                    raise ValueError("No readable text content in file")

                chunks = self._split_text(
                    text,
                    chunk_size=kb.chunk_size or settings.RAG_CHUNK_SIZE,
                    chunk_overlap=kb.chunk_overlap or settings.RAG_CHUNK_OVERLAP,
                )
                vectors = self._embed_in_batches(chunks)

                session.add_all(
                    [
                        KnowledgeChunk(
                            id=uuid4(),
                            document_id=doc.id,
                            kb_id=kb_uuid,
                            chunk_index=idx,
                            content=chunk,
                            embedding=vector,
                        )
                        for idx, (chunk, vector) in enumerate(zip(chunks, vectors))
                    ]
                )
                doc.status = "ready"
                doc.chunk_count = len(chunks)
                doc.char_count = len(text)
                doc.error = None
                session.commit()
                session.refresh(doc)
                logger.info(
                    "knowledge_document_indexed",
                    doc_id=str(doc.id),
                    kb_id=str(kb_uuid),
                    chunks=len(chunks),
                )
                return doc
            except Exception as exc:
                session.rollback()
                failed = session.get(KnowledgeDocument, doc.id)
                if failed is not None:
                    failed.status = "failed"
                    failed.error = str(exc)[:1000]
                    session.commit()
                logger.exception(
                    "knowledge_document_index_failed",
                    doc_id=str(doc.id),
                    kb_id=str(kb_uuid),
                    error=str(exc),
                )
                raise

    def list_documents(self, kb_id: str | UUID) -> list[dict]:
        kb_uuid = UUID(str(kb_id))
        with self.session_maker() as session:
            rows = (
                session.query(KnowledgeDocument)
                .filter(KnowledgeDocument.kb_id == kb_uuid)
                .order_by(KnowledgeDocument.created_at.desc())
                .all()
            )
            return [
                {
                    "id": d.id,
                    "filename": d.filename,
                    "status": d.status,
                    "chunk_count": d.chunk_count,
                    "char_count": d.char_count,
                    "error": d.error,
                    "created_at": d.created_at,
                }
                for d in rows
            ]

    def delete_document(self, doc_id: str | UUID) -> bool:
        doc_uuid = UUID(str(doc_id))
        with self.session_maker() as session:
            doc = session.get(KnowledgeDocument, doc_uuid)
            if doc is None:
                return False
            session.execute(
                delete(KnowledgeChunk).where(KnowledgeChunk.document_id == doc_uuid)
            )
            session.delete(doc)
            session.commit()
            logger.info("knowledge_document_deleted", doc_id=str(doc_uuid))
            return True

    # ==================== 检索 ====================

    def retrieve(
        self,
        kb_ids: list[str | UUID],
        query: str,
        top_k: Optional[int] = None,
        score_threshold: float = 0.0,
    ) -> list[dict]:
        """跨知识库语义检索。

        score 统一为 0~1 余弦相似度（pgvector cosine_distance ∈ [0,2]，score=1-d/2），
        score_threshold 与 score 同域，默认 0 不过滤。
        """
        if not kb_ids or not query.strip():
            return []
        kb_uuids = [UUID(str(k)) for k in kb_ids]
        if top_k is None:
            top_k = settings.RAG_TOP_K
            with self.session_maker() as session:
                kb = session.get(KnowledgeBase, kb_uuids[0])
                if kb is not None and kb.top_k:
                    top_k = kb.top_k

        query_vector = embedding_service.embed_query(query)
        distance = KnowledgeChunk.embedding.cosine_distance(query_vector).label("distance")

        with self.session_maker() as session:
            rows = (
                session.query(KnowledgeChunk, KnowledgeDocument.filename, distance)
                .join(
                    KnowledgeDocument,
                    KnowledgeDocument.id == KnowledgeChunk.document_id,
                )
                .filter(KnowledgeChunk.kb_id.in_(kb_uuids))
                .order_by(distance)
                .limit(top_k)
                .all()
            )
            results = []
            for chunk, filename, dist in rows:
                score = round(1 - float(dist) / 2, 4)
                if score < score_threshold:
                    continue
                results.append(
                    {
                        "chunk_id": str(chunk.id),
                        "document_id": str(chunk.document_id),
                        "kb_id": str(chunk.kb_id),
                        "filename": filename,
                        "chunk_index": chunk.chunk_index,
                        "content": chunk.content,
                        "score": score,
                    }
                )
            return results

    def build_retriever(
        self,
        kb_ids: list[str | UUID],
        top_k: Optional[int] = None,
        score_threshold: float = 0.0,
    ):
        """构造 LangChain Runnable 检索器。

        作为标准 Runnable 在 graph 中 ainvoke 时，callbacks 自动传播，
        Langfuse trace 树中会出现 knowledge_retriever 节点（含 query 与命中文档）。
        """
        from langchain_core.runnables import RunnableLambda

        def _run(query: str) -> list[dict]:
            return self.retrieve(kb_ids, query, top_k, score_threshold)

        return RunnableLambda(_run, name="knowledge_retriever")

    # ==================== Agent 绑定 ====================

    def set_agent_kbs(
        self,
        agent_id: str | UUID,
        kb_ids: list[str | UUID],
        user_id: Optional[int] = None,
    ) -> None:
        """重建 Agent 的知识库绑定。

        user_id 不为 None 时校验 KB 归属/公开性（my 私有路径）；
        user_id 为 None 表示管理端路径，只校验 KB 存在（可绑定任意库）。
        """
        agent_uuid = UUID(str(agent_id))
        kb_uuids = [UUID(str(k)) for k in kb_ids]
        with self.session_maker() as session:
            for kb_uuid in kb_uuids:
                kb = session.get(KnowledgeBase, kb_uuid)
                if kb is None:
                    raise ValueError(f"Knowledge base {kb_uuid} not found")
                if user_id is not None and not kb.is_public and kb.owner_id != user_id:
                    # API 层按消息前缀转 403
                    raise ValueError(f"KB_NOT_ACCESSIBLE:{kb_uuid}")
            session.execute(
                delete(AgentKnowledgeBase).where(
                    AgentKnowledgeBase.agent_id == agent_uuid
                )
            )
            session.add_all(
                [AgentKnowledgeBase(agent_id=agent_uuid, kb_id=kb) for kb in kb_uuids]
            )
            session.commit()
            logger.info(
                "agent_knowledge_bases_set",
                agent_id=str(agent_uuid),
                kb_count=len(kb_uuids),
            )

    def get_agent_kb_ids(self, agent_id: str | UUID) -> list[str]:
        agent_uuid = UUID(str(agent_id))
        with self.session_maker() as session:
            rows = (
                session.query(AgentKnowledgeBase.kb_id)
                .filter(AgentKnowledgeBase.agent_id == agent_uuid)
                .all()
            )
            return [str(row[0]) for row in rows]

    # ==================== 内部工具 ====================

    @staticmethod
    def _extract_text(ext: str, raw: bytes) -> str:
        if ext in (".txt", ".md"):
            return raw.decode("utf-8", errors="ignore")
        if ext == ".pdf":
            from pypdf import PdfReader

            reader = PdfReader(io.BytesIO(raw))
            return "\n".join((page.extract_text() or "") for page in reader.pages)
        raise ValueError(f"Unsupported file type {ext}")

    @staticmethod
    def _split_text(text: str, chunk_size: int, chunk_overlap: int) -> list[str]:
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=["\n\n", "\n", "。", "！", "？", "；", ". ", " ", ""],
            keep_separator=True,
            strip_whitespace=True,
        )
        return [c for c in splitter.split_text(text) if c.strip()]

    @staticmethod
    def _embed_in_batches(texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for start in range(0, len(texts), _EMBED_BATCH_SIZE):
            vectors.extend(
                embedding_service.embed_documents(texts[start : start + _EMBED_BATCH_SIZE])
            )
        return vectors


def _or_conditions(conditions: list):
    """组合可选 OR 条件，空条件返回永真。"""
    from sqlalchemy import true

    if not conditions:
        return true()
    if len(conditions) == 1:
        return conditions[0]
    expr = conditions[0]
    for c in conditions[1:]:
        expr = expr | c
    return expr


rag_service = RagService()
