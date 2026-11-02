"""Tool registry — one import + one register() call per tool file."""

from fastmcp import FastMCP

from trorbot_mcp.tools import (
    get_annual_report_insights,
    get_delinquency_trends,
    list_agencies,
    query_receivables,
    search_program_context,
    search_program_guidance,
    validate_tror_submission,
)


def register_tools(mcp: FastMCP) -> None:
    list_agencies.register(mcp)
    query_receivables.register(mcp)
    get_delinquency_trends.register(mcp)
    search_program_context.register(mcp)
    search_program_guidance.register(mcp)
    get_annual_report_insights.register(mcp)
    validate_tror_submission.register(mcp)
