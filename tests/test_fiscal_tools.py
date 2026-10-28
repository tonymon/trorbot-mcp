"""Behavioral tests for the Fiscal Data tools, replayed from recorded API responses."""

from __future__ import annotations

import httpx
import pytest

from tests.conftest import TROR_URL, call
from trorbot_mcp.utils import fetch_fiscal

# ── list_agencies ───────────────────────────────────────────────────────


async def test_list_agencies_reads_every_page(client, replay):
    route = replay("list_agencies_all")
    out = await call(client, "list_agencies", {"limit": 100})

    assert route.call_count > 1
    assert out["total"] == 71
    names = {a["agency_name"] for a in out["agencies"]}
    # Late-alphabet agencies were missing when only the first page was read.
    assert {"Department of the Treasury", "Department of Veterans Affairs"} <= names


async def test_list_agencies_search_and_paging(client, replay):
    replay("list_agencies_all")
    out = await call(client, "list_agencies", {"search": "veterans", "limit": 100})
    assert {a["agency_name"] for a in out["agencies"]} == {
        "Department of Veterans Affairs",
        "U.S. Court of Appeals / Veterans Claims",
    }

    first = await call(client, "list_agencies", {"limit": 50})
    assert first["has_more"] is True and first["next_offset"] == 50
    second = await call(client, "list_agencies", {"limit": 50, "offset": 50})
    assert second["returned"] == 21 and second["has_more"] is False


async def test_list_agencies_cfo_only(client, replay):
    replay("list_agencies_cfo")
    out = await call(client, "list_agencies", {"cfo_agencies_only": True, "limit": 100})
    assert out["total"] == 24
    assert all(a["cfo_agency"] for a in out["agencies"])
    assert "Small Business Administration" in {a["agency_name"] for a in out["agencies"]}


# ── get_delinquency_trends ──────────────────────────────────────────────


async def test_trends_govwide_covers_all_agencies(client, replay):
    route = replay("trends_govwide_default")
    out = await call(client, "get_delinquency_trends", {"top_n": 20})

    assert route.call_count > 5  # > 1,000 rows: the old cap would have truncated here
    assert out["window"] == "FY2021–FY2025"
    assert out["agencies_analyzed"] == 70
    assert len(out["agency_trends"]) == 20


async def test_trends_uses_q4_else_latest_quarter(client, replay):
    replay("trends_doj_2021_2026")
    out = await call(
        client,
        "get_delinquency_trends",
        {"agency_name": "Department of Justice", "fiscal_year_start": 2021, "fiscal_year_end": 2026},
    )
    series = {s["fy"]: s for s in out["agency_trends"][0]["series"]}

    assert series[2023] == {"fy": 2023, "quarter": 4, "value": 98.6437}  # Q4, not Q1 (97.28)
    assert series[2026]["quarter"] == 3  # FY2026 Q4 not yet published
    assert out["agency_trends"][0]["end_value"] == series[2026]["value"]


async def test_trends_keeps_real_zero_start_value(client, fiscal_api):
    rows = [
        {"agency_nm": "Agency Z", "record_fiscal_year": str(fy), "record_fiscal_quarter": "4",
         "compliance_rate_amt": val}
        for fy, val in [(2021, "0"), (2022, "40"), (2023, "80")]
    ]
    fiscal_api.get(TROR_URL).respond(json={"data": rows, "meta": {"total-count": 3, "total-pages": 1}})

    out = await call(client, "get_delinquency_trends", {"fiscal_year_start": 2021, "fiscal_year_end": 2023})
    trend = out["agency_trends"][0]

    assert trend["start_value"] == 0.0  # previously fell through to the wrong year
    assert trend["change_abs"] == 80.0
    assert trend["change_pct"] is None  # undefined from a zero base


async def test_trends_failed_page_returns_error_not_partial(client, fiscal_api):
    page1 = {"data": [{"agency_nm": "A", "record_fiscal_year": "2021", "record_fiscal_quarter": "4",
                       "compliance_rate_amt": "50"}], "meta": {"total-count": 2, "total-pages": 2}}
    fiscal_api.get(TROR_URL).mock(side_effect=[httpx.Response(200, json=page1), httpx.Response(503)])

    out = await call(client, "get_delinquency_trends", {})
    assert out == {"error": "Fiscal Data API returned 503", "hint": "Check agency_name or fiscal_year filters."}


