"""Shared HTTP helpers.

All outbound requests go through fetch_fiscal or fetch_trorbot_kb — never
accept a full URL from tool callers; only validated relative paths reach here.
"""

from __future__ import annotations

import httpx

from trorbot_mcp.config import settings

# Module-level clients reused across requests (connection pooling).
_fiscal_client: httpx.AsyncClient | None = None
_trorbot_client: httpx.AsyncClient | None = None


def _get_fiscal_client() -> httpx.AsyncClient:
    global _fiscal_client
    if _fiscal_client is None or _fiscal_client.is_closed:
        _fiscal_client = httpx.AsyncClient(
            base_url=settings.fiscal_data_base_url,
            timeout=settings.http_timeout,
            follow_redirects=False,  # never follow redirects — treat as errors
            headers={"Accept": "application/json"},
        )
    return _fiscal_client


def _get_trorbot_client() -> httpx.AsyncClient:
    global _trorbot_client
    if _trorbot_client is None or _trorbot_client.is_closed:
        _trorbot_client = httpx.AsyncClient(
            base_url=settings.trorbot_api_url,
            timeout=settings.http_timeout,
            follow_redirects=False,
            headers={
                "Accept": "application/json",
                "x-api-key": settings.trorbot_api_key,
            },
        )
    return _trorbot_client


async def fetch_fiscal(path: str, params: dict | None = None) -> dict:
    """GET a path appended to the Fiscal Data API base URL.

    path must start with / and contain only the endpoint segment (no scheme/host).
    Explicit string concatenation avoids httpx URL-resolution edge cases where a
    leading / would strip the base path entirely.
    """
    client = _get_fiscal_client()
    url = settings.fiscal_data_base_url.rstrip("/") + path
    try:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPStatusError as e:
        return {"error": f"Fiscal Data API returned {e.response.status_code}", "hint": "Check agency_code or fiscal_year filters."}
    except httpx.TimeoutException:
        return {"error": "Request timed out", "hint": "Try again or narrow your filters."}
    except Exception as e:
        return {"error": "Unexpected error", "detail": str(e)}


async def fetch_trorbot_kb(path: str, payload: dict) -> dict:
    """POST to a path on the TRORBOT API Gateway.

    Only called when settings.kb_enabled is True.
    """
    if not settings.kb_enabled:
        return {
            "error": "KB tools unavailable",
            "hint": "Set TRORBOT_API_URL and TRORBOT_API_KEY in .env to enable knowledge base tools.",
        }
    client = _get_trorbot_client()
    try:
        resp = await client.post(path, json=payload)
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPStatusError as e:
        return {"error": f"TRORBOT API returned {e.response.status_code}"}
    except httpx.TimeoutException:
        return {"error": "KB request timed out", "hint": "Try a more specific query."}
    except Exception as e:
        return {"error": "Unexpected error", "detail": str(e)}
