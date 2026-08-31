"""
条件表达式求值。

为什么不用 eval()：表达式是用户在前端配置面板里填的，直接 eval 等于把服务器
权限交出去。这里用 ast 白名单解析，只允许常量、比较、布尔运算、四则运算和几个
内置函数，其它语法（属性访问、下标、import、lambda…）一律拒绝。

用法：先把模板里的 {{变量}} 用 Context.render_expression 渲染成字面量，
再把得到的纯字面量表达式交给 evaluate 求值。
"""

from __future__ import annotations

import ast
import operator
from typing import Any


class UnsafeExpressionError(ValueError):
    """表达式包含不允许的语法。"""


_BIN_OPS: dict[type, Any] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Mod: operator.mod,
}

_CMP_OPS: dict[type, Any] = {
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
    ast.In: lambda a, b: a in b,
    ast.NotIn: lambda a, b: a not in b,
    ast.Is: operator.is_,
    ast.IsNot: operator.is_not,
}

_FUNCS: dict[str, Any] = {
    "len": len,
    "str": str,
    "int": int,
    "float": float,
    "bool": bool,
    "abs": abs,
    "round": round,
}


def evaluate(expression: str) -> bool:
    """求值一个字面量表达式，返回布尔结果。非法语法抛 UnsafeExpressionError。"""
    if not expression.strip():
        raise UnsafeExpressionError("表达式为空")
    tree = ast.parse(expression, mode="eval")
    return bool(_eval(tree.body))


def _eval(node: ast.AST) -> Any:
    if isinstance(node, ast.Constant):
        return node.value

    if isinstance(node, ast.List):
        return [_eval(e) for e in node.elts]

    if isinstance(node, ast.Tuple):
        return tuple(_eval(e) for e in node.elts)

    if isinstance(node, ast.Set):
        return {_eval(e) for e in node.elts}

    if isinstance(node, ast.Dict):
        return {_eval(k): _eval(v) for k, v in zip(node.keys, node.values)}

    if isinstance(node, ast.BinOp):
        op = _BIN_OPS.get(type(node.op))
        if op is None:
            raise UnsafeExpressionError(f"不支持的运算符: {type(node.op).__name__}")
        return op(_eval(node.left), _eval(node.right))

    if isinstance(node, ast.UnaryOp):
        if isinstance(node.op, ast.Not):
            return not _eval(node.operand)
        if isinstance(node.op, ast.USub):
            return -_eval(node.operand)
        raise UnsafeExpressionError(f"不支持的运算符: {type(node.op).__name__}")

    if isinstance(node, ast.BoolOp):
        values = [_eval(v) for v in node.values]
        if isinstance(node.op, ast.And):
            return all(values)
        return any(values)

    if isinstance(node, ast.Compare):
        left = _eval(node.left)
        for op, comparator in zip(node.ops, node.comparators):
            fn = _CMP_OPS.get(type(op))
            if fn is None:
                raise UnsafeExpressionError(f"不支持的比较符: {type(op).__name__}")
            right = _eval(comparator)
            if not fn(left, right):
                return False
            left = right
        return True

    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name):
            raise UnsafeExpressionError("只允许调用白名单内置函数")
        fn = _FUNCS.get(node.func.id)
        if fn is None:
            raise UnsafeExpressionError(f"不允许调用函数: {node.func.id}")
        if node.keywords:
            raise UnsafeExpressionError("不支持关键字参数")
        return fn(*[_eval(a) for a in node.args])

    if isinstance(node, ast.Name):
        raise UnsafeExpressionError(
            f"表达式里出现未渲染的变量 {node.id}，请确认已调用 render_expression"
        )

    if isinstance(node, ast.Attribute):
        raise UnsafeExpressionError("不允许属性访问")

    if isinstance(node, ast.Subscript):
        raise UnsafeExpressionError("不允许下标访问")

    raise UnsafeExpressionError(f"不支持的语法: {type(node).__name__}")
