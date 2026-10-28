"""Tool: search_program_guidance

Searches the TRORBOT Program Documentation Knowledge Base (KB ID: XWK0Y3PBLB).
This KB contains Fiscal Service FAQ pages, program guides, legislation PDFs,
and legal authority documents for Cross-Servicing, TOP, AWG, CRS, DCIA, and TROR.

Requires TRORBOT_API_URL and TRORBOT_API_KEY environment variables.
"""

from __future__ import annotations

from typing import Annotated

from fastmcp import FastMCP

from trorbot_mcp.models import KBSearchInput
from trorbot_mcp.utils import fetch_trorbot_kb

_KB_PATH = "/kb/query"
_KB_ID = "XWK0Y3PBLB"   # Program Documentation KB


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        name="search_program_guidance",
        annotations={
            "title": "Search program rules and legal authorities",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    async def search_program_guidance(
        params: Annotated[KBSearchInput, "Query and result-count options."]
    ) -> dict:
        """Search TRORBOT's Program Documentation knowledge base for rules, procedures,
        and legal authorities governing federal debt collection and receivables reporting.

        This KB covers:
        - Cross-Servicing: referral thresholds, delinquency definitions, agency exemptions
        - TOP (Treasury Offset Program): offset rules, eligibility, exclusions
        - AWG (Administrative Wage Garnishment): procedures and limits
        - CRS (Centralized Receivables Service): onboarding, program rules
        - DCIA (Debt Collection Improvement Act) requirements
        - TROR reporting requirements, form instructions, data definitions
        - Treasury Financial Manual (TFM) receivables chapters

        Use this tool when you need to understand WHAT the rules are — thresholds,
        definitions, compliance requirements. For WHY data changed, use search_program_context.

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
            "kb": "Program Documentation — rules, procedures, legal authorities",
        }
