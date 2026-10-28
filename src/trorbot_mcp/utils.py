"""Shared HTTP helpers.

All outbound requests go through fetch_fiscal, fetch_fiscal_all, or
fetch_trorbot_kb — never accept a full URL from tool callers; only validated
relative paths reach here.
"""

from __future__ import annotations

import logging

import httpx

from trorbot_mcp.config import settings

logger = logging.getLogger(__name__)

# Module-level clients reused across requests (connection pooling).
_fiscal_client: httpx.AsyncClient | None = None
_trorbot_client: httpx.AsyncClient | None = None


def _check_path(path: str) -> None:
    """Reject anything that isn't a plain relative endpoint path."""
    if not path.startswith("/") or "://" in path or ".." in path or path.startswith("//"):
        raise ValueError(f"Invalid API path: {path!r}")


def _get_fiscal_client() -> httpx.AsyncClient:
    global _fiscal_client
    if _fiscal_client is None or _fiscal_client.is_closed:
        _fiscal_client = httpx.AsyncClient(
            timeout=settings.http_timeout,
            follow_redirects=False,  # never follow redirects — treat as errors
            trust_env=False,  # ignore proxy env vars; the origin is fixed in config
            headers={"Accept": "application/json"},
        )
    return _fiscal_client


def _get_trorbot_client() -> httpx.AsyncClient:
    global _trorbot_client
    if _trorbot_client is None or _trorbot_client.is_closed:
        _trorbot_client = httpx.AsyncClient(
            timeout=settings.http_timeout,
            follow_redirects=False,
            trust_env=False,
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
    _check_path(path)
    client = _get_fiscal_client()
    url = settings.fiscal_data_base_url.rstrip("/") + path
    try:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPStatusError as e:
        return {
            "error": f"Fiscal Data API returned {e.response.status_code}",
            "hint": "Check agency_name or fiscal_year filters.",
        }
    except httpx.TimeoutException:
        return {"error": "Request timed out", "hint": "Try again or narrow your filters."}
    except Exception as e:
        # Log the exception type only — no URLs, bodies, or stack traces.
        logger.warning("Fiscal Data request failed: %s", type(e).__name__)
        return {"error": "Fiscal Data API request failed", "hint": "Try again shortly."}


async def fetch_fiscal_all(
    path: str, params: dict, page_size: int = 200
) -> tuple[list[dict], dict | None]:
    """Fetch every page for a Fiscal Data query.

    Returns (rows, error). error is the error dict from the first failed page,
    in which case rows is empty — partial results are never returned silently.
    """
    rows: list[dict] = []
    page = 1
    while True:
        raw = await fetch_fiscal(path, {**params, "page[size]": page_size, "page[number]": page})
        if "error" in raw:
            return [], raw
        data = raw.get("data", [])
        rows.extend(data)
        total_pages = int(raw.get("meta", {}).get("total-pages", 1))
        if not data or page >= total_pages:
            return rows, None
        page += 1


async def fetch_trorbot_kb(path: str, payload: dict) -> dict:
    """POST to a path on the TRORBOT API Gateway.

    Only called when settings.kb_enabled is True.
    """
    if not settings.kb_enabled:
        return {
            "error": "KB tools unavailable",
            "hint": "Set TRORBOT_API_URL and TRORBOT_API_KEY in .env to enable knowledge base tools.",
        }
    _check_path(path)
    client = _get_trorbot_client()
    url = settings.trorbot_api_url.rstrip("/") + path
    try:
        resp = await client.post(url, json=payload)
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPStatusError as e:
        return {"error": f"TRORBOT API returned {e.response.status_code}"}
    except httpx.TimeoutException:
        return {"error": "KB request timed out", "hint": "Try a more specific query."}
    except Exception as e:
        logger.warning("TRORBOT KB request failed: %s", type(e).__name__)
        return {"error": "KB request failed", "hint": "Try again shortly."}
