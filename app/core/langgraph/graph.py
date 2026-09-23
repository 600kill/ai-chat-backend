"""这个文件包含 LangGraph 智能体/工作流，以及与大模型的交互逻辑。"""

import asyncio
import sys
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import (
    Any,
    AsyncGenerator,
    Optional,
)
from urllib.parse import quote_plus

from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    BaseMessage,
    HumanMessage,
    ToolMessage,
    convert_to_openai_messages,
)
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.errors import GraphInterrupt
from langgraph.graph import (
    END,
    StateGraph,
)
from langgraph.graph.state import (
    Command,
    CompiledStateGraph,
)
from langgraph.types import (
    RunnableConfig,
    StateSnapshot,
)
from psycopg import AsyncConnection
from psycopg_pool import AsyncConnectionPool, ConnectionPool

from app.core.config import (
    Environment,
    settings,
)
from app.core.langgraph.tools import tools
from app.core.logging import logger
#from app.core.metrics import llm_inference_duration_seconds
from app.core.observability import (
    flush_langfuse,
    make_callback_handler,
    trace_metadata,
)
from app.core.prompts import load_system_prompt
from app.schemas import (
    GraphState,
    Message,
)
from app.services.llm import llm_service
from app.services.memory import memory_service
from app.services.metrics_service import metrics_service
from app.utils import (
    dump_messages,
    extract_text_content,
    prepare_messages,
    process_llm_response,
)


@dataclass
class AgentConfig:
    """单次 Agent 运行的配置（由 agent_runtime_service 从 DB 组装）。

    所有字段均可为 None：None 表示沿用平台全局默认（默认提示词、首选模型、全部工具）。
    """

    system_prompt: Optional[str] = None
    model_name: Optional[str] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    # 该 Agent 绑定的工具名子集（对应 Tool.function_name）；空列表 = 不允许调工具
    tool_names: Optional[list[str]] = None
    # 绑定的知识库 ID（阶段 4 RAG 使用）
    kb_ids: Optional[list[str]] = None
    # 版本快照（阶段 6 使用）：从历史版本还原的完整配置
    version_snapshot: Optional[dict[str, Any]] = None
    # 版本降级警告（阶段 6）：快照中缺失的工具执行器/已删除知识库等，跳过并提示，不报错
    warnings: Optional[list[str]] = None


@dataclass
class RunResult:
    """Agent 单次运行的结构化结果，供 API 与评测模块消费。"""

    messages: list[dict] = field(default_factory=list)
    tool_calls: list[dict] = field(default_factory=list)
    retrieved_docs: list[dict] = field(default_factory=list)
    model: Optional[str] = None
    latency_ms: int = 0
    interrupted: bool = False
    error: Optional[str] = None
    # 版本运行的降级警告（正常按当前配置运行时为 None）
    warnings: Optional[list[str]] = None


class _AsyncConnectionWrapper(AsyncConnectionPool):
    """Windows 兼容的异步连接池包装器。

    使用 sync ConnectionPool + asyncio.to_thread 替代 AsyncConnectionPool，
    解决 psycopg3 async 在 Windows ProactorEventLoop 下的兼容性问题。

    继承 AsyncConnectionPool 仅为通过新版 langgraph 的 isinstance 连接类型校验，
    不调用父类 __init__（不建立任何真实异步连接）。
    """

    def __init__(self, conninfo: str, **kwargs):
        self._pool = ConnectionPool(conninfo, open=False, **kwargs)

    async def open(self):
        await asyncio.to_thread(self._pool.open)

    async def close(self):
        await asyncio.to_thread(self._pool.close)

    @asynccontextmanager
    async def connection(self):
        with self._pool.connection() as conn:
            yield _SyncConnectionWrapper(conn)


class _SyncConnectionWrapper(AsyncConnection):
    """将 sync 连接包装为 async 接口，供 AsyncPostgresSaver 使用。

    继承 AsyncConnection 仅为通过 isinstance 校验，不调用父类 __init__。
    """

    def __init__(self, conn):
        self._conn = conn

    def __getattr__(self, name):
        """将未包装的属性/方法透传到原始连接。"""
        return getattr(self._conn, name)

    async def execute(self, query, params=None, **kwargs):
        result = await asyncio.to_thread(self._conn.execute, query, params, **kwargs)
        return _SyncCursorWrapper(result) if result else result

    def cursor(self, **kwargs):
        """同步工厂：返回包装后的 cursor（与真实 AsyncConnection.cursor 签名语义一致）。"""
        result = self._conn.cursor(**kwargs)
        return _SyncCursorWrapper(result)

    @asynccontextmanager
    async def transaction(self):
        sync_cm = self._conn.transaction()
        try:
            await asyncio.to_thread(sync_cm.__enter__)
            yield
        except BaseException:
            exc_info = sys.exc_info()
            await asyncio.to_thread(sync_cm.__exit__, *exc_info)
            raise
        else:
            await asyncio.to_thread(sync_cm.__exit__, None, None, None)

    @asynccontextmanager
    async def pipeline(self):
        sync_cm = self._conn.pipeline()
        try:
            yield await asyncio.to_thread(sync_cm.__enter__)
        except BaseException:
            exc_info = sys.exc_info()
            await asyncio.to_thread(sync_cm.__exit__, *exc_info)
            raise
        else:
            await asyncio.to_thread(sync_cm.__exit__, None, None, None)


