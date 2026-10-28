"""Resource: trorbot://fiscal-year-metadata

Static reference data an agent can read before making tool calls.
Provides the current and available fiscal years, quarter definitions,
and data coverage notes — reduces round-trips for orientation queries.
"""

from __future__ import annotations

import json
from datetime import date

from fastmcp import FastMCP


def _current_fiscal_year() -> int:
    today = date.today()
    # Federal fiscal year starts Oct 1; Jan–Sep belong to the current calendar year's FY
    return today.year if today.month < 10 else today.year + 1


def register(mcp: FastMCP) -> None:
    @mcp.resource("trorbot://fiscal-year-metadata")
    def fiscal_year_metadata() -> str:
        """Reference metadata for the TROR dataset: fiscal year range, quarter definitions,
        and data coverage notes. Read this resource when you need to know what fiscal years
        or quarters are available before calling query_receivables or get_delinquency_trends.
        """
        current_fy = _current_fiscal_year()
        return json.dumps({
            "current_fiscal_year": current_fy,
            "data_coverage": {
                "first_available_fy": 2016,
                "latest_complete_fy": current_fy - 1,
                "note": "FY2016 is the start of TROR form_05 era (DATA Act). Pre-2016 tables retired March 2026.",
            },
            "fiscal_quarters": {
                "Q1": "October 1 – December 31",
                "Q2": "January 1 – March 31",
                "Q3": "April 1 – June 30",
                "Q4": "July 1 – September 30",
            },
            "fiscal_year_definition": "October 1 through September 30 of the following calendar year. FY2024 = Oct 2023 – Sep 2024.",
            "data_freshness": "Updated quarterly, approximately 45–60 days after quarter close.",
            "monetary_units": "All USD values in the dataset are in whole dollars unless otherwise noted.",
        }, indent=2)
