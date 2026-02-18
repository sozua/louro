from __future__ import annotations

import asyncio
import logging
import time
from collections import deque

from agno.agent import Agent, RunOutput

from src.config import get_settings

logger = logging.getLogger(__name__)
# Rough chars-per-token ratio for estimation
_CHARS_PER_TOKEN = 4
# Overhead for system prompt, tool definitions, and knowledge base context
# that are invisible in the user prompt but count against the rate limit
_OVERHEAD_TOKENS = 8_000
# Maximum wall-clock time for a single agent run (seconds)
_AGENT_TIMEOUT = 120.0


class TokenBudget:
    """Sliding-window tracker for input tokens consumed per minute.

    Note: ``tokens_used`` / ``tokens_available`` read the deque without the
    async lock.  This is safe under CPython's GIL in a single-threaded async
    event loop, but must be revisited if the code ever runs under a
    multi-threaded executor.
    """

    def __init__(self, tokens_per_minute: int):
        self.tokens_per_minute = tokens_per_minute
        self._log: deque[tuple[float, int]] = deque()  # (monotonic_ts, tokens)
        self._lock = asyncio.Lock()

    def _purge(self) -> None:
        cutoff = time.monotonic() - 60
        while self._log and self._log[0][0] < cutoff:
            self._log.popleft()

    @property
    def tokens_used(self) -> int:
        self._purge()
        return sum(t for _, t in self._log)

    @property
    def tokens_available(self) -> int:
        return max(0, self.tokens_per_minute - self.tokens_used)

    async def acquire(self, estimated_tokens: int) -> None:
        """Wait until the budget has room, then reserve estimated_tokens."""
        while True:
            async with self._lock:
                self._purge()
                used = sum(t for _, t in self._log)
                available = self.tokens_per_minute - used
                # Proceed if there's room, or if the window is empty — blocking
                # forever when a single request exceeds the limit is worse than
                # a brief rate-limit spike.
                if available >= estimated_tokens or not self._log:
                    self._log.append((time.monotonic(), estimated_tokens))
                    logger.info(
                        "Token budget: reserved %d tokens (%d/%d used)",
                        estimated_tokens,
                        used + estimated_tokens,
                        self.tokens_per_minute,
                    )
                    return
                # Calculate wait time while still holding the lock
                wait = max(1.0, self._log[0][0] + 60 - time.monotonic())
                logger.warning(
                    "Token budget: no capacity (%d available, need %d). Waiting %.0fs",
                    available,
                    estimated_tokens,
                    wait,
                )
            # Sleep outside the lock so other coroutines can proceed
            await asyncio.sleep(wait)

    def record_actual(self, estimated: int, actual: int) -> None:
        """Adjust the reservation with the real token count."""
        diff = actual - estimated
        if diff != 0:
            self._log.append((time.monotonic(), diff))
            logger.info(
                "Token budget: adjusted by %+d (estimated %d, actual %d)",
                diff,
                estimated,
                actual,
            )


# Module-level singleton — shared across all agent calls in the process
_budget: TokenBudget | None = None


def get_token_budget() -> TokenBudget:
    global _budget
    if _budget is None:
        settings = get_settings()
        _budget = TokenBudget(settings.anthropic_input_tokens_per_minute)
    return _budget


def reset_token_budget() -> None:
    global _budget
    _budget = None


def _estimate_tokens(prompt: str) -> int:
    """Conservative estimate of input tokens (prompt + system/tools overhead)."""
    return _OVERHEAD_TOKENS + len(prompt) // _CHARS_PER_TOKEN


async def run_agent_with_retry(agent: Agent, *, prompt: str):
    """Wait for token capacity, run the agent, and record actual usage."""
    budget = get_token_budget()
    estimated = _estimate_tokens(prompt)

    await budget.acquire(estimated)
    try:
        response: RunOutput = await asyncio.wait_for(agent.arun(input=prompt), timeout=_AGENT_TIMEOUT)  # type: ignore[arg-type]
    except TimeoutError:
        logger.error("Agent timed out after %.0fs", _AGENT_TIMEOUT)
        raise

    # Normalize content to string — agno may return a list of content parts.
    # When output_schema is set, content is a Pydantic model; leave it as-is.
    if isinstance(response.content, list):
        response.content = "".join(str(part) for part in response.content)

    if response.metrics and response.metrics.input_tokens:
        budget.record_actual(estimated, response.metrics.input_tokens)

    return response
