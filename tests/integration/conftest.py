"""Integration test fixtures — testcontainer, settings override, table management."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from testcontainers.postgres import PostgresContainer

from src.config import Settings, override_settings, reset_settings
from src.db.engine import get_engine, reset_engine
from src.db.tables import Base

_tables_created = False


@pytest.fixture(scope="session")
def postgres_container():
    with PostgresContainer("pgvector/pgvector:pg16", driver=None) as pg:
        yield pg


@pytest.fixture(scope="session")
def database_url(postgres_container) -> str:
    host = postgres_container.get_container_host_ip()
    port = postgres_container.get_exposed_port(5432)
    user = postgres_container.username
    password = postgres_container.password
    dbname = postgres_container.dbname
    return f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{dbname}"


@pytest.fixture(scope="session", autouse=True)
def _override_settings(database_url: str):
    test_settings = Settings(
        github_app_id="test-app-id",
        github_private_key="test-key",
        github_webhook_secret="test-secret",
        ai_gateway_api_key="test-gateway-key",
        database_url=database_url,
        _env_file=None,
    )
    override_settings(test_settings)
    yield
    reset_settings()


@pytest.fixture(autouse=True)
async def _setup_and_clean(_override_settings):
    global _tables_created
    # Reset engine so it creates connections on the current event loop
    await reset_engine()
    if not _tables_created:
        engine = get_engine()
        async with engine.begin() as conn:
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            await conn.run_sync(Base.metadata.create_all)
        _tables_created = True
    yield
    # Truncate all tables after each test
    engine = get_engine()
    async with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            await conn.execute(table.delete())
    await reset_engine()


@pytest.fixture
async def client():
    from src.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
