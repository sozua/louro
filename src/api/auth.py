from __future__ import annotations

import hmac

from fastapi import HTTPException, Security
from fastapi.security import APIKeyHeader

from src.config import get_settings

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def verify_api_key(key: str | None = Security(_api_key_header)) -> None:
    """Reject requests when API_KEY is configured and the header doesn't match."""
    expected = get_settings().api_key
    if not expected:
        return  # auth disabled
    if not hmac.compare_digest(key or "", expected):
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
