"""
应用入口。

启动：
    uvicorn backend.api.main:app --reload
"""

from __future__ import annotations

import os
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from backend.api.routes import router
from backend.core.logging import get_logger, setup_logging
from backend.core.providers import get_provider
from backend.db.database import init_db
from backend.db.repository import NotFoundError

logger = get_logger("agentflow.api")

DESCRIPTION = """
拖拽画布编排模型 / 工具 / 条件分支的执行引擎。

- 工作流定义保存时即校验图结构（含环检测）
- 执行按分层批次并发调度，节点失败自动传播到下游
"""


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """启动时初始化日志与数据表。用 lifespan 而不是已废弃的 on_event。"""
    setup_logging()
    init_db()
    logger.info("服务启动完成，模型 provider = %s", app.state.llm_provider.name)
    yield
    logger.info("服务已停止")


def _load_env_file() -> None:
    """
    读取 backend/.env（若存在），把键值注入 os.environ。

    .env 不进版本库，密钥只留在本机。已存在的环境变量不会被覆盖，
    方便临时用命令行 export 覆盖。
    """
    from pathlib import Path

    env_path = Path(__file__).resolve().parent.parent / ".env"
    if not env_path.exists():
        return
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key, val = key.strip(), val.strip().strip('"').strip("'")
        os.environ.setdefault(key, val)


def build_provider():
    """
    按环境变量构造模型 provider。

    默认 mock：离线可跑、不花钱、不依赖密钥，本地开发和演示都够用。
    要接真模型时设 LLM_PROVIDER=openai 并配 OPENAI_API_KEY（见 backend/.env）。
    """
    _load_env_file()
    name = os.getenv("LLM_PROVIDER", "mock")
    if name == "openai":
        return get_provider(
            "openai",
            api_key=os.getenv("OPENAI_API_KEY"),
            base_url=os.getenv("OPENAI_BASE_URL"),
        )
    return get_provider(name)


def create_app() -> FastAPI:
    app = FastAPI(
        title="AgentFlow",
        description=DESCRIPTION,
        version="0.2.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=os.getenv("CORS_ORIGINS", "*").split(","),
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 模型 provider 由环境变量决定，默认 mock（离线可跑、不花钱）
    app.state.llm_provider = build_provider()

    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        """记录每个请求的方法、路径、状态码与耗时，便于排查慢接口。"""
        started = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = (time.perf_counter() - started) * 1000
        logger.info(
            "%s %s -> %d  %.1fms",
            request.method,
            request.url.path,
            response.status_code,
            elapsed_ms,
        )
        return response

    @app.exception_handler(NotFoundError)
    async def not_found_handler(request: Request, exc: NotFoundError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(ValidationError)
    async def validation_handler(request: Request, exc: ValidationError) -> JSONResponse:
        """
        工作流结构非法（缺 start、连成环、节点配置字段错）统一返回 422。

        只取 loc / msg / type 三个字段：errors() 里的 input 会带上 Node 这类
        领域对象，直接序列化会抛 TypeError，而且前端也用不上。
        """
        errors = [
            {"loc": list(e.get("loc") or []), "msg": e.get("msg"), "type": e.get("type")}
            for e in exc.errors()
        ]
        return JSONResponse(
            status_code=422,
            content={"detail": "工作流结构校验失败", "errors": errors},
        )

    @app.exception_handler(ValueError)
    async def value_error_handler(request: Request, exc: ValueError) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    app.include_router(router)
    return app


app = create_app()
