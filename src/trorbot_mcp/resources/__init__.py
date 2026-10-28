from fastmcp import FastMCP
from trorbot_mcp.resources import fiscal_year_metadata


def register_resources(mcp: FastMCP) -> None:
    fiscal_year_metadata.register(mcp)
