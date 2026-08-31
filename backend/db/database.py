"""
数据库连接与会话管理。

设计取舍：
- 默认 SQLite 文件库，零配置启动；换 PostgreSQL 只改 DATABASE_URL 一个环境变量
- Session 通过 FastAPI 依赖注入，每个请求一个会话，请求结束自动关闭
- 测试时把 DATABASE_URL 指向内存库即可，不需要起真数据库
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

DEFAULT_DB_PATH = Path(__file__).resolve().parents[2] / "data" / "agentflow.db"


def get_database_url() -> str:
    return os.getenv("DATABASE_URL", f"sqlite:///{DEFAULT_DB_PATH}")


def _build_engine(url: str):
    if url.startswith("sqlite"):
        return create_engine(url, connect_args={"check_same_thread": False}, future=True)
    return create_engine(url, future=True)


DATABASE_URL = get_database_url()
engine = _build_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False,
                            expire_on_commit=False, class_=Session)


class Base(DeclarativeBase):
    """ORM 模型基类。"""


def init_db() -> None:
    """建表。应用启动时调用一次；重复调用无副作用。"""
    if DATABASE_URL.startswith("sqlite") and "memory" not in DATABASE_URL:
        DEFAULT_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    # 导入 ORM 模型，确保它们注册到 Base.metadata 上
    from backend.db import orm  # noqa: F401

    Base.metadata.create_all(bind=engine)


def get_session() -> Iterator[Session]:
    """FastAPI 依赖项：给每个请求开一个会话，用完即关。"""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
