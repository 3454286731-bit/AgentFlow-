"""
API 请求与响应模型。

原则：直接复用 core 里的领域模型（Node / Edge / Workflow），
不另起一套平行的 DTO，避免前后端字段对不上时两边都要改。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from backend.core.models import (
    CONFIG_REGISTRY,
    Edge,
    ExecutionRecord,
    Node,
    NodeResult,
    Workflow,
    WorkflowStatus,
)


# ---------------------------------------------------------------- 工作流

class WorkflowCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = ""
    nodes: list[Node]
    edges: list[Edge] = Field(default_factory=list)


class WorkflowUpdate(BaseModel):
    """画布保存是整体提交，所以每次更新都传完整的节点和连线。"""

    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    nodes: list[Node] | None = None
    edges: list[Edge] | None = None


class WorkflowBrief(BaseModel):
    id: str
    name: str
    description: str
    version: int
    node_count: int
    edge_count: int
    updated_at: datetime

    @classmethod
    def from_domain(cls, wf: Workflow) -> WorkflowBrief:
        return cls(
            id=wf.id,
            name=wf.name,
            description=wf.description,
            version=wf.version,
            node_count=len(wf.nodes),
            edge_count=len(wf.edges),
            updated_at=wf.updated_at,
        )


class WorkflowDetail(WorkflowBrief):
    nodes: list[Node]
    edges: list[Edge]

    @classmethod
    def from_domain(cls, wf: Workflow) -> WorkflowDetail:
        return cls(
            id=wf.id,
            name=wf.name,
            description=wf.description,
            version=wf.version,
            node_count=len(wf.nodes),
            edge_count=len(wf.edges),
            updated_at=wf.updated_at,
            nodes=wf.nodes,
            edges=wf.edges,
        )


class WorkflowListResponse(BaseModel):
    items: list[WorkflowBrief]
    total: int
    skip: int
    limit: int


# ---------------------------------------------------------------- 执行

class RunRequest(BaseModel):
    inputs: dict[str, Any] = Field(default_factory=dict)


class ExecutionBrief(BaseModel):
    id: str
    workflow_id: str
    workflow_name: str = ""
    status: WorkflowStatus
    duration_ms: int
    started_at: datetime
    error: str | None = None

    @classmethod
    def from_domain(cls, record: ExecutionRecord, workflow_name: str = "") -> ExecutionBrief:
        return cls(
            id=record.id,
            workflow_id=record.workflow_id,
            workflow_name=workflow_name,
            status=record.status,
            duration_ms=record.duration_ms,
            started_at=record.started_at,
            error=record.error,
        )


class ExecutionDetail(ExecutionBrief):
    inputs: dict[str, Any]
    final_output: Any = None
    finished_at: datetime | None = None
    node_results: list[NodeResult]

    @classmethod
    def from_domain(cls, record: ExecutionRecord, workflow_name: str = "") -> ExecutionDetail:
        return cls(
            id=record.id,
            workflow_id=record.workflow_id,
            workflow_name=workflow_name,
            status=record.status,
            duration_ms=record.duration_ms,
            started_at=record.started_at,
            finished_at=record.finished_at,
            error=record.error,
            inputs=record.inputs,
            final_output=record.final_output,
            node_results=record.node_results,
        )


class ExecutionListResponse(BaseModel):
    items: list[ExecutionBrief]
    total: int
    skip: int
    limit: int


class ExecutionStats(BaseModel):
    total: int
    success: int
    failed: int
    avg_duration_ms: int


# ---------------------------------------------------------------- 节点元数据

class NodeTypeMeta(BaseModel):
    """节点类型说明 + 配置 JSON Schema。前端据此自动生成配置表单，不用手写。"""

    type: str
    config_schema: dict[str, Any]


def node_type_metadata() -> list[NodeTypeMeta]:
    return [
        NodeTypeMeta(type=node_type.value, config_schema=cfg.model_json_schema())
        for node_type, cfg in CONFIG_REGISTRY.items()
    ]
