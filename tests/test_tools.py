"""Smoke tests — verify tools register and models validate without hitting live APIs."""

import pytest

from trorbot_mcp.app import mcp
from trorbot_mcp.models import (
    DelinquencyTrendsInput,
    FiscalQuarter,
    ListAgenciesInput,
    QueryReceivablesInput,
    TRORSubmissionInput,
)


async def test_all_tools_registered():
    tool_names = {t.name for t in await mcp.list_tools()}
    expected = {
        "list_agencies",
        "query_receivables",
        "get_delinquency_trends",
        "search_program_context",
        "search_program_guidance",
        "get_annual_report_insights",
        "validate_tror_submission",
    }
    assert expected == tool_names


async def test_all_prompts_registered():
    prompt_names = {p.name for p in await mcp.list_prompts()}
    assert "analyze_agency_performance" in prompt_names
    assert "explain_collection_program" in prompt_names


async def test_fiscal_year_resource_registered():
    resource_uris = {str(r.uri) for r in await mcp.list_resources()}
    assert "trorbot://fiscal-year-metadata" in resource_uris


# ── model validation ────────────────────────────────────────────────────

def test_list_agencies_defaults():
    p = ListAgenciesInput()
    assert p.limit == 20
    assert p.offset == 0


def test_query_receivables_agency_name_accepted():
    p = QueryReceivablesInput(agency_name="Department of Justice")
    assert p.agency_name == "Department of Justice"


def test_query_receivables_fiscal_year_bounds():
    with pytest.raises(Exception):
        QueryReceivablesInput(fiscal_year=2015)  # pre-coverage


def test_delinquency_trends_end_must_exceed_start():
    with pytest.raises(Exception):
        DelinquencyTrendsInput(fiscal_year_start=2022, fiscal_year_end=2021)


def test_delinquency_trends_same_year_invalid():
    with pytest.raises(Exception):
        DelinquencyTrendsInput(fiscal_year_start=2022, fiscal_year_end=2022)


def test_query_receivables_offset_must_be_page_aligned():
    QueryReceivablesInput(offset=20, limit=10)
    with pytest.raises(Exception):
        QueryReceivablesInput(offset=5, limit=10)


def test_delinquency_trends_defaults():
    p = DelinquencyTrendsInput()
    assert p.fiscal_year_start == 2021
    assert p.fiscal_year_end == 2025
    assert p.metric.value == "compliance_rate"
    assert p.top_n == 10
    assert p.agency_name is None


def test_delinquency_trends_agency_name():
    p = DelinquencyTrendsInput(agency_name="Department of Defense", fiscal_year_start=2020, fiscal_year_end=2024)
    assert p.agency_name == "Department of Defense"


def test_kb_search_input_length_bounds():
    from trorbot_mcp.models import KBSearchInput
    with pytest.raises(Exception):
        KBSearchInput(query="hi")  # too short (< 5 chars)


def test_kb_search_input_valid():
    from trorbot_mcp.models import KBSearchInput
    p = KBSearchInput(query="What is the 120-day referral rule?")
    assert p.max_results == 5


# ── TRORSubmissionInput validation ──────────────────────────────────────

_VALID_SUBMISSION = dict(
    agency_name="Department of Justice",
    fiscal_year=2025,
    fiscal_quarter=FiscalQuarter.Q4,
    beginning_balance_usd=1_000_000.0,
    new_receivables_usd=200_000.0,
    collections_usd=150_000.0,
    write_offs_usd=50_000.0,
    adjustments_usd=0.0,
    total_delinquent_usd=300_000.0,
    total_eligible_debt_usd=250_000.0,
    total_eligible_debt_count=100,
    referred_to_treasury_usd=200_000.0,
    referred_to_treasury_count=80,
)


def test_tror_submission_valid():
    p = TRORSubmissionInput(**_VALID_SUBMISSION)
    assert p.agency_name == "Department of Justice"
    assert p.fiscal_quarter == FiscalQuarter.Q4


def test_tror_submission_referred_exceeds_eligible_usd():
    bad = {**_VALID_SUBMISSION, "referred_to_treasury_usd": 300_000.0}
    with pytest.raises(Exception, match="cannot exceed"):
        TRORSubmissionInput(**bad)


def test_tror_submission_referred_count_exceeds_eligible():
    bad = {**_VALID_SUBMISSION, "referred_to_treasury_count": 101}
    with pytest.raises(Exception, match="cannot exceed"):
        TRORSubmissionInput(**bad)


def test_tror_submission_fy_below_2016():
    bad = {**_VALID_SUBMISSION, "fiscal_year": 2015}
    with pytest.raises(Exception):
        TRORSubmissionInput(**bad)


def test_tror_submission_exemptions_default_zero():
    p = TRORSubmissionInput(**_VALID_SUBMISSION)
    assert p.exempt_bankruptcy_usd == 0.0
    assert p.exempt_litigation_usd == 0.0
    assert p.exempt_other_usd == 0.0


def test_tror_submission_adjustments_default_zero():
    p = TRORSubmissionInput(**_VALID_SUBMISSION)
    assert p.adjustments_usd == 0.0


def test_tror_submission_agency_name_too_short():
    bad = {**_VALID_SUBMISSION, "agency_name": "A"}
    with pytest.raises(Exception):
        TRORSubmissionInput(**bad)


def test_latest_complete_fy_allows_for_publication_lag(monkeypatch):
    from datetime import date

    from trorbot_mcp.resources import fiscal_year_metadata as meta

    class FakeDate(date):
        today_value = date(2026, 10, 28)

        @classmethod
        def today(cls):
            return cls.today_value

    monkeypatch.setattr(meta, "date", FakeDate)
    assert meta._current_fiscal_year() == 2027
    assert meta._latest_complete_fiscal_year() == 2025  # FY2026 Q4 not yet published
    FakeDate.today_value = date(2026, 12, 15)
    assert meta._latest_complete_fiscal_year() == 2026


@pytest.mark.parametrize(
    ("today", "expected"),
    [
        ((2026, 10, 1), (2027, 1)),
        ((2026, 11, 2), (2027, 1)),
        ((2026, 12, 31), (2027, 1)),
        ((2027, 1, 1), (2027, 2)),
        ((2027, 4, 15), (2027, 3)),
        ((2027, 9, 30), (2027, 4)),
    ],
)
def test_validate_submission_current_period(today, expected):
    from datetime import date

    from trorbot_mcp.tools.validate_tror_submission import _current_period

    assert _current_period(date(*today)) == expected
