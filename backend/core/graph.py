"""
DAG 图算法：拓扑排序、环检测、分层批次、可达性分析。

放在 core 层的原因：环检测属于工作流的结构合法性校验，是数据模型的一部分，
保存时就该拦住，不能等到执行时才炸。执行器只用到分层批次。

MVP 明确不支持环（循环节点放 v2），所以这里的职责是：
1. 有环就报错，并把环路径指出来，别让用户对着画布猜哪里连错了。
2. 把图切成一层层的批次，同一批次内的节点互不依赖，可以并发跑。
"""

from __future__ import annotations

from collections import deque

Adjacency = dict[str, list[str]]


class CyclicGraphError(ValueError):
    """工作流里存在环。"""

    def __init__(self, cycle: list[str]):
        self.cycle = cycle
        path = " -> ".join(cycle)
        super().__init__(f"工作流存在环，无法执行（MVP 不支持循环节点）：{path}")


def normalize(adj: Adjacency) -> dict[str, set[str]]:
    """
    规范化邻接表：补齐只作为终点出现的节点，并对出边去重。

    去重这一步不能省：条件分支的两个出口可能连到同一个下游节点，
    那样邻接表里会有两条相同的边，入度被算成 2，拓扑排序就永远剥不完。
    """
    clean: dict[str, set[str]] = {node: set() for node in adj}
    for node, targets in adj.items():
        for target in targets:
            clean.setdefault(target, set())
            clean[node].add(target)
    return clean


def find_cycle(adj: Adjacency) -> list[str] | None:
    """DFS 三色标记找环。返回环路径（首尾同一节点），无环返回 None。"""
    clean = normalize(adj)
    WHITE, GRAY, BLACK = 0, 1, 2
    color: dict[str, int] = {n: WHITE for n in clean}
    stack: list[str] = []

    def dfs(node: str) -> list[str] | None:
        color[node] = GRAY
        stack.append(node)
        for nxt in clean[node]:
            if color.get(nxt, WHITE) == GRAY:
                return stack[stack.index(nxt):] + [nxt]
            if color.get(nxt, WHITE) == WHITE:
                found = dfs(nxt)
                if found:
                    return found
        stack.pop()
        color[node] = BLACK
        return None

    for node in clean:
        if color[node] == WHITE:
            found = dfs(node)
            if found:
                return found
    return None


def topological_order(adj: Adjacency) -> list[str]:
    """Kahn 算法求拓扑序。有环抛 CyclicGraphError。"""
    clean = normalize(adj)
    indegree: dict[str, int] = {n: 0 for n in clean}
    for node, targets in clean.items():
        for target in targets:
            indegree[target] += 1

    queue = deque(sorted(n for n in clean if indegree[n] == 0))
    order: list[str] = []
    while queue:
        node = queue.popleft()
        order.append(node)
        for target in sorted(clean[node]):
            indegree[target] -= 1
            if indegree[target] == 0:
                queue.append(target)

    if len(order) != len(clean):
        cycle = find_cycle(adj) or ["?"]
        raise CyclicGraphError(cycle)
    return order


def reachable_from(adj: Adjacency, start: str) -> set[str]:
    """从 start 出发能到达的所有节点（含自身）。用来剔除没被连上的孤立节点。"""
    clean = normalize(adj)
    if start not in clean:
        return set()
    seen: set[str] = {start}
    queue = deque([start])
    while queue:
        node = queue.popleft()
        for target in clean[node]:
            if target not in seen:
                seen.add(target)
                queue.append(target)
    return seen


def layered_batches(adj: Adjacency, root: str | None = None) -> list[list[str]]:
    """
    把图切成分层批次，同批次内节点互不依赖，可并发执行。

    root 给定时，只保留从 root 可达的节点——画布上没连线的孤立节点
    会被自动排除，不会被执行器捞进来。

    返回示例：[['start_1'], ['llm_1'], ['cond_1'], ['end_1']]
    """
    clean = normalize(adj)
    if not clean:
        return []

    if root is not None:
        keep = reachable_from(clean, root)
        clean = {n: {t for t in ts if t in keep} for n, ts in clean.items() if n in keep}
        if not clean:
            return []

    indegree: dict[str, int] = {n: 0 for n in clean}
    for node, targets in clean.items():
        for target in targets:
            indegree[target] += 1

    current = sorted(n for n in clean if indegree[n] == 0)
    batches: list[list[str]] = []
    processed = 0

    while current:
        batches.append(current)
        processed += len(current)
        nxt: list[str] = []
        for node in current:
            for target in sorted(clean[node]):
                indegree[target] -= 1
                if indegree[target] == 0:
                    nxt.append(target)
        current = sorted(nxt)

    if processed != len(clean):
        cycle = find_cycle(adj) or ["?"]
        raise CyclicGraphError(cycle)
    return batches
