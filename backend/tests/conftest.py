"""
测试公共夹具。

要点：把数据库指向内存库，这样每个用例都是干净环境，
不落盘、不留垃圾文件、用例之间不会互相污染。
"""

from __future__ import annotations

import pytest

from backend.db.database import Base, get_session
from backend.db import orm  # noqa: F401  注册 ORM 表


@pytest.fixture
def session_factory():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False,
                           expire_on_commit=False)
    yield factory
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture
def client(session_factory):
    from fastapi.testclient import TestClient

    from backend.api.main import create_app
    from backend.core.providers import MockLLMProvider

    app = create_app()
    app.state.llm_provider = MockLLMProvider(default="这是一段模拟生成的内容")

    def override_get_session():
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_session] = override_get_session

    with TestClient(app) as test_client:
        yield test_client
