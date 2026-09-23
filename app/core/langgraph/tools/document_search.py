"""知识库检索工具：封装 RAG 服务的语义检索，供 Agent 主动查文档。

Agent 绑定知识库后（阶段 4），graph 会自动把本工具加入该 Agent 的
可用工具集；不传 kb_id 时默认检索其绑定的全部知识库。
"""

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool


@tool
def document_search(
    query: str,
    # 注意：不要用 Optional[str]=None——Pydantic 会生成 anyOf schema，
    # 部分 LLM 供应商的受限解码（grammar）不支持，会报 400
    kb_id: str = "",
    config: RunnableConfig = None,
) -> str:
    """Search the knowledge-base documents bound to this agent and return relevant passages.

    Use this tool to look up facts from documents (e.g. company policies,
    product manuals) before answering, or whenever the user asks to search
    documents. If kb_id is omitted, all knowledge bases bound to the current
    agent are searched.

    Args:
        query: 检索问题或关键词（语义检索）。
        kb_id: 可选；指定知识库 ID，传空串则检索当前 Agent 绑定的全部知识库。

    Returns:
        str: 命中的文档片段（含来源文件名与相关度）；无命中或失败时返回提示。
    """
    from app.services.rag_service import rag_service

    metadata = (config or {}).get("metadata", {}) or {}
    bound_kb_ids = metadata.get("agent_kb_ids") or []

    if kb_id:
        kb_id = str(kb_id).strip()
        # 已绑定知识库的 Agent 只能检索其绑定的库
        if bound_kb_ids and kb_id not in bound_kb_ids:
            return f"错误：知识库 {kb_id} 未绑定到当前 Agent，无权检索。"
        kb_ids = [kb_id]
    elif bound_kb_ids:
        kb_ids = bound_kb_ids
    else:
        return "错误：当前 Agent 未绑定知识库，无法检索文档。"

    try:
        docs = rag_service.retrieve(kb_ids, query)
    except Exception as exc:  # 检索失败返回提示，不中断对话
        return f"错误：知识库检索失败（{exc}）。"

    if not docs:
        return "未检索到相关文档内容。"

    blocks = [
        f"[{idx + 1}] 来源：{d.get('filename', 'unknown')}"
        f"（相关度 {d.get('score')}）\n{d['content']}"
        for idx, d in enumerate(docs)
    ]
    return "\n\n".join(blocks)
