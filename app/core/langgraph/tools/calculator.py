"""基于 ast 白名单的安全算术计算器工具。

仅支持数字、四则/整除/取模/幂运算、括号、数学常量与少量白名单函数；
不执行任意 Python 表达式，禁止 import、属性访问与未知函数调用。
"""

import ast
import math
import operator
from typing import Union

from langchain_core.tools import tool

Number = Union[int, float]

_BIN_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_UNARY_OPS = {ast.UAdd: operator.pos, ast.USub: operator.neg}
_CONSTANTS = {"pi": math.pi, "tau": math.tau, "e": math.e}
_FUNCTIONS = {
    "abs": abs,
    "round": round,
    "min": min,
    "max": max,
    "pow": pow,
    "sqrt": math.sqrt,
    "log": math.log,
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
}
# 防 9**9**9 之类指数爆炸
_MAX_POWER = 10_000


def _eval_node(node: ast.AST) -> Number:
    """递归白名单求值；遇到任何非白名单节点直接拒绝。"""
    if isinstance(node, ast.Expression):
        return _eval_node(node.body)
    if (
        isinstance(node, ast.Constant)
        and isinstance(node.value, (int, float))
        and not isinstance(node.value, bool)
    ):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _BIN_OPS:
        left, right = _eval_node(node.left), _eval_node(node.right)
        if isinstance(node.op, ast.Pow) and abs(right) > _MAX_POWER:
            raise ValueError(f"指数过大（上限 {_MAX_POWER}）")
        return _BIN_OPS[type(node.op)](left, right)
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY_OPS:
        return _UNARY_OPS[type(node.op)](_eval_node(node.operand))
    if isinstance(node, ast.Name) and node.id in _CONSTANTS:
        return _CONSTANTS[node.id]
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in _FUNCTIONS
        and not node.keywords
    ):
        args = [_eval_node(arg) for arg in node.args]
        return _FUNCTIONS[node.func.id](*args)
    raise ValueError("表达式包含不支持的语法或未白名单的函数/名称")


def _preprocess(expression: str) -> str:
    """常见符号归一化：全角运算符与 ^ 幂符号。"""
    return (
        expression.replace("×", "*")
        .replace("÷", "/")
        .replace("＋", "+")
        .replace("－", "-")
        .replace("^", "**")
        .strip()
    )


def _format(result: Number) -> str:
    """整数化浮点结果（5.0 → "5"），并拒绝 NaN/Inf。"""
    if isinstance(result, float):
        if math.isnan(result) or math.isinf(result):
            raise ValueError("计算结果不是有限数")
        if result.is_integer():
            return str(int(result))
        return f"{result:.10g}"
    return str(result)


@tool
def calculator(expression: str) -> str:
    """Evaluate an arithmetic expression and return the numeric result.

    Use this tool whenever a calculation is needed instead of computing
    mentally. Supports + - * / // % **, parentheses, constants (pi, e) and
    functions: abs, round, min, max, pow, sqrt, log, sin, cos, tan.

    Args:
        expression: 算术表达式，例如 "(3 + 5) * 12 / 2" 或 "sqrt(144)"。

    Returns:
        str: 计算结果；非法表达式返回错误说明。
    """
    try:
        tree = ast.parse(_preprocess(expression), mode="eval")
        return _format(_eval_node(tree))
    except ZeroDivisionError:
        return "错误：除数不能为零。"
    except SyntaxError:
        return "错误：表达式语法不正确。"
    except (ValueError, TypeError, OverflowError) as exc:
        return f"错误：无法计算该表达式（{exc}）。"
