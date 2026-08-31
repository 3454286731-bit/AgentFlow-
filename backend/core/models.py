"""
工作流核心数据模型（第一周 · 第一步）

设计约定：
1. 工作流 = 一张有向图。Node 是点，Edge 是边。
2. MVP 只支持 DAG（无环图），环检测在 engine/dag.py 里做。
3. 节点间通过变量引用传递数据，语法 {{node_id.field}}，由 Context.render 解析。
4. 全部使用 Pydantic v2，可直接落库、可直接导出 JSON Schema 给前端生成配置表单。

为什么先写这一层：
后端所有模块（调度器、节点运行时、API、前端画布）都依赖这套结构。
它定不稳，后面每加一个功能都要回头改，是这个项目最容易返工的地方。
"""

from __future__ import annotations

import re
from datetime import datetime
from enum import Enum
from typing import Any, Literal
from uuid import uuid4

from pydantic import (
    BaseModel,
    computed_field,
    ConfigDict,
    Field,
    ValidationError,
    model_validator,
)

# 相对导入：graph 不依赖本模块，用它做环检测不会形成循环依赖
from .graph import CyclicGraphError, find_cycle


def short_id() -> str:
    """生成 8 位短 ID。够用且比 UUID 好看，日志里一眼能认。"""
    return uuid4().hex[:8]


# ---------------------------------------------------------------- 节点类型

class NodeType(str, Enum):
    """
    通用节点五类 + 教学场景专用三类。

    教学专用节点是本项目差异化的关键：市面上的工作流平台提供的都是通用节点，
    而智能出题、作业批改、学情分析是把教学业务抽象成节点，没有现成的标准实现。
    """
    START = "start"          # 入口，定义全局输入变量
    LLM = "llm"              # 调用大模型
    HTTP = "http"            # 调用外部接口（工具节点）
    CONDITION = "condition"  # 条件分支，多出口
    END = "end"              # 出口，定义最终输出

    QUESTION = "question"    # 教学：智能出题
    GRADING = "grading"      # 教学：作业批改
    ANALYTICS = "analytics"  # 教学：学情分析


class NodeStatus(str, Enum):
    """节点在一次执行中的状态机。"""
    PENDING = "pending"    # 等待调度
    RUNNING = "running"    # 执行中
    SUCCESS = "success"    # 成功
    FAILED = "failed"      # 失败
    SKIPPED = "skipped"    # 分支未命中，跳过


# ---------------------------------------------------------------- 画布位置

class Position(BaseModel):
    """前端画布坐标，后端不关心，只负责存。"""
    x: float = 0.0
    y: float = 0.0


# ---------------------------------------------------------------- 节点配置

class BaseNodeConfig(BaseModel):
    """所有节点配置的基类。禁止多余字段，防止前端传错参数静默失效。"""
    model_config = ConfigDict(extra="forbid")


class StartConfig(BaseNodeConfig):
    """入口节点：声明这个工作流需要哪些输入。"""
    inputs: dict[str, Any] = Field(
        default_factory=dict,
        description="输入变量名 -> 默认值，例：{'topic': 'Python 入门'}",
    )


class LLMConfig(BaseNodeConfig):
    """大模型节点：核心节点，prompt 里可以写 {{变量}}。"""
    provider: str = Field(default="openai", description="模型厂商，由适配层路由")
    model: str = Field(default="deepseek-chat")
    prompt: str = Field(description="提示词，支持 {{node_id.output}} 变量引用")
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: int = Field(default=1024, ge=1, le=32000)
    output_format: Literal["text", "json"] = "text"


class HTTPConfig(BaseNodeConfig):
    """HTTP 工具节点：让工作流能调外部世界。"""
    method: Literal["GET", "POST", "PUT", "DELETE"] = "POST"
    url: str = Field(description="支持 {{变量}} 模板")
    headers: dict[str, str] = Field(default_factory=dict)
    body: str = Field(default="", description="JSON 字符串，支持 {{变量}} 模板")
    timeout: int = Field(default=30, ge=1, le=300)


class Branch(BaseNodeConfig):
    """条件分支的一个出口。"""
    handle: str = Field(description="出口标识，对应 Edge.source_handle")
    label: str = Field(default="", description="画布上连线显示的文案")
    expression: str = Field(description="判断表达式，例：{{llm_1.score}} >= 60")


