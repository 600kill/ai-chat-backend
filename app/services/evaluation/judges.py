"""评测判分器。

- Tool 判分：三档规则——exact（工具名+关键参数全对）/ partial（工具名对+部分关键参数对）
  / miss（工具名错或未调用）。
- Answer 判分：LLM-as-Judge，模型从 settings 读（JUDGE_MODEL/JUDGE_BASE_URL/JUDGE_API_KEY，
  走项目已配的 LLM 网关，不硬绑任何云厂商），输出三维分数 + 理由。
- RAG 判分：expected_document_ids 命中率（recall）。

注意：沿用项目风格，同步实现（RQ worker 进程内直接调用）。
"""

import json
import re
from typing import Any, Optional

from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI

from app.core.config import settings
from app.core.logging import logger

# 三档枚举与数值映射
TOOL_EXACT, TOOL_PARTIAL, TOOL_MISS = "exact", "partial", "miss"
TOOL_SCORE = {TOOL_EXACT: 1.0, TOOL_PARTIAL: 0.5, TOOL_MISS: 0.0}


def judge_tool(
    expected_tool: Optional[str],
    expected_arguments: Optional[dict],
    actual_tool_calls: Optional[list],
) -> dict:
    """三档工具判分。

    Args:
        expected_tool: 期望工具名（function_name）
        expected_arguments: 期望关键参数（dict，子集匹配）
        actual_tool_calls: 实际工具调用 [{name, args}, ...]
    Returns:
        {"tool": exact|partial|miss, "tool_score": 0|0.5|1, "detail": str}
    """
    calls = actual_tool_calls or []
    if not expected_tool:
        return {"tool": TOOL_EXACT, "tool_score": 1.0, "detail": "该用例未要求工具调用"}

    matched = [c for c in calls if c.get("name") == expected_tool]
    if not matched:
        called_names = [c.get("name") for c in calls]
        detail = f"未调用期望工具 {expected_tool}" if not calls else f"调用了 {called_names}，期望 {expected_tool}"
        return {"tool": TOOL_MISS, "tool_score": 0.0, "detail": detail}

    expected = expected_arguments or {}
    if not expected:
        return {"tool": TOOL_EXACT, "tool_score": 1.0, "detail": f"工具名匹配（未要求参数）"}

    best = TOOL_MISS
    best_detail = ""
    for call in matched:
        args = call.get("args") or {}
        hit = sum(1 for k, v in expected.items() if k in args and str(args[k]) == str(v))
        if hit == len(expected):
            best, best_detail = TOOL_EXACT, "工具名与关键参数全部匹配"
            break
        if hit > 0:
            best, best_detail = TOOL_PARTIAL, f"工具名匹配，关键参数命中 {hit}/{len(expected)}"
        elif best == TOOL_MISS:
            best_detail = "工具名匹配，但关键参数全部未命中"
    if best == TOOL_MISS:
        return {"tool": TOOL_MISS, "tool_score": 0.0, "detail": best_detail}
    return {"tool": best, "tool_score": TOOL_SCORE[best], "detail": best_detail}


def judge_rag(
    expected_document_ids: Optional[list],
    actual_document_ids: Optional[list],
) -> dict:
    """RAG 命中率（recall）：期望命中的文档出现在检索结果中的比例。"""
    expected = expected_document_ids or []
    if not expected:
        return {"rag_recall": 1.0, "detail": "该用例未要求文档命中"}
    actual = set(actual_document_ids or [])
    hit = sum(1 for d in expected if d in actual)
    recall = hit / len(expected)
    return {"rag_recall": round(recall, 4), "detail": f"命中 {hit}/{len(expected)} 篇期望文档"}


_JUDGE_PROMPT = """你是严格的评测 Judge。根据「参考答案」评估「被测回答」的质量，输出三个维度分数（0-10 整数）与理由。

评分维度：
- factuality：事实准确性——回答与参考答案在关键事实上是否一致（错误/编造事实扣分）。
- instruction：指令遵循——是否按要求回答（如格式、来源引用、限定范围）。
- completeness：完整性——参考答案中的要点是否覆盖。

评测问题：{question}
参考答案：{expected}
被测回答：{actual}
可用上下文（RAG 检索片段，供参考）：{context}

只输出 JSON，不要多余文字：
{{"factuality": <0-10>, "instruction": <0-10>, "completeness": <0-10>, "rationale": "<50字内理由>"}}"""