# ── query_receivables ───────────────────────────────────────────────────


async def test_query_receivables_doj_fy2023(client, replay):
    replay("query_doj_fy2023")
    out = await call(client, "query_receivables", {"agency_name": "Department of Justice", "fiscal_year": 2023})

    q4 = next(r for r in out["records"] if r["fiscal_quarter"] == "4")
    assert q4["total_eligible_debt_usd"] == 119_280_551
    assert q4["referred_debt_usd"] == 117_662_785
    assert q4["compliance_rate_by_amount_pct"] == pytest.approx(98.6437, abs=1e-4)
    assert out["total"] == 4


async def test_query_receivables_rejects_unaligned_offset(client):
    result = await client.call_tool("query_receivables", {"params": {"offset": 5, "limit": 10}},
                                    raise_on_error=False)
    assert result.is_error
    assert "multiple of limit" in result.content[0].text


# ── HTTP helper safety ──────────────────────────────────────────────────


async def test_unexpected_errors_are_sanitized(fiscal_api):
    fiscal_api.get(TROR_URL).mock(side_effect=httpx.ConnectError("secret-host.internal:443 refused"))
    out = await fetch_fiscal("/v2/debt/tror/data_act_compliance")
    assert out == {"error": "Fiscal Data API request failed", "hint": "Try again shortly."}
    assert "secret-host" not in str(out)


@pytest.mark.parametrize("path", ["https://evil.example/x", "//evil.example/x", "/v2/../../x", "v2/no-slash"])
async def test_fetch_rejects_non_relative_paths(path):
    with pytest.raises(ValueError):
        await fetch_fiscal(path)


# ── get_delinquency_trends filters ──────────────────────────────────────


def _trend_rows(agency: str, eligible: str, rates: list[str]) -> list[dict]:
    return [
        {"agency_nm": agency, "record_fiscal_year": str(2021 + i), "record_fiscal_quarter": "4",
         "compliance_rate_amt": rate, "total_eligible_debt_amt": eligible,
         "eligible_debt_referred_amt": str(float(eligible) * float(rate) / 100)}
        for i, rate in enumerate(rates)
    ]


async def test_trends_cfo_filter_is_sent_to_api(client, fiscal_api):
    route = fiscal_api.get(TROR_URL).respond(json={
        "data": _trend_rows("Big Dept", "1000000", ["90", "95"]), "meta": {"total-pages": 1},
    })
    out = await call(client, "get_delinquency_trends",
                     {"cfo_agencies_only": True, "fiscal_year_start": 2021, "fiscal_year_end": 2022})

    assert "cfo_agency_indicator:eq:CFO" in route.calls.last.request.url.params["filter"]
    assert out["filters"]["cfo_agencies_only"] is True


async def test_trends_min_eligible_debt_drops_small_agencies(client, fiscal_api):
    rows = _trend_rows("Big Dept", "5000000000", ["90", "80"]) + _trend_rows("Tiny Board", "1200", ["100", "0"])
    fiscal_api.get(TROR_URL).respond(json={"data": rows, "meta": {"total-pages": 1}})

    out = await call(client, "get_delinquency_trends",
                     {"min_eligible_debt_usd": 1_000_000, "fiscal_year_start": 2021, "fiscal_year_end": 2022})

    assert [t["agency_name"] for t in out["agency_trends"]] == ["Big Dept"]
    assert out["filters"]["excluded_below_threshold"] == 1
    assert out["agencies_analyzed"] == 1


async def test_trends_government_wide_mean_and_dollar_weighted(client, fiscal_api):
    rows = _trend_rows("Big Dept", "9000", ["90", "90"]) + _trend_rows("Small Dept", "1000", ["50", "70"])
    fiscal_api.get(TROR_URL).respond(json={"data": rows, "meta": {"total-pages": 1}})

    out = await call(client, "get_delinquency_trends", {"fiscal_year_start": 2021, "fiscal_year_end": 2022})
    fy2021, fy2022 = out["government_wide"]["series"]

    assert fy2021["mean_value"] == 70.0  # (90 + 50) / 2
    assert fy2021["dollar_weighted_value"] == 86.0  # (8100 + 500) / 10000
    assert fy2022["mean_value"] == 80.0
    assert out["government_wide"]["direction"] == "up"
