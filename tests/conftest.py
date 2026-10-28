"""Shared fixtures: replay recorded Fiscal Data API responses with respx.

Cassettes live in tests/cassettes/ and are produced by tests/record_cassettes.py.
Any request that isn't in the loaded cassette fails the test, so the suite never
touches the live API.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
import respx
from fastmcp import Client

from trorbot_mcp import utils
from trorbot_mcp.app import mcp
from trorbot_mcp.config import settings

CASSETTE_DIR = Path(__file__).parent / "cassettes"
TROR_URL = settings.fiscal_data_base_url.rstrip("/") + "/v2/debt/tror/data_act_compliance"


@pytest.fixture(autouse=True)
def fresh_http_clients():
    """Each test gets new pooled clients bound to its own event loop."""
    utils._fiscal_client = None
    utils._trorbot_client = None
    yield
    utils._fiscal_client = None
    utils._trorbot_client = None


@pytest.fixture
def fiscal_api():
    with respx.mock(assert_all_called=False) as router:
        yield router


@pytest.fixture
def replay(fiscal_api):
    """Load a cassette and serve its recorded responses, matched on query params."""

    def load(name: str) -> respx.Route:
        interactions = json.loads((CASSETTE_DIR / f"{name}.json").read_text())

        def respond(request: httpx.Request) -> httpx.Response:
            params = dict(request.url.params)
            for item in interactions:
                if item["params"] == params:
                    return httpx.Response(200, json=item["response"])
            raise AssertionError(f"No recorded response in {name}.json for params {params}")

        return fiscal_api.get(TROR_URL).mock(side_effect=respond)

    return load


@pytest.fixture
async def client():
    async with Client(mcp) as c:
        yield c


async def call(client: Client, tool: str, args: dict) -> dict:
    """Call a tool and return its structured result."""
    result = await client.call_tool(tool, {"params": args}, raise_on_error=False)
    return result.structured_content
