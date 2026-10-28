"""Tool: list_agencies

Returns federal agencies that report 120-day delinquent debt referral data
under the DATA Act compliance dataset (TROR).

Use this tool first when the exact agency name is unknown — the returned
agency_name values are the valid inputs for query_receivables and
get_delinquency_trends.

Data source: Fiscal Data API — api.fiscaldata.treasury.gov
Endpoint: /v2/debt/tror/data_act_compliance
Update cadence: Quarterly
"""

from __future__ import annotations

from typing import Annotated

from fastmcp import FastMCP

from trorbot_mcp.models import ListAgenciesInput
from trorbot_mcp.utils import fetch_fiscal

_TROR_PATH = "/v2/debt/tror/data_act_compliance"


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        name="list_agencies",
        annotations={
            "title": "List TROR reporting agencies",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def list_agencies(params: Annotated[ListAgenciesInput, "Filter and pagination options."]) -> dict:
        """List federal agencies that report 120-day delinquent debt referral (DDR)
        compliance data under the Treasury Report on Receivables (TROR).

        Returns unique agency names and their reporting fiscal year range.
        Use the exact agency_name returned here when calling query_receivables
        or get_delinquency_trends. Supports substring search and fiscal-year filtering.

        Data source: Fiscal Data API (api.fiscaldata.treasury.gov), updated quarterly.
        Returns: { agencies: [{agency_name, first_fy, latest_fy}], total, has_more }
        """
        api_params: dict = {
            "page[size]": 100,
            "page[number]": 1,
            "fields": "agency_nm,record_fiscal_year,agency_bureau_indicator",
            "sort": "agency_nm",
            # Only return agency-level rows (not bureau sub-rows) to keep the list concise
            "filter": "agency_bureau_indicator:eq:Agency",
        }

        if params.has_data_since_fy:
            api_params["filter"] += f",record_fiscal_year:gte:{params.has_data_since_fy}"

        raw = await fetch_fiscal(_TROR_PATH, api_params)

        if "error" in raw:
            return raw

        data = raw.get("data", [])

        # Deduplicate by agency name, collecting fiscal year range
        agencies: dict[str, dict] = {}
        for row in data:
            name = row.get("agency_nm", "")
            fy = int(row.get("record_fiscal_year", 0))
            if not name:
                continue
            if name not in agencies:
                agencies[name] = {"agency_name": name, "first_fy": fy, "latest_fy": fy}
            else:
                agencies[name]["first_fy"] = min(agencies[name]["first_fy"], fy)
                agencies[name]["latest_fy"] = max(agencies[name]["latest_fy"], fy)

        result = list(agencies.values())

        if params.search:
            term = params.search.lower()
            result = [a for a in result if term in a["agency_name"].lower()]

        # Apply offset/limit after deduplication (API gives all pages in one pull above)
        total = len(result)
        paged = result[params.offset: params.offset + params.limit]
        has_more = (params.offset + params.limit) < total

        return {
            "agencies": paged,
            "total": total,
            "returned": len(paged),
            "has_more": has_more,
            "next_offset": params.offset + params.limit if has_more else None,
            "as_of": "Fiscal Data API — updated quarterly",
        }