def judge_answer(
    question: str,
    expected_answer: Optional[str],
    agent_answer: Optional[str],
    context: Optional[str] = None,
) -> dict:
    """LLM-as-Judge 三维打分。Judge 失败时返回 None 分数（不阻断评测流程）。

    Judge 模型从 settings 读（JUDGE_MODEL/JUDGE_BASE_URL/JUDGE_API_KEY），走项目 LLM 网关。
    """
    llm = ChatOpenAI(
        model=settings.JUDGE_MODEL,
        api_key=settings.JUDGE_API_KEY,
        base_url=settings.JUDGE_BASE_URL or None,
        temperature=0,
        timeout=120,
        max_retries=2,
    )
    prompt = _JUDGE_PROMPT.format(
        question=question,
        expected=expected_answer or "(无参考答案，按常识判断)",
        actual=agent_answer or "(空回答)",
        context=(context or "无")[:2000],
    )
    try:
        resp = llm.invoke([HumanMessage(content=prompt)])
        text = resp.content if isinstance(resp.content, str) else str(resp.content)
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            raise ValueError(f"Judge 输出不含 JSON: {text[:200]}")
        scores = json.loads(match.group(0))
        result = {
            "factuality": int(scores.get("factuality", 0)),
            "instruction": int(scores.get("instruction", 0)),
            "completeness": int(scores.get("completeness", 0)),
            "rationale": str(scores.get("rationale", ""))[:200],
        }
        result["answer_avg"] = round(
            (result["factuality"] + result["instruction"] + result["completeness"]) / 30.0, 4
        )
        return result
    except Exception as e:
        logger.warning("judge_answer_failed", error=str(e), judge_model=settings.JUDGE_MODEL)
        return {
            "factuality": None,
            "instruction": None,
            "completeness": None,
            "answer_avg": None,
            "rationale": f"Judge 调用失败：{str(e)[:150]}",
        }


def compute_overall(case_type: str, tool_result: dict, rag_result: dict, answer_result: dict) -> Optional[float]:
    """综合分：answer 维度与工具/RAG 维度加权。"""
    answer_avg = answer_result.get("answer_avg")
    parts: list[tuple[float, float]] = []  # (weight, score)
    if case_type == "answer":
        if answer_avg is not None:
            parts.append((1.0, answer_avg))
    elif case_type == "tool":
        parts.append((0.5, tool_result.get("tool_score", 0.0)))
        if answer_avg is not None:
            parts.append((0.5, answer_avg))
        else:
            parts.append((0.5, 0.0))
    elif case_type == "rag":
        parts.append((0.5, rag_result.get("rag_recall", 0.0)))
        if answer_avg is not None:
            parts.append((0.5, answer_avg))
        else:
            parts.append((0.5, 0.0))
    if not parts:
        return None
    weight_sum = sum(w for w, _ in parts)
    return round(sum(w * s for w, s in parts) / weight_sum, 4)


def build_judge_payload(case: Any, result: Any, rag_contexts: Optional[list] = None) -> tuple[dict, Optional[float]]:
    """对单 case 结果执行全部判分并合并 scores。

    Args:
        case: EvaluationCase
        result: EvaluationCaseResult（含 agent_answer / actual_tool_calls / actual_document_ids）
        rag_contexts: runner 传入的检索片段文本列表（供 Judge 参考）
    """
    tool_result = judge_tool(
        getattr(case, "expected_tool", None),
        getattr(case, "expected_arguments", None),
        getattr(result, "actual_tool_calls", None),
    )
    rag_result = judge_rag(
        getattr(case, "expected_document_ids", None),
        getattr(result, "actual_document_ids", None),
    )
    answer_result = judge_answer(
        question=case.question,
        expected_answer=getattr(case, "expected_answer", None),
        agent_answer=getattr(result, "agent_answer", None),
        context="\n".join(str(c)[:300] for c in (rag_contexts or [])[:3]),
    )
    scores = {**answer_result, **tool_result, **rag_result}
    overall = compute_overall(case.type, tool_result, rag_result, answer_result)
    return scores, overall
