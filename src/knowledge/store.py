from __future__ import annotations

import logging
import uuid

from agno.knowledge import Knowledge
from agno.vectordb.pgvector import PgVector, SearchType

from src.config import get_settings

logger = logging.getLogger(__name__)

_knowledge_bases: dict[str, Knowledge] = {}


def _table_name(repo_full_name: str) -> str:
    """Return a per-repo vector table name to isolate knowledge across repos."""
    safe = repo_full_name.replace("/", "_").replace("-", "_").lower()
    return f"knowledge_{safe}"


def get_knowledge_base(repo_full_name: str) -> Knowledge:
    if repo_full_name in _knowledge_bases:
        return _knowledge_bases[repo_full_name]

    s = get_settings()
    vector_db = PgVector(
        table_name=_table_name(repo_full_name),
        db_url=s.pgvector_url,
        search_type=SearchType.hybrid,
    )
    kb = Knowledge(vector_db=vector_db)
    _knowledge_bases[repo_full_name] = kb
    return kb


async def store_onboarding(repo_full_name: str, content: str) -> None:
    """Store the combined onboarding analysis (patterns + architecture) as a single entry."""
    kb = get_knowledge_base(repo_full_name)
    await kb.ainsert(
        name=f"{repo_full_name}/onboarding",
        text_content=content,
        metadata={"repo": repo_full_name, "type": "onboarding"},
    )
    logger.info("Stored onboarding knowledge for %s", repo_full_name)


async def store_evolution(repo_full_name: str, evolution: str) -> None:
    """Store knowledge about how the codebase is evolving (new vs legacy patterns)."""
    kb = get_knowledge_base(repo_full_name)
    await kb.ainsert(
        name=f"{repo_full_name}/evolution",
        text_content=evolution,
        metadata={"repo": repo_full_name, "type": "evolution"},
    )
    logger.info("Stored evolution patterns for %s", repo_full_name)


async def drop_knowledge_base(repo_full_name: str) -> None:
    """Drop the per-repo vector table and remove it from the cache."""
    table = _table_name(repo_full_name)
    _knowledge_bases.pop(repo_full_name, None)

    from src.db.engine import get_engine

    engine = get_engine()
    async with engine.begin() as conn:
        await conn.exec_driver_sql(f'DROP TABLE IF EXISTS "{table}" CASCADE')
    logger.info("Dropped knowledge table for %s", repo_full_name)


def reset_knowledge_bases() -> None:
    _knowledge_bases.clear()


async def store_feedback(repo_full_name: str, original: str, response: str, sentiment: str) -> None:
    """Store feedback as a new entry each time (unique name) so it accumulates."""
    kb = get_knowledge_base(repo_full_name)
    content = (
        f"Code review feedback (sentiment: {sentiment}):\n"
        f"Original review comment: {original}\n"
        f"Developer response: {response}"
    )
    unique_id = uuid.uuid4().hex[:12]
    await kb.ainsert(
        name=f"{repo_full_name}/feedback/{unique_id}",
        text_content=content,
        metadata={"repo": repo_full_name, "type": "feedback", "sentiment": sentiment},
    )
    logger.info("Stored feedback for %s (sentiment: %s)", repo_full_name, sentiment)
