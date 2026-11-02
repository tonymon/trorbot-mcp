"""Tool: validate_tror_submission

Validates a draft quarterly TROR Form 05 submission for a federal agency.
Computes the form's derived lines (ending balance, debt eligible for and required to
be referred to the Treasury Offset Program, compliance rates), runs consistency checks,
and returns a validation receipt with a prior-quarter comparison sourced from the live
Fiscal Data API.

No data is persisted — this tool validates only. It is the first step an agency
AI agent would take before a formal TROR submission.

Data rules derived from:
- TROR Form 05 (FY2016 form with formulas): Part I-A line 7, Part II-B lines 1C, 1H, 1M, 1P
- FY2016/FY2018 TROR Instructional Workbooks
- DATA Act of 2014 (referral to the Treasury Offset Program at 120 days delinquent)

Compliance rate = debt referred to TOP (lines 1N + 1O) ÷ debt required to be referred
(line 1M). Fiscal Data's data_act_compliance dataset publishes the same split as
eligible, referred, and not referred.
"""

from __future__ import annotations

import datetime
import hashlib
from typing import Annotated

from fastmcp import FastMCP

from trorbot_mcp.models import FormLine, TRORSubmissionInput
from trorbot_mcp.resources.fiscal_year_metadata import _fiscal_year
from trorbot_mcp.utils import fetch_fiscal

_TROR_PATH = "/v2/debt/tror/data_act_compliance"

# Quarter labels for human-readable output
_QUARTER_LABEL = {1: "Q1 (Oct–Dec)", 2: "Q2 (Jan–Mar)", 3: "Q3 (Apr–Jun)", 4: "Q4 (Jul–Sep)"}

# Prior quarter lookup: (fy, q) -> (prior_fy, prior_q)
def _prior_quarter(fy: int, q: int) -> tuple[int, int]:
    if q == 1:
        return fy - 1, 4
    return fy, q - 1


async def _fetch_prior_quarter(agency_name: str, fy: int, q: int) -> dict | None:
    """Fetch the most recent published DDR record for comparison."""
    prior_fy, prior_q = _prior_quarter(fy, q)
    params = {
        "page[size]": 1,
        "fields": (
            "compliance_rate_amt,compliance_rate_cnt,"
            "total_eligible_debt_amt,eligible_debt_referred_amt,"
            "record_fiscal_year,record_fiscal_quarter"
        ),
        "filter": (
            f"agency_nm:eq:{agency_name},"
            f"record_fiscal_year:eq:{prior_fy},"
            f"record_fiscal_quarter:eq:{prior_q},"
            "agency_bureau_indicator:eq:Agency"
        ),
    }
    raw = await fetch_fiscal(_TROR_PATH, params)
    data = raw.get("data", [])
    return data[0] if data else None


def _current_period(today: datetime.date) -> tuple[int, int]:
    """(fiscal_year, quarter) containing today. FY2027 Q1 = Oct–Dec 2026."""
    return _fiscal_year(today), (today.month - 10) % 12 // 3 + 1


def _receipt_id(agency_name: str, fy: int, q: int) -> str:
    """Deterministic draft receipt ID — not a real submission ID."""
    slug = agency_name.upper().replace(" ", "-")[:20]
    h = hashlib.sha1(f"{agency_name}{fy}{q}".encode()).hexdigest()[:6].upper()
    return f"TROR-DRAFT-{fy}-Q{q}-{slug}-{h}"


def _line(usd: float, count: int) -> dict:
    return {"usd": round(usd, 2), "count": count}


def _rate(part: float, whole: float) -> float:
    # Fiscal Data publishes 0.0 when nothing is eligible; match it.
    return round(part / whole * 100, 4) if whole > 0 else 0.0


def compute_form_lines(p: TRORSubmissionInput) -> dict:
    """Compute TROR Form 05's derived lines from the submitted lines."""

    def total(*lines: FormLine) -> tuple[float, int]:
        return sum(ln.usd for ln in lines), sum(ln.count for ln in lines)

    ending = (
        p.beginning_fy_balance_usd + p.new_receivables_usd + p.accruals_usd
        - p.collections_usd + p.adjustments_usd - p.amounts_written_off_usd
    )
    c_usd, c_cnt = total(p.delinquent_over_120_days, p.currently_not_collectible)            # 1C
    inel_usd, inel_cnt = total(p.ineligible_bankruptcy, p.ineligible_forbearance_or_appeals,
                               p.ineligible_foreclosure, p.ineligible_other)
    exc_usd, exc_cnt = total(p.exception_foreign_sovereign, p.exception_litigation, p.exception_other)
    h_usd, h_cnt = c_usd - inel_usd, c_cnt - inel_cnt                                         # 1H
    m_usd, m_cnt = h_usd - exc_usd, h_cnt - exc_cnt                                           # 1M
    ref_usd, ref_cnt = total(p.referred_directly_to_top, p.referred_to_top_via_cross_servicing)  # 1N + 1O
    return {
        "ending_balance_usd": round(ending, 2),
        "total_over_120_and_cnc": _line(c_usd, c_cnt),
        "eligible_for_offset": _line(h_usd, h_cnt),
        "required_to_be_referred": _line(m_usd, m_cnt),
        "referred_to_top": _line(ref_usd, ref_cnt),
        "remaining_to_be_referred": _line(m_usd - ref_usd, m_cnt - ref_cnt),
        "compliance_rate_amt_pct": _rate(ref_usd, m_usd),
        "compliance_rate_cnt_pct": _rate(ref_cnt, m_cnt),
    }


