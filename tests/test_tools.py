"""Smoke tests — verify tools register and models validate without hitting live APIs."""

import pytest
from trorbot_mcp.app import mcp
from trorbot_mcp.models import (
    DelinquencyTrendsInput,
    ListAgenciesInput,
    QueryReceivablesInput,
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


def test_delinquency_trends_defaults():
    p = DelinquencyTrendsInput()
    assert p.fiscal_year_start == 2020
    assert p.fiscal_year_end == 2024
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
