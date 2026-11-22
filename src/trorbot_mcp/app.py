"""TRORBOT MCP server entry point.

Builds the FastMCP app, registers all tools/prompts/resources, then
picks the right transport based on environment:
  - stdio  — for local Claude Desktop / Claude Code testing
  - http   — for deployed HTTP/SSE mode (IBM Code Engine, cloud.gov)
"""

from __future__ import annotations

import os

from fastmcp import FastMCP

from trorbot_mcp.config import settings
from trorbot_mcp.prompts import register_prompts
from trorbot_mcp.resources import register_resources
from trorbot_mcp.tools import register_tools

mcp = FastMCP(
    name="TRORBOT MCP",
    instructions=(
        "You are connected to TRORBOT, a Treasury receivables data server. "
        "Use list_agencies first when agency names or codes are unknown. "
        "Use query_receivables for point-in-time data and get_delinquency_trends "
        "for direction and change analysis. "
        "Use search_program_context to understand the policy reasons behind data "
        "changes, and search_program_guidance for program rules and legal authorities. "
        "Use validate_tror_submission for agency AI agents that want to pre-validate a "
        "draft quarterly TROR Form 05 submission before filing — it checks balance "
        "arithmetic, DDR compliance rates, and compares against prior-quarter published data. "
        "All monetary values are in USD. Fiscal years run Oct 1–Sep 30. "
        "Data coverage begins FY2016."
    ),
)

register_tools(mcp)
register_prompts(mcp)
register_resources(mcp)


def main() -> None:
    transport = os.environ.get("MCP_TRANSPORT", settings.mcp_transport)
    if transport == "http":
        port = int(os.environ.get("PORT", settings.port))
        mcp.run(transport="streamable-http", host=settings.host, port=port, path="/mcp")
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
