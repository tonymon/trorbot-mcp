"""Tool: query_receivables

Query federal agency 120-day delinquent debt referral compliance data from the
DATA Act compliance dataset (part of TROR — Treasury Report on Receivables).

Returns eligible debt amounts, referral amounts, and compliance rates by agency,
fiscal year, and quarter.

Data source: Fiscal Data API — api.fiscaldata.treasury.gov
Endpoint: /v2/debt/tror/data_act_compliance
Coverage: FY2016–present
Update cadence: Quarterly, typically 45–60 days after quarter close
"""

from __future__ import annotations

from typing import Annotated

from fastmcp import FastMCP

from trorbot_mcp.models import QueryReceivablesInput
from trorbot_mcp.utils import fetch_fiscal

_TROR_PATH = "/v2/debt/tror/data_act_compliance"

_FIELDS = (
    "record_fiscal_year,"
    "record_fiscal_quarter,"
    "record_date,"
    "agency_nm,"
    "bureau_nm,"
    "agency_bureau_indicator,"
    "total_eligible_debt_amt,"
    "total_eligible_debt_cnt,"
    "eligible_debt_referred_amt,"
    "eligible_debt_referred_cnt,"
    "eligible_debt_not_referred_amt,"
    "eligible_debt_not_referred_cnt,"
    "compliance_rate_amt,"
    "compliance_rate_cnt,"
    "cfo_agency_indicator"
)

_SORT_FIELD_MAP = {
    "fiscal_year": "record_fiscal_year",
    "compliance_rate": "compliance_rate_amt",
    "eligible_debt": "total_eligible_debt_amt",
    "referred_debt": "eligible_debt_referred_amt",
    "record_date": "record_date",
}


def _build_filters(params: QueryReceivablesInput) -> list[str]:
    filters = []
    if params.agency_name:
        # Exact match on agency_nm — use list_agencies first to get the exact name
        filters.append(f"agency_nm:eq:{params.agency_name}")
    if params.fiscal_year:
        filters.append(f"record_fiscal_year:eq:{params.fiscal_year}")
    if params.fiscal_quarter:
        filters.append(f"record_fiscal_quarter:eq:{params.fiscal_quarter.value}")
    if not params.include_bureaus:
        filters.append("agency_bureau_indicator:eq:Agency")
    return filters


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        name="query_receivables",
        annotations={
            "title": "Query TROR DDR compliance data",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def query_receivables(
        params: Annotated[QueryReceivablesInput, "Filter, sort, and pagination options."]
    ) -> dict:
        """Query federal agency 120-day delinquent debt referral (DDR) compliance data
        from the Treasury Report on Receivables (TROR), sourced from the DATA Act
        compliance dataset on Fiscal Data.

        Returns eligible debt amounts, amounts referred vs not referred to
        cross-servicing/TOP, and compliance rates (both dollar-amount and count basis).

        Coverage: FY2016–present. Use list_agencies first to get the exact agency_name
        for filtering — partial matches are not supported.

        Fiscal quarters: Q1=Oct–Dec, Q2=Jan–Mar, Q3=Apr–Jun, Q4=Jul–Sep.

        Data source: Fiscal Data API (api.fiscaldata.treasury.gov), updated quarterly.
        Returns: { records: [...], total, has_more, next_offset, coverage_note }
        """
        filters = _build_filters(params)

        sort_field = _SORT_FIELD_MAP.get(params.sort_by, "record_fiscal_year")
        api_params: dict = {
            "fields": _FIELDS,
            "page[size]": params.limit,
            "page[number]": (params.offset // params.limit) + 1,
            "sort": f"{'-' if params.sort_order == 'desc' else ''}{sort_field}",
        }
        if filters:
            api_params["filter"] = ",".join(filters)

        raw = await fetch_fiscal(_TROR_PATH, api_params)

        if "error" in raw:
            return raw

        data = raw.get("data", [])
        meta = raw.get("meta", {})
        total = int(meta.get("total-count", len(data)))
        has_more = (params.offset + params.limit) < total

        records = []
        for row in data:
            record = {
                "fiscal_year": row.get("record_fiscal_year"),
                "fiscal_quarter": row.get("record_fiscal_quarter"),
                "record_date": row.get("record_date"),
                "agency_name": row.get("agency_nm"),
                "bureau_name": row.get("bureau_nm"),
                "level": row.get("agency_bureau_indicator"),  # "Agency" or "Bureau"
                "cfo_agency": row.get("cfo_agency_indicator"),
                "total_eligible_debt_usd": _to_float(row.get("total_eligible_debt_amt")),
                "total_eligible_debt_count": _to_int(row.get("total_eligible_debt_cnt")),
                "referred_debt_usd": _to_float(row.get("eligible_debt_referred_amt")),
                "referred_debt_count": _to_int(row.get("eligible_debt_referred_cnt")),
                "not_referred_debt_usd": _to_float(row.get("eligible_debt_not_referred_amt")),
                "not_referred_debt_count": _to_int(row.get("eligible_debt_not_referred_cnt")),
                "compliance_rate_by_amount_pct": _to_float(row.get("compliance_rate_amt")),
                "compliance_rate_by_count_pct": _to_float(row.get("compliance_rate_cnt")),
            }
            records.append(record)

        return {
            "records": records,
            "total": total,
            "returned": len(records),
            "has_more": has_more,
            "next_offset": params.offset + params.limit if has_more else None,
            "coverage_note": "FY2016–present. 120-day DDR compliance per DATA Act §5 requirements.",
            "freshness": "Updated quarterly, ~45–60 days after quarter close.",
        }


def _to_float(val) -> float | None:
    try:
        return float(val) if val not in (None, "null") else None
    except (TypeError, ValueError):
        return None


def _to_int(val) -> int | None:
    try:
        return int(float(val)) if val not in (None, "null") else None
    except (TypeError, ValueError):
        return None
