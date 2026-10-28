"""Ground-truth eval cases for the TRORBOT MCP server.

Each case pairs a real analyst question with:
  - the MCP tool call that answers it, plus an extractor that reads the answer
    from the tool's output, and
  - a ground-truth function that computes the same answer directly from a raw
    Fiscal Data API snapshot, independent of the server's code.

The snapshot (eval/fixtures/raw_snapshot.json) holds every agency-level TROR row
for FY2021 onward, plus the full list of agency names since FY2016.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

DOJ = "Department of Justice"
DOD = "Department of Defense"
SSA = "Social Security Administration"

Snapshot = dict[str, Any]


@dataclass(frozen=True)
class Case:
    id: str
    question: str
    tool: str
    args: dict
    extract: Callable[[dict], Any]
    ground_truth: Callable[[Snapshot], Any]


# ── ground-truth helpers (raw rows only — no server code) ───────────────


def _rows(snap: Snapshot, **match) -> list[dict]:
    return [r for r in snap["rows"] if all(str(r[k]) == str(v) for k, v in match.items())]


def _year_end(snap: Snapshot, agency: str, fy: int, field: str) -> float:
    """Q4 value for an agency-year (the window FY2021–FY2025 is fully published)."""
    (row,) = _rows(snap, agency_nm=agency, record_fiscal_year=fy, record_fiscal_quarter=4)
    return float(row[field])


def _cfo_agencies(snap: Snapshot) -> list[str]:
    return sorted({r["agency_nm"] for r in snap["rows"] if r["cfo_agency_indicator"] == "CFO"})


def _cfo_changes(snap: Snapshot) -> dict[str, float]:
    rate = "compliance_rate_amt"
    return {a: _year_end(snap, a, 2025, rate) - _year_end(snap, a, 2021, rate) for a in _cfo_agencies(snap)}


def _cfo_mean_series(snap: Snapshot) -> dict:
    series = []
    for fy in range(2021, 2026):
        values = [_year_end(snap, a, fy, "compliance_rate_amt") for a in _cfo_agencies(snap)]
        series.append({"fy": fy, "mean_rate": sum(values) / len(values)})
    change = series[-1]["mean_rate"] - series[0]["mean_rate"]
    return {"series": series, "direction": "up" if change > 0 else "down"}


# ── extractors (read the answer from tool output, as an agent would) ────


def _mover(out: dict, pick: Callable) -> dict:
    trend = pick(out["agency_trends"], key=lambda t: t["change_abs"])
    return {"agency": trend["agency_name"], "change_pct_points": trend["change_abs"]}


def _count_full_compliance(out: dict) -> int:
    assert not out["has_more"], "expected every FY2025 Q4 agency row in one page"
    return sum(1 for r in out["records"] if r["compliance_rate_by_amount_pct"] == 100)


CASES: list[Case] = [
    Case(
        id="agency_count",
        question="How many agencies have reported TROR delinquent-debt referral data since FY2016?",
        tool="list_agencies",
        args={"limit": 100},
        extract=lambda out: out["total"],
        ground_truth=lambda snap: len(snap["agency_names"]),
    ),
    Case(
        id="doj_fy2024_q4_rate",
        question="What was the Department of Justice's compliance rate in FY2024 Q4?",
        tool="query_receivables",
        args={"agency_name": DOJ, "fiscal_year": 2024, "fiscal_quarter": 4},
        extract=lambda out: out["records"][0]["compliance_rate_by_amount_pct"],
        ground_truth=lambda snap: _year_end(snap, DOJ, 2024, "compliance_rate_amt"),
    ),
    Case(
        id="cfo_largest_decline",
        question="Which CFO Act agency had the largest compliance rate decline from FY2021 to FY2025?",
        tool="get_delinquency_trends",
        args={"cfo_agencies_only": True, "fiscal_year_start": 2021, "fiscal_year_end": 2025, "top_n": 100},
        extract=lambda out: _mover(out, min),
        ground_truth=lambda snap: (
            lambda ch: {"agency": min(ch, key=ch.get), "change_pct_points": min(ch.values())}
        )(_cfo_changes(snap)),
    ),
    Case(
        id="cfo_largest_improvement",
        question="Which CFO Act agency had the largest compliance rate improvement from FY2021 to FY2025?",
        tool="get_delinquency_trends",
        args={"cfo_agencies_only": True, "fiscal_year_start": 2021, "fiscal_year_end": 2025, "top_n": 100},
        extract=lambda out: _mover(out, max),
        ground_truth=lambda snap: (
            lambda ch: {"agency": max(ch, key=ch.get), "change_pct_points": max(ch.values())}
        )(_cfo_changes(snap)),
    ),
    Case(
        id="ssa_series_2021_2025",
        question="What is SSA's year-by-year compliance rate from FY2021 to FY2025?",
        tool="get_delinquency_trends",
        args={"agency_name": SSA, "fiscal_year_start": 2021, "fiscal_year_end": 2025},
        extract=lambda out: [{"fy": p["fy"], "rate": p["value"]} for p in out["agency_trends"][0]["series"]],
        ground_truth=lambda snap: [
            {"fy": fy, "rate": _year_end(snap, SSA, fy, "compliance_rate_amt")} for fy in range(2021, 2026)
        ],
    ),
    Case(
        id="dod_fy2025_eligible_debt",
        question="What is the total eligible debt for the Department of Defense in FY2025 (year-end, Q4)?",
        tool="query_receivables",
        args={"agency_name": DOD, "fiscal_year": 2025, "fiscal_quarter": 4},
        extract=lambda out: out["records"][0]["total_eligible_debt_usd"],
        ground_truth=lambda snap: _year_end(snap, DOD, 2025, "total_eligible_debt_amt"),
    ),
    Case(
        id="full_compliance_fy2025_q4",
        question="How many agencies had 100% compliance (by dollar amount) in FY2025 Q4?",
        tool="query_receivables",
        args={"fiscal_year": 2025, "fiscal_quarter": 4, "limit": 100},
        extract=_count_full_compliance,
        ground_truth=lambda snap: sum(
            1 for r in _rows(snap, record_fiscal_year=2025, record_fiscal_quarter=4)
            if r["compliance_rate_amt"] not in (None, "null") and float(r["compliance_rate_amt"]) == 100
        ),
    ),
    Case(
        id="cfo_mean_rate_trend",
        question="What is the government-wide average compliance rate trend from FY2021 to FY2025 (CFO agencies)?",
        tool="get_delinquency_trends",
        args={"cfo_agencies_only": True, "fiscal_year_start": 2021, "fiscal_year_end": 2025, "top_n": 1},
        extract=lambda out: {
            "series": [{"fy": p["fy"], "mean_rate": p["mean_value"]} for p in out["government_wide"]["series"]],
            "direction": out["government_wide"]["direction"],
        },
        ground_truth=_cfo_mean_series,
    ),
]
