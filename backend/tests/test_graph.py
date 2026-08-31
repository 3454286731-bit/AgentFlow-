"""图算法测试。分层调度是并发执行的基础，这里的每个用例都是真实会遇到的图。"""

import pytest

from backend.core.graph import (
    CyclicGraphError,
    find_cycle,
    layered_batches,
    normalize,
    reachable_from,
    topological_order,
)


# ---------------------------------------------------------------- 分层

def test_linear_graph_batches():
    adj = {"a": ["b"], "b": ["c"], "c": []}
    assert layered_batches(adj) == [["a"], ["b"], ["c"]]


def test_diamond_graph_enables_concurrency():
    """菱形图：b 和 c 互不依赖，必须落在同一批次里才能并发。"""
    adj = {"a": ["b", "c"], "b": ["d"], "c": ["d"], "d": []}
    batches = layered_batches(adj)
    assert batches == [["a"], ["b", "c"], ["d"]]


def test_duplicate_edges_are_deduplicated():
    """条件分支两个出口连到同一个节点时，入度不能被重复计算。"""
    adj = {"a": ["b", "b"], "b": []}
    assert normalize(adj) == {"a": {"b"}, "b": set()}
    assert layered_batches(adj) == [["a"], ["b"]]


def test_root_filters_unreachable_nodes():
    """画布上没连线的孤立节点不应被执行器捞进来。"""
    adj = {"a": ["b"], "b": [], "orphan": []}
    assert layered_batches(adj, root="a") == [["a"], ["b"]]
    assert layered_batches(adj) == [["a", "orphan"], ["b"]]


def test_empty_graph():
    assert layered_batches({}) == []


# ---------------------------------------------------------------- 环检测

def test_cycle_is_detected():
    adj = {"a": ["b"], "b": ["c"], "c": ["a"]}
    cycle = find_cycle(adj)
    assert cycle is not None
    assert cycle[0] == cycle[-1]
    assert set(cycle) == {"a", "b", "c"}


def test_self_loop_is_detected():
    assert find_cycle({"a": ["a"]}) is not None


def test_acyclic_graph_has_no_cycle():
    assert find_cycle({"a": ["b"], "b": ["c"], "c": []}) is None


def test_layered_batches_raises_on_cycle():
    adj = {"a": ["b"], "b": ["a"]}
    with pytest.raises(CyclicGraphError, match="存在环"):
        layered_batches(adj)


def test_topological_order_raises_on_cycle():
    with pytest.raises(CyclicGraphError):
        topological_order({"a": ["b"], "b": ["a"]})


def test_topological_order_respects_dependencies():
    order = topological_order({"a": ["b", "c"], "b": ["d"], "c": ["d"], "d": []})
    assert order.index("a") < order.index("b") < order.index("d")
    assert order.index("a") < order.index("c") < order.index("d")


# ---------------------------------------------------------------- 可达性

def test_reachable_from_includes_self():
    assert reachable_from({"a": []}, "a") == {"a"}


def test_reachable_from_unknown_start():
    assert reachable_from({"a": []}, "ghost") == set()
