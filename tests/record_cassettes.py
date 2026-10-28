"""Record live Fiscal Data API responses for offline replay in the test suite.

Run when the upstream data or a tool's query shape changes:

    uv run python tests/record_cassettes.py

Each cassette is a list of {"params": {...}, "response": {...}} pairs, one per
HTTP request the tool made. tests/conftest.py replays them with respx.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from fastmcp import Client

from trorbot_mcp import utils
from trorbot_mcp.app import mcp

CASSETTE_DIR = Path(__file__).parent / "cassettes"

# cassette name -> (tool, arguments)
SCENARIOS: dict[str, tuple[str, dict]] = {
    "list_agencies_all": ("list_agencies", {"limit": 100}),
    "list_agencies_cfo": ("list_agencies", {"cfo_agencies_only": True, "limit": 100}),
    "trends_govwide_default": ("get_delinquency_trends", {}),
    "trends_doj_2021_2026": (
        "get_delinquency_trends",
        {"agency_name": "Department of Justice", "fiscal_year_start": 2021, "fiscal_year_end": 2026},
    ),
    "query_doj_fy2023": (
        "query_receivables",
        {"agency_name": "Department of Justice", "fiscal_year": 2023},
    ),
}


async def record() -> None:
    CASSETTE_DIR.mkdir(exist_ok=True)
    client = utils._get_fiscal_client()
    async with Client(mcp) as mcp_client:
        for name, (tool, args) in SCENARIOS.items():
            interactions: list[dict] = []

            async def capture(response, _log=interactions):
                await response.aread()
                _log.append({"params": dict(response.request.url.params), "response": response.json()})

            client.event_hooks["response"] = [capture]
            await mcp_client.call_tool(tool, {"params": args})
            path = CASSETTE_DIR / f"{name}.json"
            path.write_text(json.dumps(interactions, indent=1) + "\n")
            print(f"{path.name}: {len(interactions)} request(s)")


if __name__ == "__main__":
    asyncio.run(record())
