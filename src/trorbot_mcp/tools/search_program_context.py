"""Tool: search_program_context

Searches the TRORBOT Context Events knowledge base.
This KB contains analyst-curated policy events, regulatory changes, legislation,
and program context relevant to federal receivables management.

Requires TRORBOT_KB_BUCKET (an Amazon S3 Vectors bucket) and AWS credentials.
"""

from __future__ import annotations

from typing import Annotated

from fastmcp import FastMCP

from trorbot_mcp.kb import search_kb
from trorbot_mcp.models import KBSearchInput

_KB = "context-events"


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

        Requires: TRORBOT_KB_BUCKET and AWS credentials.
        Returns: { passages: [{text, source, source_uri, relevance_score}], query, kb }
        """
        result = await search_kb(_KB, params.query, params.max_results)

        if "error" in result:
            return result

        return {
            "passages": result["passages"],
            "query": params.query,
            "kb": "Context Events — policy, legislation, program changes",
        }
