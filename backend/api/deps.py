"""
FastAPI 依赖注入。

把 session、仓储、模型 provider 都做成依赖项，好处是测试时可以直接
dependency_overrides 掉，不用起真数据库、不用真调模型。
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from backend.core.providers import LLMProvider, MockLLMProvider
from backend.db.database import get_session
from backend.db.repository import ExecutionRepository, WorkflowRepository

SessionDep = Annotated[Session, Depends(get_session)]


def get_workflow_repo(session: SessionDep) -> WorkflowRepository:
    return WorkflowRepository(session)


def get_execution_repo(session: SessionDep) -> ExecutionRepository:
    return ExecutionRepository(session)


def get_llm_provider(request: Request) -> LLMProvider:
    """从应用状态取模型 provider，启动时根据环境变量配置，测试时可整体替换。"""
    provider = getattr(request.app.state, "llm_provider", None)
    return provider or MockLLMProvider()


WorkflowRepoDep = Annotated[WorkflowRepository, Depends(get_workflow_repo)]
ExecutionRepoDep = Annotated[ExecutionRepository, Depends(get_execution_repo)]
ProviderDep = Annotated[LLMProvider, Depends(get_llm_provider)]