class ConditionConfig(BaseNodeConfig):
    """条件分支节点：按 expression 顺序匹配，命中即走，全不中走 default_handle。"""
    branches: list[Branch] = Field(default_factory=list, min_length=1)
    default_handle: str = Field(default="else", description="兜底出口")


class EndConfig(BaseNodeConfig):
    """出口节点：定义工作流最终返回什么。"""
    output_template: str = Field(
        default="", description="输出模板，例：最终结果：{{llm_1.output}}"
    )


# ------------------------------------------------ 教学场景专用节点配置

class QuestionConfig(BaseNodeConfig):
    """智能出题节点：按知识点、难度、题型批量生成题目。"""
    model: str = Field(default="deepseek-chat")
    knowledge_point: str = Field(description="知识点，支持 {{变量}} 引用")
    difficulty: Literal["easy", "medium", "hard"] = Field(
        default="medium", description="难度"
    )
    question_type: Literal["choice", "fill", "short", "program"] = Field(
        default="choice", description="题型：选择 / 填空 / 简答 / 编程"
    )
    count: int = Field(default=3, ge=1, le=20, description="生成题量")
    requirements: str = Field(default="", description="补充要求，如「结合生活实例」")
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)


class GradingConfig(BaseNodeConfig):
    """作业批改节点：按评分细则打分并给出旁批与改进建议。"""
    model: str = Field(default="deepseek-chat")
    answer: str = Field(description="学生作答内容，支持 {{变量}}")
    rubric: str = Field(description="评分细则，例：概念准确 40 分，步骤完整 60 分")
    reference: str = Field(default="", description="参考答案（可选）")
    max_score: int = Field(default=100, ge=1, le=1000, description="满分")
    temperature: float = Field(default=0.2, ge=0.0, le=2.0,
                               description="批改要稳定，温度默认偏低")


class AnalyticsConfig(BaseNodeConfig):
    """学情分析节点：从学习记录里提炼薄弱点与掌握度。"""
    model: str = Field(default="deepseek-chat")
    records: str = Field(description="学习记录，支持 {{变量}}，JSON 文本")
    dimension: Literal["knowledge", "skill", "progress"] = Field(
        default="knowledge", description="分析维度：知识点 / 能力 / 进度"
    )
    top_n: int = Field(default=3, ge=1, le=10, description="输出几个薄弱点")
    temperature: float = Field(default=0.3, ge=0.0, le=2.0)


CONFIG_REGISTRY: dict[NodeType, type[BaseNodeConfig]] = {
    NodeType.START: StartConfig,
    NodeType.LLM: LLMConfig,
    NodeType.HTTP: HTTPConfig,
    NodeType.CONDITION: ConditionConfig,
    NodeType.END: EndConfig,
    NodeType.QUESTION: QuestionConfig,
    NodeType.GRADING: GradingConfig,
    NodeType.ANALYTICS: AnalyticsConfig,
}


# ---------------------------------------------------------------- 图结构

class Node(BaseModel):
    id: str = Field(default_factory=short_id)
    type: NodeType
    name: str = Field(description="画布上显示的节点名")
    config: dict[str, Any] = Field(default_factory=dict)
    position: Position = Field(default_factory=Position)

    @property
    def config_model(self) -> BaseNodeConfig:
        """按节点类型把 config 字典转成强类型模型，顺便完成校验。"""
        return CONFIG_REGISTRY[self.type](**self.config)

    def validate_config(self) -> None:
        """显式校验配置。工作流保存时调用，把错误拦在入口。"""
        self.config_model


class Edge(BaseModel):
    id: str = Field(default_factory=short_id)
    source: str = Field(description="上游节点 id")
    target: str = Field(description="下游节点 id")
    source_handle: str | None = Field(
        default=None, description="上游出口标识；普通节点为 None，条件节点为分支 handle"
    )
    condition: str | None = Field(
        default=None, description="可选的边级条件，字符串表达式，为 None 表示无条件连通"
    )


