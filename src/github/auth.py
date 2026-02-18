from __future__ import annotations

import time

import httpx
import jwt

from src.config import get_settings

_token_cache: dict[int, tuple[str, float]] = {}

GITHUB_API = "https://api.github.com"

# Shared client for auth requests (token exchanges).
# Lazily initialised so no connection is opened at import time.
_auth_client: httpx.AsyncClient | None = None


def _get_auth_client() -> httpx.AsyncClient:
    global _auth_client
    if _auth_client is None:
        _auth_client = httpx.AsyncClient(base_url=GITHUB_API, timeout=30.0)
    return _auth_client


async def close_auth_client() -> None:
    """Close the shared auth HTTP client (call during shutdown)."""
    global _auth_client
    if _auth_client is not None:
        await _auth_client.aclose()
        _auth_client = None


def reset_token_cache() -> None:
    _token_cache.clear()


def invalidate_token(installation_id: int) -> None:
    """Remove a cached token so the next request fetches a fresh one."""
    _token_cache.pop(installation_id, None)


def _make_jwt() -> str:
    s = get_settings()
    now = int(time.time())
    payload = {
        "iat": now - 60,
        "exp": now + 600,
        "iss": s.github_app_id,
    }
    return jwt.encode(payload, s.get_github_private_key_bytes(), algorithm="RS256")


async def get_installation_token(installation_id: int) -> str:
    cached = _token_cache.get(installation_id)
    if cached and cached[1] > time.time() + 300:
        return cached[0]

    app_jwt = _make_jwt()
    client = _get_auth_client()
    resp = await client.post(
        f"/app/installations/{installation_id}/access_tokens",
        headers={
            "Authorization": f"Bearer {app_jwt}",
            "Accept": "application/vnd.github+json",
        },
    )
    resp.raise_for_status()

    data = resp.json()
    token = data.get("token")
    if not token:
        raise ValueError(f"GitHub token response missing 'token' key: {list(data.keys())}")
    expires_at = time.time() + 3600  # tokens last ~1h
    _token_cache[installation_id] = (token, expires_at)
    return token  # type: ignore[no-any-return]
