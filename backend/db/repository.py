"""
仓储层：把 ORM 行和领域模型互相转换，向上只暴露领域对象。

上层（API、执行器）永远只见 Workflow / ExecutionRecord，
不碰 SQLAlchemy，这样以后换数据库或换 ORM 都不会波及业务代码。
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.core.models import ExecutionRecord, NodeResult, Workflow, WorkflowStatus
from backend.db.orm import ExecutionTable, WorkflowTable


class NotFoundError(LookupError):
    """查不到对应记录。"""


# ---------------------------------------------------------------- 互转

def _row_to_workflow(row: WorkflowTable) -> Workflow:
    data = dict(row.definition or {})
    data.update(
        id=row.id,
        name=row.name,
        description=row.description,
        version=row.version,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )
    return Workflow(**data)


def _row_to_execution(row: ExecutionTable) -> ExecutionRecord:
    return ExecutionRecord(
        id=row.id,
        workflow_id=row.workflow_id,
        status=WorkflowStatus(row.status),
        inputs=row.inputs or {},
        final_output=row.final_output,
        node_results=[NodeResult(**r) for r in (row.node_results or [])],
        error=row.error,
        started_at=row.started_at,
        finished_at=row.finished_at,
    )


# ---------------------------------------------------------------- 工作流

class WorkflowRepository:
    def __init__(self, session: Session):
        self.session = session

    def create(self, workflow: Workflow) -> Workflow:
        row = WorkflowTable(
            id=workflow.id,
            name=workflow.name,
            description=workflow.description,
            version=workflow.version,
            definition=workflow.model_dump(mode="json"),
            created_at=workflow.created_at,
            updated_at=workflow.updated_at,
        )
        self.session.add(row)
        self.session.commit()
        self.session.refresh(row)
        return _row_to_workflow(row)

    def get(self, workflow_id: str) -> Workflow:
        row = self.session.get(WorkflowTable, workflow_id)
        if row is None:
            raise NotFoundError(f"工作流不存在: {workflow_id}")
        return _row_to_workflow(row)

    def list(self, skip: int = 0, limit: int = 50) -> list[Workflow]:
        rows = self.session.execute(
            select(WorkflowTable).order_by(WorkflowTable.updated_at.desc())
            .offset(skip).limit(limit)
        ).scalars().all()
        return [_row_to_workflow(r) for r in rows]

    def count(self) -> int:
        return self.session.execute(select(func.count(WorkflowTable.id))).scalar_one()

    def update(self, workflow: Workflow) -> Workflow:
        row = self.session.get(WorkflowTable, workflow.id)
        if row is None:
            raise NotFoundError(f"工作流不存在: {workflow.id}")
        row.name = workflow.name
        row.description = workflow.description
        row.version = workflow.version + 1
        row.definition = workflow.model_dump(mode="json")
        self.session.commit()
        self.session.refresh(row)
        return _row_to_workflow(row)

    def delete(self, workflow_id: str) -> None:
        row = self.session.get(WorkflowTable, workflow_id)
        if row is None:
            raise NotFoundError(f"工作流不存在: {workflow_id}")
        self.session.delete(row)
        self.session.commit()


# ---------------------------------------------------------------- 执行记录

class ExecutionRepository:
    def __init__(self, session: Session):
        self.session = session

    def save(self, record: ExecutionRecord, workflow_name: str = "") -> ExecutionRecord:
        row = ExecutionTable(
            id=record.id,
            workflow_id=record.workflow_id,
            workflow_name=workflow_name,
            status=record.status.value,
            inputs=record.inputs,
            final_output=_jsonable(record.final_output),
            node_results=[r.model_dump(mode="json") for r in record.node_results],
            error=record.error,
            duration_ms=record.duration_ms,
            started_at=record.started_at,
            finished_at=record.finished_at,
        )
        self.session.add(row)
        self.session.commit()
        self.session.refresh(row)
        return _row_to_execution(row)

    def get(self, execution_id: str) -> ExecutionRecord:
        row = self.session.get(ExecutionTable, execution_id)
        if row is None:
            raise NotFoundError(f"执行记录不存在: {execution_id}")
        return _row_to_execution(row)

    def list(
        self,
        *,
        workflow_id: str | None = None,
        status: WorkflowStatus | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> list[ExecutionRecord]:
        stmt = select(ExecutionTable)
        if workflow_id:
            stmt = stmt.where(ExecutionTable.workflow_id == workflow_id)
        if status:
            stmt = stmt.where(ExecutionTable.status == status.value)
        rows = self.session.execute(
            stmt.order_by(ExecutionTable.started_at.desc()).offset(skip).limit(limit)
        ).scalars().all()
        return [_row_to_execution(r) for r in rows]

    def count(self, workflow_id: str | None = None,
              status: WorkflowStatus | None = None) -> int:
        """
        统计数量。过滤条件必须与 list 保持一致，
        否则分页会出现「总数 10 但只能翻出 3 条」这种对不上的情况。
        """
        stmt = select(func.count(ExecutionTable.id))
        if workflow_id:
            stmt = stmt.where(ExecutionTable.workflow_id == workflow_id)
        if status:
            stmt = stmt.where(ExecutionTable.status == status.value)
        return self.session.execute(stmt).scalar_one()

    def stats(self, workflow_id: str | None = None) -> dict[str, Any]:
        """执行统计：总数、成功数、失败数、平均耗时。给执行历史页的概览卡片用。"""
        stmt = select(
            func.count(ExecutionTable.id),
            func.sum(ExecutionTable.duration_ms),
        )
        if workflow_id:
            stmt = stmt.where(ExecutionTable.workflow_id == workflow_id)
        total, total_ms = self.session.execute(stmt).one()

        stmt_fail = select(func.count(ExecutionTable.id)).where(
            ExecutionTable.status == WorkflowStatus.FAILED.value
        )
        if workflow_id:
            stmt_fail = stmt_fail.where(ExecutionTable.workflow_id == workflow_id)
        failed = self.session.execute(stmt_fail).scalar_one()

        total = total or 0
        return {
            "total": total,
            "success": total - failed,
            "failed": failed,
            "avg_duration_ms": int((total_ms or 0) / total) if total else 0,
        }


def _jsonable(value: Any) -> Any:
    """执行结果可能是任意 Python 对象，落 JSON 列前先确保可序列化。"""
    try:
        import json
        json.dumps(value)
        return value
    except (TypeError, ValueError):
        return str(value)
