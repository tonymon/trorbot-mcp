from fastmcp import FastMCP

from trorbot_mcp.prompts import analyze_agency, explain_program


def register_prompts(mcp: FastMCP) -> None:
    analyze_agency.register(mcp)
    explain_program.register(mcp)
