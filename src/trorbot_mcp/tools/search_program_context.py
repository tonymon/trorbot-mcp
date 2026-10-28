"""Tool: search_program_context

Searches the TRORBOT Context Events Knowledge Base (KB ID: 3VB0O6OVXE).
This KB contains analyst-curated policy events, regulatory changes, legislation,
and program context relevant to federal receivables management.

Requires TRORBOT_API_URL and TRORBOT_API_KEY environment variables.
"""

from __future__ import annotations

from typing import Annotated

from fastmcp import FastMCP

from trorbot_mcp.models import KBSearchInput
from trorbot_mcp.utils import fetch_trorbot_kb

_KB_PATH = "/kb/query"
_KB_ID = "3VB0O6OVXE"   # Context Events KB


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        name="search_program_context",
        annotations={
            "title": "Search policy and regulatory context",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    async def search_program_context(
        params: Annotated[KBSearchInput, "Query and result-count options."]
    ) -> dict:
        """Search the TRORBOT Context Events knowledge base for policy events,
        regulatory changes, and program context affecting federal receivables.

        This KB contains analyst-curated content about legislation (DCIA, DATA Act,
        Debt Collection Improvement Act), Treasury Financial Manual updates, program
        changes to Cross-Servicing, TOP (Treasury Offset Program), AWG, and CRS, and
        significant events that explain trends or anomalies in the receivables data.

        Use this tool to explain WHY data changed, not just WHAT it shows. For example,
        after finding a compliance-rate drop with query_receivables, call this tool to
        find policy or operational context that explains the change.

        Requires: TRORBOT_API_URL and TRORBOT_API_KEY environment variables.
        Returns: { passages: [{text, source, relevance_score}], query, kb }
        """
        result = await fetch_trorbot_kb(_KB_PATH, {
            "query": params.query,
            "kb_id": _KB_ID,
            "max_results": params.max_results,
        })

        if "error" in result:
            return result

        return {
            "passages": result.get("passages") or result.get("results") or [],
            "query": params.query,
            "kb": "Context Events — policy, legislation, program changes",
        }
