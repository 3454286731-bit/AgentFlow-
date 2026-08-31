"""
节点基类与注册表。

新增一种节点类型只需要三步：
1. 在 core/models.py 的 NodeType 里加枚举值，并配一个 Config 模型 + 注册进 CONFIG_REGISTRY
2. 写一个 BaseNode 子类，实现 async run
3. 用 @register 装饰，引擎自动就能调度它
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from backend.core.models import Context, Node, NodeType


class NodeExecutionError(RuntimeError):
    """节点执行失败。"""

    def __init__(self, node_id: str, message: str):
        self.node_id = node_id
        super().__init__(f"节点 {node_id} 执行失败: {message}")


class BaseNode(ABC):
    node_type: NodeType

    @abstractmethod
    async def run(self, node: Node, ctx: Context) -> Any:
        """
        执行节点并返回输出。

        约定返回值统一是 dict 且至少含 output 字段，
        这样下游一律用 {{node_id.output}} 引用，不用关心节点类型。
        """


NODE_REGISTRY: dict[NodeType, type[BaseNode]] = {}


def register(cls: type[BaseNode]) -> type[BaseNode]:
    NODE_REGISTRY[cls.node_type] = cls
    return cls


def get_handler(node_type: NodeType) -> BaseNode:
    if node_type not in NODE_REGISTRY:
        raise NotImplementedError(
            f"节点类型 {node_type.value} 还没有实现，已支持：{[t.value for t in NODE_REGISTRY]}"
        )
    return NODE_REGISTRY[node_type]()