class Workflow(BaseModel):
    """一张完整的工作流定义。存库时整体序列化成 JSON。"""
    id: str = Field(default_factory=short_id)
    name: str
    description: str = ""
    version: int = 1
    nodes: list[Node] = Field(default_factory=list)
    edges: list[Edge] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

    # ---- 图查询工具方法，engine 层全靠这几个 ----

    def get_node(self, node_id: str) -> Node:
        for n in self.nodes:
            if n.id == node_id:
                return n
        raise KeyError(f"节点不存在: {node_id}")

    def has_node(self, node_id: str) -> bool:
        return any(n.id == node_id for n in self.nodes)

    def outgoing(self, node_id: str) -> list[Edge]:
        return [e for e in self.edges if e.source == node_id]

    def incoming(self, node_id: str) -> list[Edge]:
        return [e for e in self.edges if e.target == node_id]

    @property
    def start_node(self) -> Node:
        for n in self.nodes:
            if n.type == NodeType.START:
                return n
        raise ValueError("工作流缺少 start 节点")

    def to_adjacency(self) -> dict[str, list[str]]:
        """转成邻接表，喂给 engine/dag.py 做拓扑排序。"""
        adj: dict[str, list[str]] = {n.id: [] for n in self.nodes}
        for e in self.edges:
            adj[e.source].append(e.target)
        return adj

    # ---- 校验：把非法结构挡在保存之前 ----

    @model_validator(mode="after")
    def _validate_graph(self) -> Workflow:
        # 1. 节点 id 唯一
        ids = [n.id for n in self.nodes]
        dup = {i for i in ids if ids.count(i) > 1}
        if dup:
            raise ValueError(f"节点 id 重复: {sorted(dup)}")

        # 2. 每个节点的 config 必须符合该类型的 schema
        for n in self.nodes:
            try:
                n.validate_config()
            except ValidationError as exc:
                raise ValueError(f"节点 {n.id}({n.type.value}) 配置不合法: {exc}") from exc

        # 3. 边的两端必须存在
        for e in self.edges:
            if not self.has_node(e.source):
                raise ValueError(f"边 {e.id} 的 source 不存在: {e.source}")
            if not self.has_node(e.target):
                raise ValueError(f"边 {e.id} 的 target 不存在: {e.target}")

        # 4. start 唯一，end 至少一个
        starts = [n for n in self.nodes if n.type == NodeType.START]
        if len(starts) != 1:
            raise ValueError(f"工作流必须且只能有一个 start 节点，当前 {len(starts)} 个")
        if not any(n.type == NodeType.END for n in self.nodes):
            raise ValueError("工作流至少需要一个 end 节点")

        # 5. start 不能有入边，end 不能有出边
        for e in self.edges:
            if self.get_node(e.target).type == NodeType.START:
                raise ValueError(f"start 节点不能有入边: {e.id}")
            if self.get_node(e.source).type == NodeType.END:
                raise ValueError(f"end 节点不能有出边: {e.id}")

        # 6. 环检测：MVP 不支持循环节点，保存时就拦住，别等到执行时才发现
        cycle = find_cycle(self.to_adjacency())
        if cycle:
            raise CyclicGraphError(cycle)

        return self


# ---------------------------------------------------------------- 执行期结构

