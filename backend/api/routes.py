"""
REST 接口。

分三组：
- /api/workflows   工作流 CRUD
- /api/executions  执行历史与详情
- /api/node-types  节点类型元数据，供前端动态生成配置表单
"""

from __future__ import annotations

from fastapi import APIRouter, Query, Response, status
from sqlalchemy import text

from backend.api.deps import (
    ExecutionRepoDep,
    ProviderDep,
    SessionDep,
    WorkflowRepoDep,
)
from backend.api.schemas import (
    ExecutionBrief,
    ExecutionDetail,
    ExecutionListResponse,
    ExecutionStats,
    NodeTypeMeta,
    RunRequest,
    WorkflowBrief,
    WorkflowCreate,
    WorkflowDetail,
    WorkflowListResponse,
    WorkflowUpdate,
    node_type_metadata,
)
from backend.core.models import Workflow, WorkflowStatus
from backend.db.repository import ExecutionRepository, NotFoundError, WorkflowRepository
from backend.engine.executor import Executor

router = APIRouter(prefix="/api")


# ---------------------------------------------------------------- 工作流

@router.get("/health", summary="健康检查")
async def health(session: SessionDep, provider: ProviderDep) -> dict:
    """
    健康检查顺带探一下数据库，这样部署后能立刻发现连不上库的情况，
    而不是等第一个业务请求打进来才报错。
    """
    try:
        session.execute(text("SELECT 1"))
        database = "ok"
    except Exception:
        database = "unavailable"

    return {
        "status": "ok" if database == "ok" else "degraded",
        "database": database,
        "provider": provider.name,
    }


@router.get("/node-types", response_model=list[NodeTypeMeta], summary="节点类型与配置 Schema")
async def list_node_types() -> list[NodeTypeMeta]:
    return node_type_metadata()


@router.post("/workflows", response_model=WorkflowDetail, status_code=status.HTTP_201_CREATED,
             summary="创建工作流")
async def create_workflow(payload: WorkflowCreate, repo: WorkflowRepoDep) -> WorkflowDetail:
    workflow = Workflow(
        name=payload.name,
        description=payload.description,
        nodes=payload.nodes,
        edges=payload.edges,
    )
    return WorkflowDetail.from_domain(repo.create(workflow))


@router.get("/workflows", response_model=WorkflowListResponse, summary="工作流列表")
async def list_workflows(
    repo: WorkflowRepoDep,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
) -> WorkflowListResponse:
    return WorkflowListResponse(
        items=[WorkflowBrief.from_domain(w) for w in repo.list(skip, limit)],
        total=repo.count(),
        skip=skip,
        limit=limit,
    )


@router.get("/workflows/{workflow_id}", response_model=WorkflowDetail, summary="工作流详情")
async def get_workflow(workflow_id: str, repo: WorkflowRepoDep) -> WorkflowDetail:
    return WorkflowDetail.from_domain(repo.get(workflow_id))


@router.put("/workflows/{workflow_id}", response_model=WorkflowDetail, summary="更新工作流")
async def update_workflow(
    workflow_id: str, payload: WorkflowUpdate, repo: WorkflowRepoDep
) -> WorkflowDetail:
    current = repo.get(workflow_id)
    merged = Workflow(
        id=current.id,
        name=payload.name if payload.name is not None else current.name,
        description=payload.description if payload.description is not None else current.description,
        version=current.version,
        nodes=payload.nodes if payload.nodes is not None else current.nodes,
        edges=payload.edges if payload.edges is not None else current.edges,
        created_at=current.created_at,
    )
    return WorkflowDetail.from_domain(repo.update(merged))


@router.delete("/workflows/{workflow_id}", status_code=status.HTTP_204_NO_CONTENT,
               summary="删除工作流")
async def delete_workflow(workflow_id: str, repo: WorkflowRepoDep) -> Response:
    repo.delete(workflow_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------- 执行

@router.post("/workflows/{workflow_id}/run", response_model=ExecutionDetail,
             summary="执行一次工作流")
async def run_workflow(
    workflow_id: str,
    payload: RunRequest,
    wf_repo: WorkflowRepoDep,
    exec_repo: ExecutionRepoDep,
    provider: ProviderDep,
) -> ExecutionDetail:
    workflow = wf_repo.get(workflow_id)
    record = await Executor(workflow, llm_provider=provider).run(payload.inputs)
    saved = exec_repo.save(record, workflow_name=workflow.name)
    return ExecutionDetail.from_domain(saved, workflow_name=workflow.name)


@router.get("/workflows/{workflow_id}/executions", response_model=ExecutionListResponse,
            summary="某个工作流的执行历史")
async def list_workflow_executions(
    workflow_id: str,
    exec_repo: ExecutionRepoDep,
    wf_repo: WorkflowRepoDep,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
) -> ExecutionListResponse:
    wf_repo.get(workflow_id)  # 确保工作流存在，否则 404
    items = [
        ExecutionBrief.from_domain(r, workflow_name=_name_of(wf_repo, r.workflow_id))
        for r in exec_repo.list(workflow_id=workflow_id, skip=skip, limit=limit)
    ]
    return ExecutionListResponse(
        items=items, total=exec_repo.count(workflow_id), skip=skip, limit=limit
    )


@router.get("/workflows/{workflow_id}/stats", response_model=ExecutionStats,
            summary="某个工作流的执行统计")
async def workflow_stats(
    workflow_id: str, exec_repo: ExecutionRepoDep, wf_repo: WorkflowRepoDep
) -> ExecutionStats:
    wf_repo.get(workflow_id)
    return ExecutionStats(**exec_repo.stats(workflow_id))


@router.get("/executions", response_model=ExecutionListResponse, summary="全部执行历史")
async def list_executions(
    exec_repo: ExecutionRepoDep,
    wf_repo: WorkflowRepoDep,
    workflow_id: str | None = Query(None, description="按工作流过滤"),
    status_filter: WorkflowStatus | None = Query(None, alias="status"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
) -> ExecutionListResponse:
    items = [
        ExecutionBrief.from_domain(r, workflow_name=_name_of(wf_repo, r.workflow_id))
        for r in exec_repo.list(
            workflow_id=workflow_id, status=status_filter, skip=skip, limit=limit
        )
    ]
    total = exec_repo.count(workflow_id=workflow_id, status=status_filter)
    return ExecutionListResponse(items=items, total=total, skip=skip, limit=limit)


@router.get("/executions/{execution_id}", response_model=ExecutionDetail,
            summary="执行详情，含每个节点的结果")
async def get_execution(
    execution_id: str, exec_repo: ExecutionRepoDep, wf_repo: WorkflowRepoDep
) -> ExecutionDetail:
    record = exec_repo.get(execution_id)
    return ExecutionDetail.from_domain(record, workflow_name=_name_of(wf_repo, record.workflow_id))


def _name_of(repo: WorkflowRepository, workflow_id: str) -> str:
    try:
        return repo.get(workflow_id).name
    except NotFoundError:
        return ""
