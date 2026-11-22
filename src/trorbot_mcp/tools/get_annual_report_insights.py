"""Tool: get_annual_report_insights

Searches the TRORBOT Annual TROR Reports knowledge base.
This KB contains PDF Annual TROR Reports to Congress, which provide government-wide
receivables summaries, trend analysis, and program highlights for each fiscal year.

Requires TRORBOT_KB_BUCKET (an Amazon S3 Vectors bucket) and AWS credentials.
"""

from __future__ import annotations

from typing import Annotated

from fastmcp import FastMCP

from trorbot_mcp.kb import search_kb
from trorbot_mcp.models import KBSearchInput

_KB = "annual-tror-reports"


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        name="get_annual_report_insights",
        annotations={
            "title": "Get insights from annual TROR reports",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    async def get_annual_report_insights(
        params: Annotated[KBSearchInput, "Query and result-count options."]
    ) -> dict:
        """Search the Annual TROR Reports to Congress knowledge base for government-wide
        receivables summaries, year-over-year trend analysis, and program highlights.

        Each annual report (FY2016–present) contains:
        - Government-wide totals: receivables outstanding, delinquencies, collections
        - Agency-by-agency breakdowns and compliance summaries
        - Highlight narratives on significant changes and program achievements
        - Cross-Servicing and TOP referral totals
        - CRS and AWG program statistics

        Use this tool for authoritative narrative context from Treasury's official reports.
        Complement with query_receivables for precise current numbers and
        search_program_context for recent policy events not yet in an annual report.

        Requires: TRORBOT_KB_BUCKET and AWS credentials.
        Returns: { passages: [{text, source, source_uri, relevance_score}], query, kb }
        """
        result = await search_kb(_KB, params.query, params.max_results)

        if "error" in result:
            return result

        return {
            "passages": result["passages"],
            "query": params.query,
            "kb": "Annual TROR Reports to Congress — government-wide summaries and narratives",
        }
