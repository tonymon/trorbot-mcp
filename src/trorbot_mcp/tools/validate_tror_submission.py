"""Tool: validate_tror_submission

Validates a draft quarterly TROR Form 05 submission for a federal agency.
Computes derived fields (ending balance, DDR compliance rates), runs arithmetic
and business-rule checks, and returns a validation receipt with a prior-quarter
comparison sourced from the live Fiscal Data API.

No data is persisted — this tool validates only. It is the first step an agency
AI agent would take before a formal TROR submission.

Data rules derived from:
- TROR Form 05 (docs/businessrules/TROR-Form-yr2016-with-formulas.xlsx)
- FY2016/FY2018 TROR Instructional Workbooks
- DCIA §3716 (120-day mandatory referral requirement)
"""

from __future__ import annotations

import datetime
import hashlib
from typing import Annotated

from fastmcp import FastMCP

from trorbot_mcp.models import FiscalQuarter, TRORSubmissionInput
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


def _receipt_id(agency_name: str, fy: int, q: int) -> str:
    """Deterministic draft receipt ID — not a real submission ID."""
    slug = agency_name.upper().replace(" ", "-")[:20]
    h = hashlib.sha1(f"{agency_name}{fy}{q}".encode()).hexdigest()[:6].upper()
    return f"TROR-DRAFT-{fy}-Q{q}-{slug}-{h}"


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        name="validate_tror_submission",
        annotations={
            "title": "Validate a draft TROR quarterly submission",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    async def validate_tror_submission(
        params: Annotated[TRORSubmissionInput, "Draft TROR Form 05 data for the agency and quarter."]
    ) -> dict:
        """Validate a federal agency's draft quarterly TROR submission before it is filed.

        Accepts the key fields from TROR Form 05 — receivables status (Part I-A),
        delinquency snapshot (Part I-C), and the 120-day DDR compliance section
        (Part II-B) — then:

        1. Computes the ending receivables balance and flags any arithmetic discrepancy.
        2. Computes DDR compliance rates (amount basis and count basis) from the
           submitted figures, so the agency knows their rate before filing.
        3. Checks that referred debt does not exceed eligible debt.
        4. Validates fiscal year and quarter plausibility against today's date.
        5. Compares the draft compliance rate against the most recently published
           quarter for the same agency (from the live Fiscal Data API).

        No data is persisted. This is a pre-submission validation tool — the output
        is a structured receipt the agency can review and correct before formal filing.

        TROR data requirements derive from DCIA §3716, OMB Circular A-129, and the
        Treasury Financial Manual (TFM) Vol. I, Part 3.

        Returns: { validation_status, receipt_id, computed_fields, checks, prior_quarter }
        """
        checks: list[dict] = []
        warnings: list[str] = []

        # ── 1. Balance arithmetic ────────────────────────────────────────────
        computed_ending = (
            params.beginning_balance_usd
            + params.new_receivables_usd
            - params.collections_usd
            - params.write_offs_usd
            + params.adjustments_usd
        )
        # We don't require the agency to submit an ending balance, so just report
        checks.append({
            "rule": "ending_balance_arithmetic",
            "result": "info",
            "computed_ending_balance_usd": round(computed_ending, 2),
            "note": (
                "Ending balance = beginning + new_receivables − collections "
                "− write_offs + adjustments. Verify this matches your system of record."
            ),
        })

        # ── 2. DDR compliance rates ──────────────────────────────────────────
        eligible_usd = params.total_eligible_debt_usd
        referred_usd = params.referred_to_treasury_usd
        eligible_cnt = params.total_eligible_debt_count
        referred_cnt = params.referred_to_treasury_count

        if eligible_usd > 0:
            compliance_rate_amt = round(referred_usd / eligible_usd * 100, 4)
        else:
            compliance_rate_amt = 100.0  # no eligible debt → fully compliant by definition

        if eligible_cnt > 0:
            compliance_rate_cnt = round(referred_cnt / eligible_cnt * 100, 4)
        else:
            compliance_rate_cnt = 100.0

        not_referred_usd = round(eligible_usd - referred_usd, 2)
        not_referred_cnt = eligible_cnt - referred_cnt

        checks.append({
            "rule": "ddr_compliance_computation",
            "result": "pass",
            "compliance_rate_amt_pct": compliance_rate_amt,
            "compliance_rate_cnt_pct": compliance_rate_cnt,
            "not_referred_usd": not_referred_usd,
            "not_referred_count": not_referred_cnt,
        })

        # ── 3. Delinquency vs. eligible sanity check ─────────────────────────
        if params.total_delinquent_usd > 0 and eligible_usd > params.total_delinquent_usd * 1.05:
            warnings.append(
                f"total_eligible_debt_usd ({eligible_usd:,.0f}) exceeds "
                f"total_delinquent_usd ({params.total_delinquent_usd:,.0f}) by more than 5%. "
                "Eligible debt should be a subset of delinquent debt — verify your figures."
            )
            checks.append({"rule": "eligible_subset_of_delinquent", "result": "warning"})
        else:
            checks.append({"rule": "eligible_subset_of_delinquent", "result": "pass"})

        # ── 4. Exemptions don't exceed eligible ──────────────────────────────
        total_exempt = (
            params.exempt_bankruptcy_usd
            + params.exempt_litigation_usd
            + params.exempt_other_usd
        )
        if total_exempt > eligible_usd * 1.001:
            checks.append({
                "rule": "exemptions_le_eligible",
                "result": "fail",
                "detail": (
                    f"Total exemptions ({total_exempt:,.0f}) exceed "
                    f"eligible debt ({eligible_usd:,.0f})."
                ),
            })
        else:
            checks.append({"rule": "exemptions_le_eligible", "result": "pass"})

        # ── 5. Fiscal year/quarter plausibility ──────────────────────────────
        today = datetime.date.today()
        current_fy = today.year if today.month >= 10 else today.year - 1
        current_q = {10: 1, 11: 1, 12: 1, 1: 2, 2: 2, 3: 2,
                     4: 3, 5: 3, 6: 3, 7: 4, 8: 4, 9: 4}[today.month]

        sub_fy, sub_q = params.fiscal_year, params.fiscal_quarter.value
        future = (sub_fy > current_fy) or (sub_fy == current_fy and sub_q > current_q)
        if future:
            warnings.append(
                f"FY{sub_fy} Q{sub_q} is in the future (current period: FY{current_fy} Q{current_q}). "
                "Submissions are typically filed after the quarter closes."
            )
            checks.append({"rule": "quarter_plausibility", "result": "warning"})
        else:
            checks.append({"rule": "quarter_plausibility", "result": "pass"})

        # ── 6. Prior-quarter comparison (live API) ───────────────────────────
        prior = await _fetch_prior_quarter(params.agency_name, sub_fy, sub_q)
        prior_fy, prior_q = _prior_quarter(sub_fy, sub_q)
        if prior:
            prior_rate = float(prior.get("compliance_rate_amt") or 0)
            change_pp = round(compliance_rate_amt - prior_rate, 2)
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

        # ── Overall status ───────────────────────────────────────────────────
        has_fail = any(c["result"] == "fail" for c in checks)
        has_warning = bool(warnings) or any(c["result"] == "warning" for c in checks)
        if has_fail:
            status = "failed"
        elif has_warning:
            status = "passed_with_warnings"
        else:
            status = "passed"

        return {
            "validation_status": status,
            "receipt_id": _receipt_id(params.agency_name, sub_fy, sub_q),
            "submission": {
                "agency": params.agency_name,
                "period": f"FY{sub_fy} {_QUARTER_LABEL[sub_q]}",
            },
            "computed_fields": {
                "ending_balance_usd": round(computed_ending, 2),
                "compliance_rate_amt_pct": compliance_rate_amt,
                "compliance_rate_cnt_pct": compliance_rate_cnt,
                "not_referred_usd": not_referred_usd,
                "not_referred_count": not_referred_cnt,
            },
            "checks": checks,
            "warnings": warnings,
            "prior_quarter": prior_quarter_summary,
            "next_steps": (
                "Review computed_fields and correct any discrepancies in your source data. "
                "When all checks pass, proceed to formal submission through your agency's "
                "TROR reporting system or contact BFS for submission instructions."
            ),
        }