class Context:
    """
    一次执行的变量池。

    - inputs:   工作流全局输入（来自 start 节点）
    - outputs:  各节点的输出，key 为节点 id
    """

    _VAR_PATTERN = re.compile(r"\{\{\s*([\w.]+)\s*\}\}")

    def __init__(self, inputs: dict[str, Any] | None = None,
                 services: dict[str, Any] | None = None):
        self.inputs: dict[str, Any] = inputs or {}
        self.outputs: dict[str, Any] = {}
        # 服务定位器：执行器把 llm_provider、http_client 等外部依赖注入进来，
        # 节点按需取用，节点本身不负责创建连接。测试时换成 mock 即可离线跑通。
        self.services: dict[str, Any] = services or {}

    def set_output(self, node_id: str, value: Any) -> None:
        """
        记录节点输出。

        约定：节点输出统一是 dict，且至少含 output 字段，所以引用一律写
        {{node_id.output}}。这样节点还能顺带吐出 usage、duration 等元信息
        供下游引用。传入非 dict 时自动包装一层，保证引用语法永远一致。
        """
        self.outputs[node_id] = value if isinstance(value, dict) else {"output": value}

    def get_output(self, node_id: str) -> Any:
        if node_id not in self.outputs:
            raise KeyError(f"节点 {node_id} 还没有输出，无法引用")
        return self.outputs[node_id]

    def _resolve(self, path: str) -> Any:
        """解析 a.b.c 形式的路径，先在 outputs 里找，再去 inputs 里找。"""
        parts = path.split(".")
        head, rest = parts[0], parts[1:]

        if head in self.outputs:
            value = self.outputs[head]
        elif head in self.inputs:
            value = self.inputs[head]
        else:
            raise KeyError(f"变量未定义: {path}")

        for key in rest:
            if not isinstance(value, dict) or key not in value:
                raise KeyError(f"变量路径无法解析: {path}")
            value = value[key]
        return value

    def render(self, template: str) -> str:
        """把字符串里的 {{xxx}} 全部替换成实际值。"""
        def _sub(match: re.Match) -> str:
            value = self._resolve(match.group(1))
            return value if isinstance(value, str) else str(value)

        return self._VAR_PATTERN.sub(_sub, template)

    def render_expression(self, template: str) -> str:
        """
        渲染成可直接求值的字面量表达式：字符串自动加引号。

        {{llm_1.output}} 渲染成 冒泡排序    ->  语法错误
        {{llm_1.output}} 渲染成 '冒泡排序'  ->  len('冒泡排序') > 5 可正常求值
        """
        def _sub(match: re.Match) -> str:
            value = self._resolve(match.group(1))
            return repr(value) if isinstance(value, str) else str(value)

        return self._VAR_PATTERN.sub(_sub, template)

    def render_value(self, value: Any) -> Any:
        """递归渲染：字符串直接渲染，dict / list 逐项渲染。"""
        if isinstance(value, str):
            return self.render(value)
        if isinstance(value, dict):
            return {k: self.render_value(v) for k, v in value.items()}
        if isinstance(value, list):
            return [self.render_value(v) for v in value]
        return value


class NodeResult(BaseModel):
    """单个节点的执行结果，用于日志、回放、前端高亮。"""
    node_id: str
    node_type: NodeType
    status: NodeStatus
    output: Any = None
    error: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def duration_ms(self) -> int:
        """
        节点耗时。用 computed_field 而不是普通 property，
        否则 model_dump 时会把它丢掉，存库后前端就看不到每个节点花了多久。
        """
        if self.started_at and self.finished_at:
            return int((self.finished_at - self.started_at).total_seconds() * 1000)
        return 0


class WorkflowStatus(str, Enum):
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"


class ExecutionRecord(BaseModel):
    """一次完整执行的记录，落库用，前端执行历史页直接读它。"""
    id: str = Field(default_factory=short_id)
    workflow_id: str
    status: WorkflowStatus = WorkflowStatus.RUNNING
    inputs: dict[str, Any] = Field(default_factory=dict)
    final_output: Any = None
    node_results: list[NodeResult] = Field(default_factory=list)
    error: str | None = None
    started_at: datetime = Field(default_factory=datetime.now)
    finished_at: datetime | None = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def duration_ms(self) -> int:
        if self.finished_at:
            return int((self.finished_at - self.started_at).total_seconds() * 1000)
        return 0


# ---------------------------------------------------------------- 自测 demo

if __name__ == "__main__":
    wf = Workflow(
        name="知识点讲解生成",
        description="输入知识点 -> 大模型生成讲解 -> 按长度分支 -> 输出",
        nodes=[
            Node(id="start_1", type=NodeType.START, name="开始",
                 config={"inputs": {"topic": "冒泡排序"}}, position=Position(x=0, y=0)),
            Node(id="llm_1", type=NodeType.LLM, name="生成讲解",
                 config={"model": "gpt-4o-mini",
                         "prompt": "请用通俗语言讲解：{{topic}}",
                         "temperature": 0.7},
                 position=Position(x=260, y=0)),
            Node(id="cond_1", type=NodeType.CONDITION, name="长度判断",
                 config={"branches": [
                     {"handle": "too_long", "label": "超过 500 字",
                      "expression": "len({{llm_1.output}}) > 500"}],
                     "default_handle": "ok"},
                 position=Position(x=520, y=0)),
            Node(id="end_1", type=NodeType.END, name="结束",
                 config={"output_template": "讲解结果：{{llm_1.output}}"},
                 position=Position(x=780, y=0)),
        ],
        edges=[
            Edge(source="start_1", target="llm_1"),
            Edge(source="llm_1", target="cond_1"),
            Edge(source="cond_1", target="end_1", source_handle="ok"),
        ],
    )

    # 调试打印已移除：校验与渲染逻辑保留，仅去掉上线多余的 stdout 输出
