"""
core 层：纯数据结构与算法，不依赖网络、不依赖数据库。

- graph.py     图算法（分层 / 环检测 / 可达性）
- expr.py      安全的条件表达式求值（不用 eval）
- models.py    工作流数据模型与执行期结构
- providers.py 大模型适配层
"""

from .expr import UnsafeExpressionError, evaluate
from .graph import (
    CyclicGraphError,
    find_cycle,
    layered_batches,
    normalize,
    reachable_from,
    topological_order,
)
from .models import (
    Branch,
    ConditionConfig,
    CONFIG_REGISTRY,
    Context,
    Edge,
    EndConfig,
    ExecutionRecord,
    HTTPConfig,
    LLMConfig,
    Node,
    NodeResult,
    NodeStatus,
    NodeType,
    Position,
    StartConfig,
    Workflow,
    WorkflowStatus,
)
from .providers import (
    get_provider,
    LLMProvider,
    LLMResponse,
    MockLLMProvider,
    OpenAIProvider,
    PROVIDER_REGISTRY,
)

__all__ = [
    "Branch",
    "ConditionConfig",
    "CONFIG_REGISTRY",
    "Context",
    "CyclicGraphError",
    "Edge",
    "EndConfig",
    "evaluate",
    "ExecutionRecord",
    "find_cycle",
    "get_provider",
    "HTTPConfig",
    "layered_batches",
    "LLMConfig",
    "LLMProvider",
    "LLMResponse",
    "MockLLMProvider",
    "Node",
    "NodeResult",
    "NodeStatus",
    "NodeType",
    "normalize",
    "OpenAIProvider",
    "Position",
    "PROVIDER_REGISTRY",
    "reachable_from",
    "StartConfig",
    "topological_order",
    "UnsafeExpressionError",
    "Workflow",
    "WorkflowStatus",
]
