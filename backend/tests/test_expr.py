"""安全表达式求值测试。重点是验证 eval 能干的事这里都能拦住。"""

import pytest

from backend.core.expr import UnsafeExpressionError, evaluate


# ---------------------------------------------------------------- 正常求值

@pytest.mark.parametrize(
    "expr,expected",
    [
        ("1 > 0", True),
        ("10 <= 5", False),
        ("'abc' == 'abc'", True),
        ("len('冒泡排序') > 3", True),
        ("len('abc') > 5 or 2 > 1", True),
        ("not (1 > 2)", True),
        ("5 in [1, 2, 5]", True),
        ("abs(-3) == 3", True),
    ],
)
def test_valid_expressions(expr, expected):
    assert evaluate(expr) is expected


def test_chinese_string_repr():
    """render_expression 用 repr，中文字符串要能正常求值。"""
    assert evaluate("len('这是一段比较长的中文文本') > 5")


# ---------------------------------------------------------------- 安全拦截

@pytest.mark.parametrize(
    "expr",
    [
        "__import__('os').system('echo pwned')",
        "open('/etc/passwd').read()",
        "(1).__class__",
        "eval('1+1')",
        "exec('x=1')",
    ],
)
def test_dangerous_calls_rejected(expr):
    with pytest.raises(UnsafeExpressionError):
        evaluate(expr)


def test_attribute_access_rejected():
    with pytest.raises(UnsafeExpressionError, match="属性访问"):
        evaluate("'abc'.upper")


def test_subscript_rejected():
    with pytest.raises(UnsafeExpressionError, match="下标"):
        evaluate("{'a': 1}['a']")


def test_unrendered_variable_rejected():
    """漏渲染的变量会被拦下，避免静默按 NameError 处理。"""
    with pytest.raises(UnsafeExpressionError, match="未渲染"):
        evaluate("score > 60")


def test_undefined_function_rejected():
    with pytest.raises(UnsafeExpressionError, match="不允许调用函数"):
        evaluate("system('ls')")


def test_empty_expression_rejected():
    with pytest.raises(UnsafeExpressionError, match="为空"):
        evaluate("   ")


def test_syntax_error_surfaces():
    with pytest.raises(SyntaxError):
        evaluate("1 >")
