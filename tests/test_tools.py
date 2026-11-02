"""Smoke tests — verify tools register and models validate without hitting live APIs."""

from datetime import date

import pytest

from trorbot_mcp.app import mcp
from trorbot_mcp.models import (
    DelinquencyTrendsInput,
    FiscalQuarter,
    ListAgenciesInput,
    QueryReceivablesInput,
    TRORSubmissionInput,
)
from trorbot_mcp.tools.validate_tror_submission import compute_form_lines, run_checks


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


# ── validate_tror_submission: inputs, Form 05 arithmetic, checks ─────────

_VALID_SUBMISSION = dict(
    agency_name="Department of Justice",
    fiscal_year=2025,
    fiscal_quarter=FiscalQuarter.Q4,
    beginning_fy_balance_usd=1_000_000.0,
    new_receivables_usd=200_000.0,
    accruals_usd=10_000.0,
    collections_usd=150_000.0,
    amounts_written_off_usd=50_000.0,
    total_delinquent={"usd": 300_000.0, "count": 120},
    delinquent_over_120_days={"usd": 250_000.0, "count": 100},
    currently_not_collectible={"usd": 20_000.0, "count": 10},
    ineligible_bankruptcy={"usd": 15_000.0, "count": 5},
    ineligible_forbearance_or_appeals={"usd": 5_000.0, "count": 3},
    exception_litigation={"usd": 10_000.0, "count": 2},
    referred_directly_to_top={"usd": 150_000.0, "count": 60},
    referred_to_top_via_cross_servicing={"usd": 54_000.0, "count": 20},
)
_TODAY = date(2026, 11, 2)


def _results(submission: dict) -> tuple[dict, dict]:
    p = TRORSubmissionInput(**submission)
    lines = compute_form_lines(p)
    return lines, {c["rule"]: c["result"] for c in run_checks(p, lines, _TODAY)}


def test_tror_submission_optional_lines_default_zero():
    p = TRORSubmissionInput(**_VALID_SUBMISSION)
    assert p.adjustments_usd == 0.0
    assert p.ineligible_foreclosure.usd == 0.0 and p.exception_foreign_sovereign.count == 0


def test_tror_submission_rejects_negative_amounts():
    with pytest.raises(Exception):
        TRORSubmissionInput(**{**_VALID_SUBMISSION, "ineligible_bankruptcy": {"usd": -1.0, "count": 0}})


def test_tror_submission_fy_below_2016():
    with pytest.raises(Exception):
        TRORSubmissionInput(**{**_VALID_SUBMISSION, "fiscal_year": 2015})


def test_tror_submission_agency_name_too_short():
    with pytest.raises(Exception):
        TRORSubmissionInput(**{**_VALID_SUBMISSION, "agency_name": "A"})


def test_form_lines_follow_form_05():
    lines, results = _results(_VALID_SUBMISSION)
    assert lines["ending_balance_usd"] == 1_010_000.0  # 1,000,000 + 200,000 + 10,000 − 150,000 − 50,000
    assert lines["total_over_120_and_cnc"] == {"usd": 270_000.0, "count": 110}  # 1C = 1A + 1B
    assert lines["eligible_for_offset"] == {"usd": 250_000.0, "count": 102}  # 1H = 1C − 1D…1G
    assert lines["required_to_be_referred"] == {"usd": 240_000.0, "count": 100}  # 1M = 1H − 1J…1L
    assert lines["referred_to_top"] == {"usd": 204_000.0, "count": 80}  # 1N + 1O
    assert lines["remaining_to_be_referred"] == {"usd": 36_000.0, "count": 20}  # 1P
    assert lines["compliance_rate_amt_pct"] == 85.0
    assert lines["compliance_rate_cnt_pct"] == 80.0
    assert set(results.values()) == {"pass"}


def test_cnc_debt_can_exceed_delinquent_without_failing():
    # Part I-C excludes CNC debt, Part II-B adds it back, so 1C can exceed total delinquent.
    lines, results = _results({**_VALID_SUBMISSION, "currently_not_collectible": {"usd": 400_000.0, "count": 50}})
    assert lines["total_over_120_and_cnc"]["usd"] > _VALID_SUBMISSION["total_delinquent"]["usd"]
    assert set(results.values()) == {"pass"}


def test_over_120_exceeding_total_delinquent_fails():
    _, results = _results({**_VALID_SUBMISSION, "delinquent_over_120_days": {"usd": 350_000.0, "count": 100}})
    assert results["over_120_within_total_delinquent"] == "fail"


def test_ineligible_exceeding_over_120_and_cnc_fails():
    _, results = _results({**_VALID_SUBMISSION, "ineligible_bankruptcy": {"usd": 300_000.0, "count": 5}})
    assert results["ineligible_within_over_120_and_cnc"] == "fail"


def test_referred_exceeding_required_fails():
    _, results = _results({**_VALID_SUBMISSION, "referred_directly_to_top": {"usd": 200_000.0, "count": 60}})
    assert results["referred_within_required"] == "fail"


def test_nothing_required_to_refer_reports_zero_rate_like_fiscal_data():
    empty = {"usd": 0.0, "count": 0}
    lines, _ = _results({**_VALID_SUBMISSION, "delinquent_over_120_days": empty, "currently_not_collectible": empty,
                         "ineligible_bankruptcy": empty, "ineligible_forbearance_or_appeals": empty,
                         "exception_litigation": empty, "referred_directly_to_top": empty,
                         "referred_to_top_via_cross_servicing": empty})
    assert lines["compliance_rate_amt_pct"] == 0.0 and lines["compliance_rate_cnt_pct"] == 0.0


def test_open_quarter_is_a_warning():
    _, results = _results({**_VALID_SUBMISSION, "fiscal_year": 2027, "fiscal_quarter": FiscalQuarter.Q1})
    assert results["quarter_has_closed"] == "warning"


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


@pytest.mark.parametrize(
    ("bureau", "level_filter"),
    [
        (None, "agency_bureau_indicator:eq:Agency"),
        ("Bureau of the Fiscal Service", "agency_bureau_indicator:eq:Bureau,bureau_nm:eq:Bureau of the Fiscal Service"),
    ],
)
async def test_prior_quarter_compares_at_the_drafts_level(monkeypatch, bureau, level_filter):
    from trorbot_mcp.tools import validate_tror_submission as tool

    seen = {}

    async def fake_fetch(path, params):
        seen.update(params)
        return {"data": []}

    monkeypatch.setattr(tool, "fetch_fiscal", fake_fetch)
    assert await tool._fetch_prior_quarter("Department of the Treasury", bureau, 2026, 4) is None
    assert seen["filter"].endswith(level_filter)
    assert "record_fiscal_year:eq:2026,record_fiscal_quarter:eq:3" in seen["filter"]