class _SyncCursorWrapper:
    """将 sync cursor 包装为 async 接口。"""

    def __init__(self, cursor):
        self._cursor = cursor

    def __getattr__(self, name):
        return getattr(self._cursor, name)

    async def fetchone(self):
        return await asyncio.to_thread(self._cursor.fetchone)

    async def fetchall(self):
        return await asyncio.to_thread(self._cursor.fetchall)

    async def fetchmany(self, size=None):
        return await asyncio.to_thread(self._cursor.fetchmany, size)

    async def execute(self, query, params=None, **kwargs):
        await asyncio.to_thread(self._cursor.execute, query, params, **kwargs)
        return self

    async def executemany(self, query, params, **kwargs):
        await asyncio.to_thread(self._cursor.executemany, query, params, **kwargs)
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await asyncio.to_thread(self._cursor.close)

    async def __aiter__(self):
        for row in await asyncio.to_thread(list, self._cursor):
            yield row


class LangGraphAgent:
    """管理 LangGraph 智能体/工作流，以及与大模型的交互。

    这个类负责创建和管理 LangGraph 工作流，
    包括大模型调用、数据库连接、响应处理。
    """

    def __init__(self):
        """初始化 LangGraph 智能体，加载所需组件。"""
        # 使用已绑定工具的大模型服务
        self.llm_service = llm_service
        self.llm_service.bind_tools(tools)
        self.tools_by_name = {tool.name: tool for tool in tools}
        self._connection_pool: Optional[_AsyncConnectionWrapper] = None
        self._graph: Optional[CompiledStateGraph] = None
        logger.info(
            "langgraph_agent_initialized",
            model=settings.DEFAULT_LLM_MODEL,
            environment=settings.ENVIRONMENT.value,
        )

    async def _get_connection_pool(self) -> _AsyncConnectionWrapper:
        """根据环境配置获取 PostgreSQL 连接池（Windows兼容）。

        返回：
            _AsyncConnectionWrapper：PostgreSQL 数据库连接池。
        """
        if self._connection_pool is None:
            try:
                # 根据环境配置连接池大小
                max_size = settings.POSTGRES_POOL_SIZE

                connection_url = (
                    "postgresql://"
                    f"{quote_plus(settings.POSTGRES_USER)}:{quote_plus(settings.POSTGRES_PASSWORD)}"
                    f"@{settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}/{settings.POSTGRES_DB}"
                )

                self._connection_pool = _AsyncConnectionWrapper(
                    connection_url,
                    max_size=max_size,
                    kwargs={
                        "autocommit": True,
                        "connect_timeout": 5,
                        "prepare_threshold": None,
                    },
                )
                await self._connection_pool.open()
                logger.info("connection_pool_created", max_size=max_size, environment=settings.ENVIRONMENT.value)
            except Exception as e:
                logger.error("connection_pool_creation_failed", error=str(e), environment=settings.ENVIRONMENT.value)
                # 生产环境下需要优雅降级
                if settings.ENVIRONMENT == Environment.PRODUCTION:
                    logger.warning("continuing_without_connection_pool", environment=settings.ENVIRONMENT.value)
                    return None
                raise e
        return self._connection_pool

    async def _retrieve_knowledge(self, state: GraphState, config: RunnableConfig) -> Command:
        """图入口节点：按 Agent 绑定的知识库执行向量检索，结果写入 state。

        - 仅 Agent Runtime 路径且 metadata.agent_kb_ids 非空时检索，普通 chatbot 直接跳过；
        - 检索器是标准 LangChain Runnable，节点内 ainvoke 时 callbacks 自动传播，
          Langfuse trace 中呈现 retrieve_knowledge → knowledge_retriever 子树；
        - 检索失败降级为空参考资料，不阻断主对话。
        """
        metadata = config.get("metadata", {}) or {}
        kb_ids = metadata.get("agent_kb_ids") or []
        if not kb_ids:
            return Command(goto="chat")

        # 取最后一条人类消息作为检索 query
        query = ""
        for msg in reversed(state.messages):
            if isinstance(msg, HumanMessage):
                query = str(msg.content or "")
                break
        if not query:
            return Command(goto="chat")

        session_id = config["configurable"]["thread_id"]
        metrics_session_id = metadata.get("metrics_session_id")
        try:
            from app.services.rag_service import rag_service

            rag_start = time.time()
            retriever = rag_service.build_retriever(kb_ids)
            docs = await retriever.ainvoke(query, config=config)
            rag_duration_ms = int((time.time() - rag_start) * 1000)

            if metrics_session_id:
                await metrics_service.record_vector_search(
                    metrics_session_id=metrics_session_id,
                    session_id=session_id,
                    search_duration_ms=rag_duration_ms,
                    results_count=len(docs),
                    query_length=len(query),
                    memory_type="rag",
                )

            blocks = [
                f"[{idx + 1}] 来源：{d.get('filename', 'unknown')}"
                f"（相关度 {d.get('score')}）\n{d['content']}"
                for idx, d in enumerate(docs)
            ]
            logger.info(
                "rag_retrieval_done",
                session_id=session_id,
                kb_count=len(kb_ids),
                hits=len(docs),
                duration_ms=rag_duration_ms,
            )
            return Command(
                update={
                    "reference_context": "\n\n".join(blocks) if blocks else None,
                    "retrieved_docs": docs,
                },
                goto="chat",
            )
        except Exception as rag_error:
            logger.warning("rag_retrieval_failed", error=str(rag_error), session_id=session_id)
            return Command(update={"reference_context": None, "retrieved_docs": []}, goto="chat")

    async def _chat(self, state: GraphState, config: RunnableConfig) -> Command:
        """处理聊天状态并生成响应。

        参数：
            state (GraphState)：当前对话状态。
            config (RunnableConfig)：当前调用的配置信息。

        返回：
            Command：包含更新后状态与下一个执行节点的指令对象。
        """
        node_start_time = time.time()

        metadata = config.get("metadata", {}) or {}
        is_agent_run = metadata.get("agent_runtime") is True

        # 获取当前大模型实例，用于指标统计（Agent 运行时在调用后按实际响应回填）
        current_llm = self.llm_service.get_llm()
        model_name = (
            current_llm.model_name
            if current_llm and hasattr(current_llm, "model_name")
            else settings.DEFAULT_LLM_MODEL
        )

        username = metadata.get("username")
        system_prompt_override = metadata.get("agent_system_prompt")
        # RAG 参考资料来自 retrieve_knowledge 节点写入的 state（metadata 兜底）
        reference_context = state.reference_context or metadata.get("reference_context")

        # Agent 自定义提示词直接覆盖默认模板；否则加载平台默认模板
        if is_agent_run and system_prompt_override:
            SYSTEM_PROMPT = system_prompt_override
            if state.long_term_memory and state.long_term_memory != "未找到相关记忆。":
                SYSTEM_PROMPT = f"{SYSTEM_PROMPT}\n\n# 用户长期记忆\n{state.long_term_memory}"
        else:
            SYSTEM_PROMPT = load_system_prompt(username=username, long_term_memory=state.long_term_memory)

        # RAG 参考资料注入（阶段 4 由 run() 检索后写入 metadata）
        if reference_context:
            SYSTEM_PROMPT = (
                f"{SYSTEM_PROMPT}\n\n# Reference Context\n{reference_context}\n\n"
                "请优先基于以上参考内容回答；若参考内容与问题无关，可忽略并按已有知识回答。"
            )

        # 拼接系统提示词，准备消息
        messages = prepare_messages(state.messages, SYSTEM_PROMPT)
        session_id = config["configurable"]["thread_id"]
        metrics_session_id = metadata.get("metrics_session_id")

        try:
            # LLM 推理埋点开始
            llm_start_time = time.time()

            if is_agent_run:
                # Agent 路径：按本次运行配置构造本地模型实例，不污染全局默认实例
                tool_names = metadata.get("agent_tool_names") or []
                tool_subset = [
                    self.tools_by_name[name]
                    for name in tool_names
                    if name in self.tools_by_name
                ]
                # 绑定知识库的 Agent 自动获得 document_search 工具（主动检索补充自动注入的参考上下文）
                if metadata.get("agent_kb_ids") and "document_search" in self.tools_by_name:
                    tool_subset.append(self.tools_by_name["document_search"])
                response_message = await self.llm_service.call_agent(
                    dump_messages(messages),
                    model_name=metadata.get("agent_model_name"),
                    tools=tool_subset or None,
                    temperature=metadata.get("agent_temperature"),
                    max_tokens=metadata.get("agent_max_tokens"),
                )
                model_name = self._extract_model_name(response_message, model_name)
            else:
                # 平台默认 chatbot 路径：全局工具绑定 + 循环降级
                response_message = await self.llm_service.call(dump_messages(messages))
            '''with llm_inference_duration_seconds.labels(model=model_name).time():
                response_message = await self.llm_service.call(dump_messages(messages))'''

            llm_end_time = time.time()
            llm_duration_ms = int((llm_end_time - llm_start_time) * 1000)
            
            # 记录 LLM 推理指标（简化：不记录 token 数）
            if metrics_session_id:
                await metrics_service.record_llm_inference(
                    metrics_session_id=metrics_session_id,
                    session_id=session_id,
                    llm_model=model_name,
                    inference_duration_ms=llm_duration_ms,
                    input_tokens=0,
                    output_tokens=0,
                    total_tokens=0
                )

            # 处理响应，解析结构化内容块
            response_message = process_llm_response(response_message)

            logger.info(
                "llm_response_generated",
                session_id=session_id,
                model=model_name,
                environment=settings.ENVIRONMENT.value,
            )

            # 根据是否存在工具调用，决定下一个节点
            if response_message.tool_calls:
                goto = "tool_call"
            else:
                goto = END
            
            # 记录节点统计（明细 trace 由 Langfuse 承载，本地只存耗时/状态供评测聚合）
            node_end_time = time.time()
            node_duration_ms = int((node_end_time - node_start_time) * 1000)

            if metrics_session_id:
                await metrics_service.record_node_execution(
                    metrics_session_id=metrics_session_id,
                    session_id=session_id,
                    node_name="chat",
                    node_type="chat",
                    duration_ms=node_duration_ms,
                    status="success"
                )

            return Command(update={"messages": [response_message]}, goto=goto)
        except Exception as e:
            # 记录失败状态的节点执行指标
            node_end_time = time.time()
            node_duration_ms = int((node_end_time - node_start_time) * 1000)
            
            if metrics_session_id:
                await metrics_service.record_node_execution(
                    metrics_session_id=metrics_session_id,
                    session_id=session_id,
                    node_name="chat",
                    node_type="chat",
                    duration_ms=node_duration_ms,
                    status="failed"
                )
            
            logger.error(
                "llm_call_failed_all_models",
                session_id=session_id,
                error=str(e),
                environment=settings.ENVIRONMENT.value,
            )
            raise Exception(f"尝试所有模型后仍无法获取大模型响应：{str(e)}")

    # 定义工具节点
    async def _tool_call(self, state: GraphState, config: RunnableConfig) -> Command:
        """处理上一条消息中的工具调用。

        参数：
            state：包含消息与工具调用的当前智能体状态。
            config：当前调用配置，透传给工具（callbacks 挂 Langfuse、metadata 提供 document_search 默认知识库）。

        返回：
            Command：包含更新后消息并路由回聊天节点的指令。
        """
        node_start_time = time.time()

        tool_calls = state.messages[-1].tool_calls
        node_metadata = (config.get("metadata", {}) or {})
        session_id = node_metadata.get("session_id", "")
        metrics_session_id = node_metadata.get("metrics_session_id", "")

        async def _execute_tool(tool_call: dict) -> BaseMessage:
            tool_start_time = time.time()
            tool_name = tool_call["name"]

            try:
                tool_result = await self.tools_by_name[tool_name].ainvoke(
                    tool_call["args"], config=config
                )
                tool_end_time = time.time()
                tool_duration_ms = int((tool_end_time - tool_start_time) * 1000)
                
                # 记录工具调用统计（参数/结果明细由 Langfuse 记录）
                if metrics_session_id:
                    await metrics_service.record_tool_call(
                        metrics_session_id=metrics_session_id,
                        session_id=session_id,
                        tool_name=tool_name,
                        call_duration_ms=tool_duration_ms,
                        status="success"
                    )
            except Exception as e:
                tool_end_time = time.time()
                tool_duration_ms = int((tool_end_time - tool_start_time) * 1000)
                
                # 记录失败的工具调用（仅错误原因，不含参数明细）
                if metrics_session_id:
                    await metrics_service.record_tool_call(
                        metrics_session_id=metrics_session_id,
                        session_id=session_id,
                        tool_name=tool_name,
                        call_duration_ms=tool_duration_ms,
                        status="failed",
                        error_message=str(e)
                    )
                raise
            
            # 如果是生成图表工具，直接返回包含图片的assistant消息
            # 不再走LLM二次生成，确保图片能正确展示
            if tool_name == "generate_chart":
                # 检查工具是否返回了错误信息（以"错误"开头）
                if isinstance(tool_result, str) and tool_result.startswith("错误"):
                    return AIMessage(content=tool_result)
                return AIMessage(
                    content=f"图表已生成：\n\n![chart](/api/v1/chatbot/image/{tool_result})"
                )
            return ToolMessage(
                content=tool_result,
                name=tool_name,
                tool_call_id=tool_call["id"],
            )

        # 当有多个工具调用时，并发执行
        try:
            if len(tool_calls) == 1:
                outputs = [await _execute_tool(tool_calls[0])]
            else:
                outputs = list(await asyncio.gather(*[_execute_tool(tc) for tc in tool_calls]))
            
            # 记录节点执行指标
            node_end_time = time.time()
            node_duration_ms = int((node_end_time - node_start_time) * 1000)
            
            if metrics_session_id:
                await metrics_service.record_node_execution(
                    metrics_session_id=metrics_session_id,
                    session_id=session_id,
                    node_name="tool_call",
                    node_type="tool_call",
                    duration_ms=node_duration_ms,
                    status="success"
                )

            # 检查是否所有输出都是AIMessage（图表生成），如果是则直接结束
            if all(isinstance(o, AIMessage) for o in outputs):
                return Command(update={"messages": outputs}, goto=END)

            return Command(update={"messages": outputs}, goto="chat")
        except Exception as e:
            # 记录失败状态的节点执行指标
            node_end_time = time.time()
            node_duration_ms = int((node_end_time - node_start_time) * 1000)
            
            if metrics_session_id:
                await metrics_service.record_node_execution(
                    metrics_session_id=metrics_session_id,
                    session_id=session_id,
                    node_name="tool_call",
                    node_type="tool_call",
                    duration_ms=node_duration_ms,
                    status="failed"
                )
            raise

    async def create_graph(self) -> Optional[CompiledStateGraph]:
        """创建并配置 LangGraph 工作流。

        返回：
            Optional[CompiledStateGraph]：配置好的 LangGraph 实例，初始化失败则返回 None
        """
        if self._graph is None:
            try:
                graph_builder = StateGraph(GraphState)
                # 入口先做知识库检索（未绑定 KB 时节点空转），再进入 chat；
                # tool_call 回边直接到 chat，故每轮只检索一次，中断恢复也不会重复检索
                graph_builder.add_node("retrieve_knowledge", self._retrieve_knowledge, ends=["chat"])
                graph_builder.add_node("chat", self._chat, ends=["tool_call", END])
                graph_builder.add_node("tool_call", self._tool_call, ends=["chat"])
                graph_builder.set_entry_point("retrieve_knowledge")
                graph_builder.set_finish_point("chat")

                # 获取连接池（生产环境数据库不可用时可能为 None）
                connection_pool = await self._get_connection_pool()
                if connection_pool:
                    checkpointer = AsyncPostgresSaver(connection_pool)
                    await checkpointer.setup()
                else:
                    # 生产环境必要时可无状态持久化运行
                    checkpointer = None
                    if settings.ENVIRONMENT != Environment.PRODUCTION:
                        raise Exception("连接池初始化失败")

                self._graph = graph_builder.compile(
                    checkpointer=checkpointer, name=f"{settings.PROJECT_NAME} Agent ({settings.ENVIRONMENT.value})"
                )

                logger.info(
                    "graph_created",
                    graph_name=f"{settings.PROJECT_NAME} Agent",
                    environment=settings.ENVIRONMENT.value,
                    has_checkpointer=checkpointer is not None,
                )
            except Exception as e:
                logger.error("graph_creation_failed", error=str(e), environment=settings.ENVIRONMENT.value)
                # 生产环境不希望直接崩溃
                if settings.ENVIRONMENT == Environment.PRODUCTION:
                    logger.warning("continuing_without_graph")
                    return None
                raise e

        return self._graph

    @staticmethod
    def _extract_model_name(message: BaseMessage, fallback: str) -> str:
        """尽力从模型响应元数据中提取实际服务模型名（降级后可能与请求模型不同）。"""
        for attr in ("model_name", "model"):
            value = getattr(message, attr, None)
            if isinstance(value, str) and value:
                return value
        metadata = getattr(message, "response_metadata", None) or {}
        for key in ("model_name", "model", "lm_model_name"):
            value = metadata.get(key)
            if isinstance(value, str) and value:
                return value
        return fallback

    @staticmethod
    def _build_run_metadata(
        session_id: str,
        user_id: Optional[str],
        username: Optional[str],
        metrics_session_id: Optional[str],
        agent_config: Optional[AgentConfig],
    ) -> dict:
        """组装 graph metadata。Agent 配置只放可 JSON 序列化的标量（会随 checkpoint 持久化）。"""
        metadata = {
            "user_id": user_id,
            "username": username,
            "session_id": session_id,
            "environment": settings.ENVIRONMENT.value,
            "debug": settings.DEBUG,
            "metrics_session_id": str(metrics_session_id) if metrics_session_id else None,
        }
        if agent_config is not None:
            metadata.update(
                {
                    "agent_runtime": True,
                    "agent_system_prompt": agent_config.system_prompt,
                    "agent_model_name": agent_config.model_name,
                    "agent_temperature": agent_config.temperature,
                    "agent_max_tokens": agent_config.max_tokens,
                    "agent_tool_names": agent_config.tool_names or [],
                    "agent_kb_ids": agent_config.kb_ids or [],
                }
            )
        return metadata

    async def run(
        self,
        messages: list[Message],
        session_id: str,
        *,
        config: Optional[AgentConfig] = None,
        user_id: Optional[str] = None,
        username: Optional[str] = None,
        agent_id: Optional[str] = None,
        record_metrics: bool = True,
        persist_memory: bool = True,
        extra_metadata: Optional[dict] = None,
    ) -> RunResult:
        """按 AgentConfig 执行一次完整 ReAct 运行，返回结构化 RunResult。

        与 get_response 的区别：调用方可以指定提示词/模型/温度/工具子集，
        并拿到工具调用、检索文档、模型、耗时等结构化信息（评测模块依赖）。

        参数：
            messages: 本轮输入消息（多轮时含历史）
            session_id: 会话/线程 ID（checkpointer thread_id）
            config: Agent 运行配置；None 表示平台默认 chatbot 路径
            user_id/username/agent_id: 会话归属信息
            record_metrics: 是否写入 metrics 会话（评测批量跑可关闭）
            persist_memory: 是否异步写入长期记忆（评测单轮跑可关闭）
        """
        session_start_time = time.time()
        metrics_session_id = None

        # 尝试创建指标会话
        if record_metrics:
            try:
                if agent_id and user_id:
                    from uuid import UUID
                    metrics_session_id = await metrics_service.start_session(
                        session_id=session_id,
                        agent_id=UUID(agent_id),
                        user_id=int(user_id)
                    )
            except Exception as e:
                logger.warning("metrics_session_start_failed", error=str(e))

        if self._graph is None:
            self._graph = await self.create_graph()

        run_metadata = self._build_run_metadata(
            session_id, user_id, username, metrics_session_id, config
        )
        # Langfuse：一次 run 一个 handler，LLM/Tool/Retriever 自动挂同一棵 trace
        lf_handler = make_callback_handler()
        run_metadata.update(
            trace_metadata(
                trace_name="agent-run" if config is not None else "chatbot",
                session_id=session_id,
                user_id=user_id,
                tags=["agent-runtime"] if config is not None else ["chatbot"],
                agent_id=agent_id,
                username=username,
                agent_model=config.model_name if config is not None else None,
            )
        )
        # 调用方附加元数据（如评测 source: "evaluation"），后写覆盖，trace 可区分来源
        if extra_metadata:
            run_metadata.update(extra_metadata)
        graph_config: RunnableConfig = {
            "configurable": {"thread_id": session_id},
            "callbacks": [lf_handler] if lf_handler is not None else [],
            "metadata": run_metadata,
        }
        # 版本快照运行的降级警告（阶段 6），透传到 RunResult
        config_warnings = config.warnings if config is not None else None

        async def _finish(total_status: str, error: Optional[str] = None) -> None:
            if not metrics_session_id:
                return
            total_duration_ms = int((time.time() - session_start_time) * 1000)
            try:
                await metrics_service.end_session(
                    metrics_session_id=metrics_session_id,
                    total_duration_ms=total_duration_ms,
                    status=total_status,
                    error_message=error,
                )
            except Exception as end_error:
                logger.warning("metrics_session_end_failed", error=str(end_error))

        rag_docs: list[dict] = []
        try:
            # 并发执行状态检查与记忆搜索，节省 200-500ms
            retrieval_start = time.time()
            state, relevant_memory = await asyncio.gather(
                self._graph.aget_state(graph_config),
                memory_service.search(user_id, messages[-1].content),
            )
            retrieval_duration_ms = int((time.time() - retrieval_start) * 1000)
            memory_results_count = len(relevant_memory) if isinstance(relevant_memory, list) else 0

            # 记录向量检索指标（长期记忆）
            if metrics_session_id:
                await metrics_service.record_vector_search(
                    metrics_session_id=metrics_session_id,
                    session_id=session_id,
                    search_duration_ms=retrieval_duration_ms,
                    results_count=memory_results_count,
                    query_length=len(messages[-1].content),
                    memory_type="long_term"
                )

            if state.next:
                logger.info("resuming_interrupted_graph", session_id=session_id, next_nodes=state.next)
                # 中断恢复从断点继续，不经过 retrieve_knowledge，无新增检索文档
                response = await self._graph.ainvoke(
                    Command(resume=messages[-1].content),
                    config=graph_config,
                )
            else:
                relevant_memory = relevant_memory or "未找到相关记忆。"
                # RAG 检索在图内 retrieve_knowledge 入口节点完成，命中结果写入最终 state
                response = await self._graph.ainvoke(
                    input={"messages": dump_messages(messages), "long_term_memory": relevant_memory},
                    config=graph_config,
                )
                rag_docs = response.get("retrieved_docs") or []

            # 检查本次调用是否触发中断（如 Human Approval）
            state = await self._graph.aget_state(graph_config)
            latency_ms = int((time.time() - session_start_time) * 1000)
            if state.next:
                interrupt_value = state.tasks[0].interrupts[0].value if state.tasks else "等待输入。"
                logger.info("graph_interrupted", session_id=session_id, interrupt_value=str(interrupt_value))
                await _finish("success")
                return RunResult(
                    messages=[{"role": "assistant", "content": str(interrupt_value)}],
                    interrupted=True,
                    latency_ms=latency_ms,
                    warnings=config_warnings,
                )

            raw_messages = response["messages"]

            if persist_memory:
                asyncio.create_task(
                    memory_service.add(
                        user_id, convert_to_openai_messages(raw_messages), graph_config["metadata"]
                    )
                )

            # 提取结构化工具调用记录（跨全部 ReAct 轮次）
            tool_calls: list[dict] = []
            final_model: Optional[str] = None
            for message in raw_messages:
                if isinstance(message, AIMessage):
                    final_model = self._extract_model_name(message, final_model or "")
                    for call in getattr(message, "tool_calls", None) or []:
                        tool_calls.append(
                            {
                                "name": call.get("name"),
                                "args": call.get("args", {}),
                                "id": call.get("id"),
                            }
                        )

            await _finish("success")
            return RunResult(
                messages=[m.model_dump() for m in self.__process_messages(raw_messages)],
                tool_calls=tool_calls,
                retrieved_docs=rag_docs,
                model=final_model or None,
                latency_ms=latency_ms,
                warnings=config_warnings,
            )
        except GraphInterrupt:
            state = await self._graph.aget_state(graph_config)
            interrupt_value = state.tasks[0].interrupts[0].value if state.tasks else "等待输入。"
            logger.info("graph_interrupted", session_id=session_id, interrupt_value=str(interrupt_value))
            await _finish("success")
            return RunResult(
                messages=[{"role": "assistant", "content": str(interrupt_value)}],
                interrupted=True,
                latency_ms=int((time.time() - session_start_time) * 1000),
                warnings=config_warnings,
            )
        except Exception as e:
            await _finish("failed", error=str(e))
            logger.exception("agent_run_failed", error=str(e), session_id=session_id)
            return RunResult(
                latency_ms=int((time.time() - session_start_time) * 1000),
                error=str(e),
                warnings=config_warnings,
            )
        finally:
            # Langfuse 事件后台批量上报，run 结束主动 flush（同步 HTTP，放线程池避免阻塞 loop）
            if lf_handler is not None:
                try:
                    await asyncio.to_thread(flush_langfuse)
                except Exception as flush_error:
                    logger.debug("langfuse_flush_skipped", error=str(flush_error))

    async def get_response(
        self,
        messages: list[Message],
        session_id: str,
        user_id: Optional[str] = None,
        username: Optional[str] = None,
        agent_id: Optional[str] = None,
    ) -> list[Message]:
        """从大模型获取响应（平台默认 chatbot 路径，保持历史行为等价）。

        参数：
            messages (list[Message])：发送给大模型的消息。
            session_id (str)：对话会话 ID。
            user_id (Optional[str])：用户 ID。
            username (Optional[str])：用户显示名称。
            agent_id (Optional[str])：Agent ID。

        返回：
            list[Message]：大模型返回的响应。
        """
        result = await self.run(
            messages,
            session_id,
            config=None,
            user_id=user_id,
            username=username,
            agent_id=agent_id,
        )
        if result.error:
            raise Exception(result.error)
        return [Message(role=m["role"], content=m["content"]) for m in result.messages]

    async def get_stream_response(
        self,
        messages: list[Message],
        session_id: str,
        user_id: Optional[str] = None,
        username: Optional[str] = None,
        agent_config: Optional[AgentConfig] = None,
    ) -> AsyncGenerator[str, None]:
        """从大模型获取流式响应。

        参数：
            messages (list[Message])：发送给大模型的消息。
            session_id (str)：对话会话 ID。
            user_id (Optional[str])：用户 ID。
            username (Optional[str])：用户显示名称。
            agent_config (Optional[AgentConfig])：Agent 运行配置；None 为默认路径。

        输出：
            str：大模型响应的逐词内容。
        """
        # Langfuse：流式同样一次 run 一个 handler
        lf_handler = make_callback_handler()
        stream_metadata = self._build_run_metadata(
            session_id, user_id, username, None, agent_config
        )
        stream_metadata.update(
            trace_metadata(
                trace_name="agent-run-stream" if agent_config is not None else "chatbot-stream",
                session_id=session_id,
                user_id=user_id,
                tags=["agent-runtime", "stream"] if agent_config is not None else ["chatbot", "stream"],
                username=username,
                agent_model=agent_config.model_name if agent_config is not None else None,
            )
        )
        config = {
            "configurable": {"thread_id": session_id},
            "callbacks": [lf_handler] if lf_handler is not None else [],
            "metadata": stream_metadata,
        }
        if self._graph is None:
            self._graph = await self.create_graph()

        try:
            # 并发执行状态检查与记忆搜索，节省 200-500ms
            state, relevant_memory = await asyncio.gather(
                self._graph.aget_state(config),
                memory_service.search(user_id, messages[-1].content),
            )

            if state.next:
                logger.info("resuming_interrupted_graph_stream", session_id=session_id, next_nodes=state.next)
                graph_input = Command(resume=messages[-1].content)
            else:
                # RAG 检索由图内 retrieve_knowledge 节点统一处理（非流式/流式一致）
                relevant_memory = relevant_memory or "未找到相关记忆。"
                graph_input = {"messages": dump_messages(messages), "long_term_memory": relevant_memory}

            async for token, _ in self._graph.astream(
                graph_input,
                config,
                stream_mode="messages",
            ):
                if not isinstance(token, (AIMessage, AIMessageChunk)):
                    continue

                text = extract_text_content(token.content)
                if text:
                    yield text

            # 流式输出结束后，检查中断或更新记忆
            state = await self._graph.aget_state(config)
            if state.next:
                interrupt_value = state.tasks[0].interrupts[0].value if state.tasks else "等待输入。"
                logger.info("graph_interrupted_stream", session_id=session_id, interrupt_value=str(interrupt_value))
                yield str(interrupt_value)
            elif state.values and "messages" in state.values:
                asyncio.create_task(
                    memory_service.add(
                        user_id, convert_to_openai_messages(state.values["messages"]), config["metadata"]
                    )
                )
        except GraphInterrupt:
            state = await self._graph.aget_state(config)
            interrupt_value = state.tasks[0].interrupts[0].value if state.tasks else "等待输入。"
            logger.info("graph_interrupted_stream", session_id=session_id, interrupt_value=str(interrupt_value))
            yield str(interrupt_value)
        except Exception as stream_error:
            logger.exception("stream_processing_failed", error=str(stream_error), session_id=session_id)
            raise stream_error
        finally:
            if lf_handler is not None:
                try:
                    await asyncio.to_thread(flush_langfuse)
                except Exception as flush_error:
                    logger.debug("langfuse_flush_skipped", error=str(flush_error))

    async def get_chat_history(self, session_id: str) -> list[Message]:
        """获取指定会话 ID 的聊天历史。

        参数：
            session_id (str)：对话会话 ID。

        返回：
            list[Message]：聊天历史记录。
        """
        if self._graph is None:
            self._graph = await self.create_graph()

        state: StateSnapshot = await self._graph.aget_state(config={"configurable": {"thread_id": session_id}})
        return self.__process_messages(state.values["messages"]) if state.values else []

    def __process_messages(self, messages: list[BaseMessage]) -> list[Message]:
        openai_style_messages = convert_to_openai_messages(messages)
        # 只保留助手和用户消息
        return [
            Message(role=message["role"], content=str(message["content"]))
            for message in openai_style_messages
            if message["role"] in ["assistant", "user"] and message["content"]
        ]

    async def clear_chat_history(self, session_id: str) -> None:
        """清空指定会话 ID 的所有聊天历史。

        参数：
            session_id：要清空历史的会话 ID。

        异常：
            Exception：清空聊天历史失败时抛出。
        """
        try:
            # 确保连接池在当前事件循环中已初始化
            conn_pool = await self._get_connection_pool()

            # 在一次管道中批量执行所有删除操作
            async with conn_pool.connection() as conn:
                async with conn.pipeline():
                    for table in settings.CHECKPOINT_TABLES:
                        await conn.execute(f"DELETE FROM {table} WHERE thread_id = %s", (session_id,))
                logger.info(
                    "checkpoint_tables_cleared_for_session",
                    tables=settings.CHECKPOINT_TABLES,
                    session_id=session_id,
                )

        except Exception as e:
            logger.error(
                "clear_chat_history_operation_failed",
                session_id=session_id,
                error=str(e),
            )
            raise