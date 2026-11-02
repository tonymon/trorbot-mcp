"""Pydantic input models for all TRORBOT MCP tools.

Validated inputs prevent bad API calls and give agents clear error messages
when they pass wrong types. Every field carries a description the model reads
when deciding how to populate the argument.
"""

from __future__ import annotations

from enum import Enum
from typing import Annotated

from pydantic import BaseModel, Field, field_validator, model_validator

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
    cfo_agencies_only: Annotated[
        bool,
        Field(description="Only return the 24 CFO Act agencies (the large agencies under Congressional oversight).")
    ] = False


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
    offset: Annotated[
        int,
        Field(ge=0, description="Zero-based record offset for pagination. Must be a multiple of limit.")
    ] = 0

    @model_validator(mode="after")
    def offset_page_aligned(self) -> "QueryReceivablesInput":
        # The Fiscal Data API pages by page number, so only page-aligned offsets are exact.
        if self.offset % self.limit != 0:
            raise ValueError(
                f"offset ({self.offset}) must be a multiple of limit ({self.limit}); "
                "use the next_offset value from the previous response"
            )
        return self


class DelinquencyTrendsInput(BaseModel):
    """Inputs for get_delinquency_trends."""
    fiscal_year_start: Annotated[
        int,
        Field(ge=2016, le=2029, description="Start of the trend window (inclusive).")
    ] = 2021
    fiscal_year_end: Annotated[
        int,
        Field(ge=2017, le=2030, description="End of the trend window (inclusive).")
    ] = 2025
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
        Field(
            ge=1, le=100,
            description="When agency_name is omitted, return only the top N agencies by change magnitude.",
        )
    ] = 10
    cfo_agencies_only: Annotated[
        bool,
        Field(description=(
            "Only include the 24 CFO Act agencies — the large agencies that receive "
            "Congressional oversight. Recommended for government-wide 'biggest movers' questions."
        ))
    ] = False
    min_eligible_debt_usd: Annotated[
        float | None,
        Field(ge=0, description=(
            "Drop agencies whose start-year total eligible debt is below this USD amount "
            "before ranking. Filters out small agencies whose rates swing 0↔100% on a few debts."
        ))
    ] = None

    @field_validator("fiscal_year_end")
    @classmethod
    def end_after_start(cls, v: int, info) -> int:
        start = info.data.get("fiscal_year_start", 2016)
        if v <= start:
            raise ValueError(f"fiscal_year_end ({v}) must be greater than fiscal_year_start ({start})")
        return v


class TRORSubmissionInput(BaseModel):
    """Inputs for validate_tror_submission.

    Covers the key sections of TROR Form 05 that drive DDR compliance analysis.
    Derived fields (ending balance, compliance rates) are computed and validated
    by the tool — do not compute them before submitting.
    """
    agency_name: Annotated[
        str,
        Field(
            min_length=2, max_length=200,
            description=(
                "Exact agency name as returned by list_agencies. "
                "Use list_agencies first if unsure of the exact name."
            ),
        ),
    ]
    fiscal_year: Annotated[
        int,
        Field(ge=2016, le=2030, description="Fiscal year of the submission (e.g. 2026)."),
    ]
    fiscal_quarter: Annotated[
        FiscalQuarter,
        Field(description="Fiscal quarter: 1=Oct–Dec, 2=Jan–Mar, 3=Apr–Jun, 4=Jul–Sep."),
    ]

    # Part I-A: Status of Receivables
    beginning_balance_usd: Annotated[
        float,
        Field(ge=0, description="Total receivables outstanding at the start of the quarter (USD)."),
    ]
    new_receivables_usd: Annotated[
        float,
        Field(ge=0, description="New receivables established during the quarter (USD)."),
    ]
    collections_usd: Annotated[
        float,
        Field(ge=0, description="Total collections received during the quarter (USD)."),
    ]
    write_offs_usd: Annotated[
        float,
        Field(ge=0, description="Amounts written off during the quarter (USD)."),
    ]
    adjustments_usd: Annotated[
        float,
        Field(description="Net adjustments during the quarter (USD). May be negative."),
    ] = 0.0

    # Part I-C: Delinquency snapshot
    total_delinquent_usd: Annotated[
        float,
        Field(ge=0, description="Total delinquent receivables at end of quarter (USD)."),
    ]

    # Part II-B: 120-Day DDR Compliance (the mandatory DCIA referral section)
    total_eligible_debt_usd: Annotated[
        float,
        Field(ge=0, description="Total debt eligible for 120-day referral to Cross-Servicing/TOP (USD)."),
    ]
    total_eligible_debt_count: Annotated[
        int,
        Field(ge=0, description="Number of eligible debt accounts."),
    ]
    referred_to_treasury_usd: Annotated[
        float,
        Field(ge=0, description="Eligible debt actually referred to Treasury Cross-Servicing or TOP (USD)."),
    ]
    referred_to_treasury_count: Annotated[
        int,
        Field(ge=0, description="Number of accounts referred to Treasury."),
    ]

    # Common exemptions (optional — include only what applies)
    exempt_bankruptcy_usd: Annotated[
        float,
        Field(ge=0, description="Debt exempt from referral because the debtor is in bankruptcy (USD)."),
    ] = 0.0
    exempt_litigation_usd: Annotated[
        float,
        Field(ge=0, description="Debt exempt from referral due to active litigation or enforcement action (USD)."),
    ] = 0.0
    exempt_other_usd: Annotated[
        float,
        Field(ge=0, description="Debt exempt for other approved reasons (USD)."),
    ] = 0.0

    @field_validator("referred_to_treasury_usd")
    @classmethod
    def referred_le_eligible(cls, v: float, info) -> float:
        eligible = info.data.get("total_eligible_debt_usd")
        if eligible is not None and v > eligible * 1.001:  # allow 0.1% rounding tolerance
            raise ValueError(
                f"referred_to_treasury_usd ({v:,.0f}) cannot exceed "
                f"total_eligible_debt_usd ({eligible:,.0f})"
            )
        return v

    @field_validator("referred_to_treasury_count")
    @classmethod
    def referred_count_le_eligible(cls, v: int, info) -> int:
        eligible = info.data.get("total_eligible_debt_count")
        if eligible is not None and v > eligible:
            raise ValueError(
                f"referred_to_treasury_count ({v}) cannot exceed "
                f"total_eligible_debt_count ({eligible})"
            )
        return v


class KBSearchInput(BaseModel):
    """Inputs for the Bedrock KB search tools.

    Used by search_program_context, search_program_guidance, and get_annual_report_insights.
    """
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
