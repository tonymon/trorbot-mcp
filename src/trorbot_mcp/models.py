"""Pydantic input models for all TRORBOT MCP tools.

Validated inputs prevent bad API calls and give agents clear error messages
when they pass wrong types. Every field carries a description the model reads
when deciding how to populate the argument.
"""

from __future__ import annotations

from enum import Enum
from typing import Annotated

from pydantic import BaseModel, Field, field_validator


# ── enums ──────────────────────────────────────────────────────────────

class FiscalQuarter(int, Enum):
    Q1 = 1
    Q2 = 2
    Q3 = 3
    Q4 = 4


class SortOrder(str, Enum):
    asc = "asc"
    desc = "desc"


class TrendMetric(str, Enum):
    compliance_rate = "compliance_rate"         # % of eligible debt referred (amount basis)
    eligible_debt = "eligible_debt"             # total debt eligible for 120-day referral
    referred_debt = "referred_debt"             # debt actually referred to cross-servicing/TOP
    not_referred_debt = "not_referred_debt"     # debt NOT referred (inverse of compliance)


# ── shared pagination ───────────────────────────────────────────────────

class PaginationParams(BaseModel):
    limit: Annotated[int, Field(ge=1, le=100, description="Number of records to return (1–100).")] = 20
    offset: Annotated[int, Field(ge=0, description="Zero-based record offset for pagination.")] = 0


# ── tool input models ───────────────────────────────────────────────────

class ListAgenciesInput(PaginationParams):
    """Inputs for list_agencies."""
    search: Annotated[
        str | None,
        Field(description="Optional substring filter on agency name or code (case-insensitive).")
    ] = None
    has_data_since_fy: Annotated[
        int | None,
        Field(ge=1999, le=2030, description="Only return agencies that have reported TROR data since this fiscal year.")
    ] = None


class QueryReceivablesInput(PaginationParams):
    """Inputs for query_receivables."""
    agency_name: Annotated[
        str | None,
        Field(
            min_length=2, max_length=200,
            description=(
                "Exact agency name as returned by list_agencies "
                "(e.g. 'Department of Justice'). Case-sensitive exact match."
            )
        )
    ] = None
    fiscal_year: Annotated[
        int | None,
        Field(ge=2016, le=2030, description="Fiscal year (2016–present). TROR data starts FY2016.")
    ] = None
    fiscal_quarter: Annotated[
        FiscalQuarter | None,
        Field(description="Fiscal quarter: 1=Oct–Dec, 2=Jan–Mar, 3=Apr–Jun, 4=Jul–Sep.")
    ] = None
    include_bureaus: Annotated[
        bool,
        Field(description="Include bureau-level rows in addition to agency-level rows. Default false.")
    ] = False
    sort_by: Annotated[
        str,
        Field(description=(
            "Field to sort by: 'fiscal_year' (default), 'compliance_rate', "
            "'eligible_debt', 'referred_debt', 'record_date'."
        ))
    ] = "fiscal_year"
    sort_order: Annotated[SortOrder, Field(description="Sort direction.")] = SortOrder.desc


class DelinquencyTrendsInput(BaseModel):
    """Inputs for get_delinquency_trends."""
    fiscal_year_start: Annotated[
        int,
        Field(ge=2016, le=2029, description="Start of the trend window (inclusive).")
    ] = 2020
    fiscal_year_end: Annotated[
        int,
        Field(ge=2017, le=2030, description="End of the trend window (inclusive).")
    ] = 2024
    agency_name: Annotated[
        str | None,
        Field(description="Exact agency name from list_agencies. Omit for government-wide trend.")
    ] = None
    metric: Annotated[
        TrendMetric,
        Field(description=(
            "Which metric to trend: compliance_rate (default), eligible_debt, "
            "referred_debt, or not_referred_debt."
        ))
    ] = TrendMetric.compliance_rate
    top_n: Annotated[
        int,
        Field(ge=1, le=20, description="When agency_code is omitted, return only the top N agencies by change magnitude.")
    ] = 10

    @field_validator("fiscal_year_end")
    @classmethod
    def end_after_start(cls, v: int, info) -> int:
        start = info.data.get("fiscal_year_start", 2016)
        if v <= start:
            raise ValueError(f"fiscal_year_end ({v}) must be greater than fiscal_year_start ({start})")
        return v


class KBSearchInput(BaseModel):
    """Inputs for Bedrock KB search tools (search_program_context, search_program_guidance, get_annual_report_insights)."""
    query: Annotated[
        str,
        Field(
            min_length=5, max_length=500,
            description="Plain-language question or search phrase. Be specific for better results."
        )
    ]
    max_results: Annotated[
        int,
        Field(ge=1, le=10, description="Maximum number of source passages to return.")
    ] = 5
