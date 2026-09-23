"""Embedding 服务：统一封装两种 provider。

- local：本地 sentence-transformers（默认 BAAI/bge-small-zh-v1.5，512 维），无外部依赖
- openai：OpenAI 兼容接口（DashScope text-embedding-v2，1536 维）

方法均为同步阻塞（本地 CPU 推理 / 远程 HTTP），async 调用方请用 asyncio.to_thread 包装。
"""

import os
from typing import Optional

from app.core.config import settings
from app.core.logging import logger

# 国内下载 HF 模型走镜像（必须在 huggingface_hub 被读取前设置）
if settings.RAG_EMBEDDING_PROVIDER == "local":
    os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
    # 模型已缓存到本机，运行时不再做在线元数据检查（规避代理 SSL 拦截）
    os.environ.setdefault("HF_HUB_OFFLINE", "1")

# bge 中文检索的官方查询指令（仅 query 侧加，文档侧不加）
_BGE_QUERY_INSTRUCTION = "为这个句子生成表示以用于检索相关文章："


class EmbeddingService:
    """文档/查询向量化服务（进程内单例，底层模型延迟加载）。"""

    def __init__(self) -> None:
        self.provider = settings.RAG_EMBEDDING_PROVIDER
        self._local_model = None
        self._openai_model = None

    # ---------- 底层模型延迟初始化 ----------

    def _get_local_model(self):
        if self._local_model is None:
            from sentence_transformers import SentenceTransformer

            model_name = settings.RAG_LOCAL_EMBEDDING_MODEL
            logger.info("embedding_local_model_loading", model=model_name)
            # local_files_only：模型已通过 hf-mirror 预下载到本机缓存，禁止运行时联网校验
            self._local_model = SentenceTransformer(model_name, local_files_only=True)
            logger.info(
                "embedding_local_model_loaded",
                model=model_name,
                dim=self._local_model.get_sentence_embedding_dimension(),
            )
        return self._local_model

    def _get_openai_model(self):
        if self._openai_model is None:
            from langchain_openai import OpenAIEmbeddings

            self._openai_model = OpenAIEmbeddings(
                model=settings.RAG_EMBEDDING_MODEL,
                api_key=settings.RAG_EMBEDDING_API_KEY,
                base_url=settings.RAG_EMBEDDING_BASE_URL,
            )
            logger.info(
                "embedding_openai_initialized",
                model=settings.RAG_EMBEDDING_MODEL,
                base_url=settings.RAG_EMBEDDING_BASE_URL,
            )
        return self._openai_model

    # ---------- 统一接口 ----------

    @property
    def dim(self) -> int:
        """向量维度，需与 knowledge_chunk.embedding 列一致。"""
        return settings.RAG_EMBEDDING_DIM

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """批量文档切片向量化。"""
        if not texts:
            return []
        if self.provider == "local":
            vectors = self._get_local_model().encode(
                texts, normalize_embeddings=True, show_progress_bar=False
            )
            return [v.tolist() for v in vectors]
        return self._get_openai_model().embed_documents(texts)

    def embed_query(self, text: str) -> list[float]:
        """单条查询向量化（bge 模型查询侧加检索指令）。"""
        if self.provider == "local":
            vector = self._get_local_model().encode(
                _BGE_QUERY_INSTRUCTION + text,
                normalize_embeddings=True,
                show_progress_bar=False,
            )
            return vector.tolist()
        return self._get_openai_model().embed_query(text)


embedding_service = EmbeddingService()
