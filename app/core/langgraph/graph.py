"""这个文件包含 LangGraph 智能体/工作流，以及与大模型的交互逻辑。"""

import asyncio
from contextlib import asynccontextmanager
from typing import (
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
from psycopg_pool import ConnectionPool

from app.core.config import (
    Environment,
    settings,
)
from app.core.langgraph.tools import tools
from app.core.logging import logger
#from app.core.metrics import llm_inference_duration_seconds
#from app.core.observability import langfuse_callback_handler
from app.core.prompts import load_system_prompt
from app.schemas import (
    GraphState,
    Message,
)
from app.services.llm import llm_service
from app.services.memory import memory_service
from app.utils import (
    dump_messages,
    extract_text_content,
    prepare_messages,
    process_llm_response,
)


class _AsyncConnectionWrapper:
    """Windows 兼容的异步连接池包装器。

    使用 sync ConnectionPool + asyncio.to_thread 替代 AsyncConnectionPool，
    解决 psycopg3 async 在 Windows ProactorEventLoop 下的兼容性问题。
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


class _SyncConnectionWrapper:
    """将 sync 连接包装为 async 接口，供 AsyncPostgresSaver 使用。"""

    def __init__(self, conn):
        self._conn = conn

    def __getattr__(self, name):
        """将未包装的属性/方法透传到原始连接。"""
        return getattr(self._conn, name)

    async def execute(self, query, params=None, **kwargs):
        result = await asyncio.to_thread(self._conn.execute, query, params, **kwargs)
        return _SyncCursorWrapper(result) if result else result

    async def cursor(self, **kwargs):
        result = await asyncio.to_thread(self._conn.cursor, **kwargs)
        return _SyncCursorWrapper(result)

    @asynccontextmanager
    async def pipeline(self):
        with self._conn.pipeline():
            yield


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

    async def _chat(self, state: GraphState, config: RunnableConfig) -> Command:
        """处理聊天状态并生成响应。

        参数：
            state (GraphState)：当前对话状态。
            config (RunnableConfig)：当前调用的配置信息。

        返回：
            Command：包含更新后状态与下一个执行节点的指令对象。
        """
        # 获取当前大模型实例，用于指标统计
        current_llm = self.llm_service.get_llm()
        model_name = (
            current_llm.model_name
            if current_llm and hasattr(current_llm, "model_name")
            else settings.DEFAULT_LLM_MODEL
        )

        username = config.get("metadata", {}).get("username")
        SYSTEM_PROMPT = load_system_prompt(username=username, long_term_memory=state.long_term_memory)

        # 拼接系统提示词，准备消息
        messages = prepare_messages(state.messages, SYSTEM_PROMPT)

        try:
            # 使用自带自动重试与循环兜底的大模型服务
            response_message = await self.llm_service.call(dump_messages(messages))
            '''with llm_inference_duration_seconds.labels(model=model_name).time():
                response_message = await self.llm_service.call(dump_messages(messages))'''

            # 处理响应，解析结构化内容块
            response_message = process_llm_response(response_message)

            logger.info(
                "llm_response_generated",
                session_id=config["configurable"]["thread_id"],
                model=model_name,
                environment=settings.ENVIRONMENT.value,
            )

            # 根据是否存在工具调用，决定下一个节点
            if response_message.tool_calls:
                goto = "tool_call"
            else:
                goto = END

            return Command(update={"messages": [response_message]}, goto=goto)
        except Exception as e:
            logger.error(
                "llm_call_failed_all_models",
                session_id=config["configurable"]["thread_id"],
                error=str(e),
                environment=settings.ENVIRONMENT.value,
            )
            raise Exception(f"尝试所有模型后仍无法获取大模型响应：{str(e)}")

    # 定义工具节点
    async def _tool_call(self, state: GraphState) -> Command:
        """处理上一条消息中的工具调用。

        参数：
            state：包含消息与工具调用的当前智能体状态。

        返回：
            Command：包含更新后消息并路由回聊天节点的指令。
        """
        tool_calls = state.messages[-1].tool_calls

        async def _execute_tool(tool_call: dict) -> BaseMessage:
            tool_result = await self.tools_by_name[tool_call["name"]].ainvoke(tool_call["args"])
            # 如果是生成图表工具，直接返回包含图片的assistant消息
            # 不再走LLM二次生成，确保图片能正确展示
            if tool_call["name"] == "generate_chart":
                # 检查工具是否返回了错误信息（以"错误"开头）
                if isinstance(tool_result, str) and tool_result.startswith("错误"):
                    return AIMessage(content=tool_result)
                return AIMessage(
                    content=f"图表已生成：\n\n![chart](/api/v1/chatbot/image/{tool_result})"
                )
            return ToolMessage(
                content=tool_result,
                name=tool_call["name"],
                tool_call_id=tool_call["id"],
            )

        # 当有多个工具调用时，并发执行
        if len(tool_calls) == 1:
            outputs = [await _execute_tool(tool_calls[0])]
        else:
            outputs = list(await asyncio.gather(*[_execute_tool(tc) for tc in tool_calls]))

        # 检查是否所有输出都是AIMessage（图表生成），如果是则直接结束
        if all(isinstance(o, AIMessage) for o in outputs):
            return Command(update={"messages": outputs}, goto=END)

        return Command(update={"messages": outputs}, goto="chat")

    async def create_graph(self) -> Optional[CompiledStateGraph]:
        """创建并配置 LangGraph 工作流。

        返回：
            Optional[CompiledStateGraph]：配置好的 LangGraph 实例，初始化失败则返回 None
        """
        if self._graph is None:
            try:
                graph_builder = StateGraph(GraphState)
                graph_builder.add_node("chat", self._chat, ends=["tool_call", END])
                graph_builder.add_node("tool_call", self._tool_call, ends=["chat"])
                graph_builder.set_entry_point("chat")
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

    async def get_response(
        self,
        messages: list[Message],
        session_id: str,
        user_id: Optional[str] = None,
        username: Optional[str] = None,
    ) -> list[dict]:
        """从大模型获取响应。

        参数：
            messages (list[Message])：发送给大模型的消息。
            session_id (str)：对话会话 ID。
            user_id (Optional[str])：用户 ID。
            username (Optional[str])：用户显示名称。

        返回：
            list[dict]：大模型返回的响应。
        """
        if self._graph is None:
            self._graph = await self.create_graph()
        callbacks = []
        #callbacks = [langfuse_callback_handler] if settings.LANGFUSE_TRACING_ENABLED else []
        config = {
            "configurable": {"thread_id": session_id},
            "callbacks": callbacks,
            "metadata": {
                "user_id": user_id,
                "username": username,
                "session_id": session_id,
                "environment": settings.ENVIRONMENT.value,
                "debug": settings.DEBUG,
            },
        }

        try:
            # 并发执行状态检查与记忆搜索，节省 200-500ms
            state, relevant_memory = await asyncio.gather(
                self._graph.aget_state(config),
                memory_service.search(user_id, messages[-1].content),
            )

            if state.next:
                logger.info("resuming_interrupted_graph", session_id=session_id, next_nodes=state.next)
                response = await self._graph.ainvoke(
                    Command(resume=messages[-1].content),
                    config=config,
                )
            else:
                relevant_memory = relevant_memory or "未找到相关记忆。"
                response = await self._graph.ainvoke(
                    input={"messages": dump_messages(messages), "long_term_memory": relevant_memory},
                    config=config,
                )

            # 检查本次调用是否触发中断
            state = await self._graph.aget_state(config)
            if state.next:
                interrupt_value = state.tasks[0].interrupts[0].value if state.tasks else "等待输入。"
                logger.info("graph_interrupted", session_id=session_id, interrupt_value=str(interrupt_value))
                return [Message(role="assistant", content=str(interrupt_value))]

            asyncio.create_task(
                memory_service.add(user_id, convert_to_openai_messages(response["messages"]), config["metadata"])
            )
            return self.__process_messages(response["messages"])
        except GraphInterrupt:
            state = await self._graph.aget_state(config)
            interrupt_value = state.tasks[0].interrupts[0].value if state.tasks else "等待输入。"
            logger.info("graph_interrupted", session_id=session_id, interrupt_value=str(interrupt_value))
            return [Message(role="assistant", content=str(interrupt_value))]
        except Exception as e:
            logger.exception("get_response_failed", error=str(e), session_id=session_id)
            raise

    async def get_stream_response(
        self,
        messages: list[Message],
        session_id: str,
        user_id: Optional[str] = None,
        username: Optional[str] = None,
    ) -> AsyncGenerator[str, None]:
        """从大模型获取流式响应。

        参数：
            messages (list[Message])：发送给大模型的消息。
            session_id (str)：对话会话 ID。
            user_id (Optional[str])：用户 ID。
            username (Optional[str])：用户显示名称。

        输出：
            str：大模型响应的逐词内容。
        """
        callbacks = []
        #callbacks = [langfuse_callback_handler] if settings.LANGFUSE_TRACING_ENABLED else []
        config = {
            "configurable": {"thread_id": session_id},
            "callbacks": callbacks,
            "metadata": {
                "user_id": user_id,
                "username": username,
                "session_id": session_id,
                "environment": settings.ENVIRONMENT.value,
                "debug": settings.DEBUG,
            },
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