def run_checks(p: TRORSubmissionInput, lines: dict, today: datetime.date) -> list[dict]:
    """Consistency checks on the draft. Each check: rule, result (pass|fail|warning), detail."""
    checks: list[dict] = []

    def check(rule: str, ok: bool, detail: str, failure: str = "fail") -> None:
        checks.append({"rule": rule, "result": "pass" if ok else failure, "detail": detail})

    check("ending_balance_not_negative", lines["ending_balance_usd"] >= 0,
          "Part I-A line 7 = beginning FY balance + new receivables + accruals − collections "
          "± adjustments − amounts written off. Verify it matches your system of record.")
    over, delinquent = p.delinquent_over_120_days, p.total_delinquent
    check("over_120_within_total_delinquent",
          over.usd <= delinquent.usd * 1.001 and over.count <= delinquent.count,
          "Part II-B line 1A (debt over 120 days) is a subset of Part I-C total delinquencies.")
    eligible, required = lines["eligible_for_offset"], lines["required_to_be_referred"]
    check("ineligible_within_over_120_and_cnc", eligible["usd"] >= 0 and eligible["count"] >= 0,
          "Ineligible debt (lines 1D–1G) can't exceed debt over 120 days plus CNC (line 1C).")
    check("exceptions_within_eligible", required["usd"] >= 0 and required["count"] >= 0,
          "Exceptions (lines 1J–1L) can't exceed the debt eligible for offset (line 1H).")
    remaining = lines["remaining_to_be_referred"]
    check("referred_within_required", remaining["usd"] >= -0.01 and remaining["count"] >= 0,
          "Debt referred to TOP (lines 1N + 1O) can't exceed debt required to be referred (line 1M).")
    current_fy, current_q = _current_period(today)
    check("quarter_has_closed", (p.fiscal_year, p.fiscal_quarter.value) < (current_fy, current_q),
          f"Submissions are filed after the quarter closes. Current period: FY{current_fy} Q{current_q}.",
          failure="warning")
    return checks


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        name="validate_tror_submission",
        annotations={
            "title": "Validate a draft TROR quarterly submission",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def validate_tror_submission(
        params: Annotated[TRORSubmissionInput, "Draft TROR Form 05 lines for the agency and quarter."]
    ) -> dict:
        """Validate a federal agency's draft quarterly TROR submission before it is filed.

        Takes the TROR Form 05 lines that drive referral compliance: Part I-A
        (receivables and collections, fiscal-year-to-date), the Part I-C delinquency
        total, and Part II-B section 1 (debt eligible for referral to the Treasury
        Offset Program at 120 days, with ineligible debt, exceptions, and debt referred).
        Enter every amount as a positive figure; the tool applies the form's signs.

        It then:
        1. Computes the form's derived lines: ending balance (Part I-A line 7), debt
           eligible for offset (1H), debt required to be referred (1M), and the balance
           remaining to be referred (1P).
        2. Computes the compliance rate, referred ÷ required, on a dollar and an
           account basis: the same measure Treasury publishes on Fiscal Data.
        3. Checks the lines for consistency and that the quarter has closed.
        4. Compares the draft rate with the agency's last published quarter (live API).

        No data is persisted. The output is a receipt the agency can review and
        correct before formal filing.

        Returns: { validation_status, receipt_id, computed_lines, checks, prior_quarter }
        """
        lines = compute_form_lines(params)
        checks = run_checks(params, lines, datetime.date.today())

        sub_fy, sub_q = params.fiscal_year, params.fiscal_quarter.value
        prior = await _fetch_prior_quarter(params.agency_name, sub_fy, sub_q)
        prior_fy, prior_q = _prior_quarter(sub_fy, sub_q)
        if prior:
            prior_rate = float(prior.get("compliance_rate_amt") or 0)
            change_pp = round(lines["compliance_rate_amt_pct"] - prior_rate, 2)
            direction = "improvement" if change_pp > 0.05 else ("decline" if change_pp < -0.05 else "no change")
            prior_quarter_summary = {
                "found": True,
                "period": f"FY{prior_fy} Q{prior_q}",
                "published_compliance_rate_amt_pct": round(prior_rate, 4),
                "draft_vs_prior_change_pp": change_pp,
                "direction": direction,
            }
        else:
            prior_quarter_summary = {
                "found": False,
                "period": f"FY{prior_fy} Q{prior_q}",
                "note": (
                    "No published data found for the prior quarter. "
                    "This may be a new reporting agency or data not yet published."
                ),
            }

        results = {c["result"] for c in checks}
        status = "failed" if "fail" in results else ("passed_with_warnings" if "warning" in results else "passed")

        return {
            "validation_status": status,
            "receipt_id": _receipt_id(params.agency_name, sub_fy, sub_q),
            "submission": {
                "agency": params.agency_name,
                "period": f"FY{sub_fy} {_QUARTER_LABEL[sub_q]}",
            },
            "computed_lines": lines,
            "checks": checks,
            "prior_quarter": prior_quarter_summary,
            "next_steps": (
                "Review computed_lines and correct any discrepancies in your source data. "
                "When all checks pass, proceed to formal submission through your agency's "
                "TROR reporting system or contact BFS for submission instructions."
            ),
        }
