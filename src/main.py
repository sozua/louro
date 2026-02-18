from __future__ import annotations

import asyncio
import contextlib
import json as json_mod
import logging
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from alembic.config import Config as AlembicConfig
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from scalar_fastapi import get_scalar_api_reference
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from alembic import command
from src.api.billing import router as billing_router
from src.api.orgs import router as orgs_router
from src.api.repos import router as repos_router
from src.config import get_settings
from src.db.engine import get_engine
from src.db.queries import cleanup_old_deliveries
from src.github.auth import close_auth_client
from src.github.client import close_client
from src.github.webhooks import router as webhooks_router


class _CorrelationFilter(logging.Filter):
    """Inject the current correlation ID into every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        from src.github.webhooks import correlation_id

        record.correlation_id = correlation_id.get("")  # type: ignore[attr-defined]
        return True


class _JSONFormatter(logging.Formatter):
    """Minimal JSON log formatter for production use."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        cid = getattr(record, "correlation_id", "")
        if cid:
            log_entry["correlation_id"] = cid
        if record.exc_info and record.exc_info[1]:
            log_entry["exception"] = self.formatException(record.exc_info)
        return json_mod.dumps(log_entry)


def _configure_logging() -> None:
    settings = get_settings()
    level = getattr(logging, settings.log_level.upper(), logging.INFO)

    corr_filter = _CorrelationFilter()
    if settings.log_format == "json":
        handler = logging.StreamHandler()
        handler.setFormatter(_JSONFormatter())
        handler.addFilter(corr_filter)
        logging.root.handlers = [handler]
        logging.root.setLevel(level)
    else:
        logging.basicConfig(
            level=level,
            format="%(asctime)s %(levelname)s %(name)s [%(correlation_id)s]: %(message)s",
        )
        for h in logging.root.handlers:
            h.addFilter(corr_filter)


_configure_logging()
logger = logging.getLogger(__name__)


def _run_migrations() -> None:
    """Run Alembic migrations to HEAD on startup."""
    alembic_cfg = AlembicConfig("alembic.ini")
    command.upgrade(alembic_cfg, "head")


async def _cleanup_loop() -> None:
    """Periodically clean up old delivery records."""
    while True:
        await asyncio.sleep(3600)
        try:
            deleted = await cleanup_old_deliveries()
            if deleted:
                logger.info("Cleaned up %d old webhook delivery records", deleted)
        except Exception:
            logger.exception("Webhook delivery cleanup failed")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    if not settings.api_key:
        logger.warning(
            "API_KEY is not set — management endpoints (repos, billing, orgs) "
            "are publicly accessible. Set API_KEY in your environment to require "
            "authentication."
        )

    _run_migrations()
    logger.info("Database migrations applied")

    cleanup_task = asyncio.create_task(_cleanup_loop())

    yield

    cleanup_task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await cleanup_task
    await close_client()
    await close_auth_client()
    await get_engine().dispose()


app = FastAPI(title="Louro", version="0.1.0", lifespan=lifespan, docs_url=None, redoc_url=None)
app.include_router(webhooks_router)
app.include_router(repos_router)
app.include_router(orgs_router)
app.include_router(billing_router)


@app.get("/docs", include_in_schema=False)
async def docs():
    return get_scalar_api_reference(
        openapi_url=app.openapi_url,
        title=app.title,
    )


@app.get("/health")
async def health():
    try:
        engine = get_engine()
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except (OSError, SQLAlchemyError):
        return JSONResponse(status_code=503, content={"status": "unhealthy", "detail": "database unreachable"})
    return {"status": "ok"}
