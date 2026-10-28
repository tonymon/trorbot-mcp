"""Tool: get_delinquency_trends

Computes year-over-year trends in DDR compliance metrics across federal agencies.
Fetches multi-year data from the Fiscal Data API, groups by agency and fiscal year,
and returns ranked trend summaries showing which agencies improved or declined the most.

Data source: Fiscal Data API — api.fiscaldata.treasury.gov
Endpoint: /v2/debt/tror/data_act_compliance
Coverage: FY2016–present
"""

from __future__ import annotations

from typing import Annotated

from fastmcp import FastMCP

from trorbot_mcp.models import DelinquencyTrendsInput, TrendMetric
from trorbot_mcp.utils import fetch_fiscal_all

_TROR_PATH = "/v2/debt/tror/data_act_compliance"

_METRIC_FIELD: dict[str, str] = {
    TrendMetric.compliance_rate: "compliance_rate_amt",
    TrendMetric.eligible_debt: "total_eligible_debt_amt",
    TrendMetric.referred_debt: "eligible_debt_referred_amt",
    TrendMetric.not_referred_debt: "eligible_debt_not_referred_amt",
}

_METRIC_LABEL: dict[str, str] = {
    TrendMetric.compliance_rate: "Compliance rate (% by amount)",
    TrendMetric.eligible_debt: "Total eligible debt (USD)",
    TrendMetric.referred_debt: "Debt referred to cross-servicing/TOP (USD)",
    TrendMetric.not_referred_debt: "Debt NOT referred (USD)",
}


def _year_value(quarters: dict[int, float]) -> tuple[float, int]:
    """Pick one value per fiscal year: Q4 (year-end) if reported, else the latest quarter."""
    q = 4 if 4 in quarters else max(quarters)
    return quarters[q], q


def _aggregate(
    fy_values: dict[str, dict[int, tuple[float, int]]],
    eligible: dict[str, dict[int, float]],
    referred: dict[str, dict[int, float]],
    is_pct_metric: bool,
) -> dict:
    """Government-wide series across the analyzed agencies.

    Rates are averaged across agencies (each agency counts once) and also reported
    dollar-weighted (total referred ÷ total eligible). USD metrics are summed.
    """
    by_fy: dict[int, list[str]] = {}
    for name, fy_map in fy_values.items():
        for fy in fy_map:
            by_fy.setdefault(fy, []).append(name)

    series = []
    for fy in sorted(by_fy):
        names = by_fy[fy]
        values = [fy_values[n][fy][0] for n in names]
        point = {"fy": fy, "agencies": len(names)}
        if is_pct_metric:
            point["mean_value"] = round(sum(values) / len(values), 4)
            total_eligible = sum(eligible[n].get(fy, 0.0) for n in names)
            total_referred = sum(referred[n].get(fy, 0.0) for n in names)
            point["dollar_weighted_value"] = (
                round(total_referred / total_eligible * 100, 4) if total_eligible else None
            )
        else:
            point["total_value"] = round(sum(values), 2)
        series.append(point)

    key = "mean_value" if is_pct_metric else "total_value"
    change = series[-1][key] - series[0][key] if len(series) >= 2 else 0.0
    return {
        "basis": (
            "mean across agencies; dollar_weighted_value = total referred ÷ total eligible"
            if is_pct_metric else "sum across agencies"
        ),
        "series": series,
        "change_abs": round(change, 4),
        "direction": "up" if change > 0.001 else ("down" if change < -0.001 else "flat"),
    }


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        name="get_delinquency_trends",
        annotations={
            "title": "Get DDR compliance trends",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def get_delinquency_trends(
        params: Annotated[DelinquencyTrendsInput, "Trend window, agency filter, and metric options."]
    ) -> dict:
        """Compute year-over-year trends in federal agency DDR compliance metrics.

        Fetches agency-level data for a range of fiscal years from the Fiscal Data API,
        then ranks agencies by how much their selected metric changed from the first to
        the last year in the window. Useful for spotting systematic improvement or
        deterioration in referral compliance across the government or within one agency.

        When agency_name is omitted, returns the top_n agencies by change magnitude
        across the whole government. When agency_name is provided, returns the year-by-year
        series for that single agency.

        For "biggest movers" questions, set cfo_agencies_only=True (the 24 CFO Act
        agencies) or min_eligible_debt_usd — otherwise tiny agencies whose rates swing
        between 0% and 100% on a handful of debts dominate the ranking.

        Returns:
          { metric, window, trend_direction (up/down/flat), agency_trends: [...],
            government_wide: {basis, series, change_abs, direction},
            filters, start_fy, end_fy, note }
        Each agency_trend: { agency_name, start_value, end_value, change_abs,
                             change_pct, direction, series: [{fy, quarter, value}] }

        The data is quarterly; each fiscal year is represented by its Q4 (year-end)
        value, or its latest reported quarter if Q4 is not yet published.
        """
        metric_field = _METRIC_FIELD[params.metric]
        # Eligible and referred debt are always fetched: they drive the dollar
        # threshold and the dollar-weighted government-wide rate.
        extra = [f for f in ("total_eligible_debt_amt", "eligible_debt_referred_amt") if f != metric_field]
        fields = ",".join(["agency_nm", "record_fiscal_year", "record_fiscal_quarter", metric_field, *extra])

        filters = [
            f"record_fiscal_year:gte:{params.fiscal_year_start}",
            f"record_fiscal_year:lte:{params.fiscal_year_end}",
            "agency_bureau_indicator:eq:Agency",
        ]
        if params.agency_name:
            filters.append(f"agency_nm:eq:{params.agency_name}")
        if params.cfo_agencies_only:
            filters.append("cfo_agency_indicator:eq:CFO")

        rows, error = await fetch_fiscal_all(_TROR_PATH, {
            "fields": fields,
            "sort": "agency_nm,record_fiscal_year,record_fiscal_quarter",
            "filter": ",".join(filters),
        })
        if error:
            return error
        if not rows:
            return {
                "error": "No data returned for the requested range.",
                "hint": "Check that agency_name exactly matches a name from list_agencies.",
            }

        # Group: {agency_name: {fy: {quarter: value}}}, per field
        grouped: dict[str, dict[int, dict[int, float]]] = {}
        eligible_q: dict[str, dict[int, dict[int, float]]] = {}
        referred_q: dict[str, dict[int, dict[int, float]]] = {}
        for row in rows:
            name = row.get("agency_nm", "")
            if not name:
                continue
            fy = int(row.get("record_fiscal_year", 0))
            quarter = int(row.get("record_fiscal_quarter", 0))
            for target, field in (
                (grouped, metric_field),
                (eligible_q, "total_eligible_debt_amt"),
                (referred_q, "eligible_debt_referred_amt"),
            ):
                val = _to_float(row.get(field))
                if val is not None:
                    target.setdefault(name, {}).setdefault(fy, {})[quarter] = val

        # Compute trend per agency
        start_fy = params.fiscal_year_start
        end_fy = params.fiscal_year_end

        def year_values(q_map: dict[str, dict[int, dict[int, float]]], name: str) -> dict[int, float]:
            return {fy: _year_value(qs)[0] for fy, qs in q_map.get(name, {}).items()}

        agency_trends = []
        analyzed: dict[str, dict[int, tuple[float, int]]] = {}
        eligible: dict[str, dict[int, float]] = {}
        referred: dict[str, dict[int, float]] = {}
        excluded_below_threshold = 0
        for name, fy_quarters in grouped.items():
            fy_map = {fy: _year_value(qs) for fy, qs in fy_quarters.items()}
            fys = sorted(fy_map)
            if len(fys) < 2:
                continue
            # Membership test, not `or`: a real 0.0 value must not fall through.
            first_fy = start_fy if start_fy in fy_map else fys[0]
            last_fy = end_fy if end_fy in fy_map else fys[-1]
            eligible[name] = year_values(eligible_q, name)
            referred[name] = year_values(referred_q, name)
            if params.min_eligible_debt_usd is not None:
                if eligible[name].get(first_fy, 0.0) < params.min_eligible_debt_usd:
                    excluded_below_threshold += 1
                    continue
            analyzed[name] = fy_map
            start_val = fy_map[first_fy][0]
            end_val = fy_map[last_fy][0]
            change_abs = end_val - start_val
            change_pct = (change_abs / start_val * 100) if start_val else None
            direction = "up" if change_abs > 0.001 else ("down" if change_abs < -0.001 else "flat")
            series = [
                {"fy": fy, "quarter": fy_map[fy][1], "value": round(fy_map[fy][0], 4)}
                for fy in fys
            ]
            agency_trends.append({
                "agency_name": name,
                "start_value": round(start_val, 4),
                "end_value": round(end_val, 4),
                "change_abs": round(change_abs, 4),
                "change_pct": round(change_pct, 2) if change_pct is not None else None,
                "direction": direction,
                "series": series,
            })

        if not agency_trends:
            return {
                "error": "No agencies matched the filters.",
                "hint": "Lower min_eligible_debt_usd or widen the fiscal year window.",
            }
        is_pct_metric = params.metric == TrendMetric.compliance_rate
        government_wide = _aggregate(analyzed, eligible, referred, is_pct_metric)

        # Sort by absolute change magnitude; apply top_n when not scoped to one agency
        agency_trends.sort(key=lambda x: abs(x["change_abs"]), reverse=True)
        if not params.agency_name:
            agency_trends = agency_trends[: params.top_n]

        # Government-wide trend direction: majority direction
        directions = [a["direction"] for a in agency_trends]
        gov_direction = max(set(directions), key=directions.count) if directions else "flat"

        return {
            "metric": _METRIC_LABEL[params.metric],
            "window": f"FY{start_fy}–FY{end_fy}",
            "trend_direction": gov_direction,
            "agency_trends": agency_trends,
            "start_fy": start_fy,
            "end_fy": end_fy,
            "agencies_analyzed": len(analyzed),
            "filters": {
                "cfo_agencies_only": params.cfo_agencies_only,
                "min_eligible_debt_usd": params.min_eligible_debt_usd,
                "excluded_below_threshold": excluded_below_threshold,
            },
            "government_wide": government_wide,
            "note": (
                ("Values are percentages (0–100)." if is_pct_metric else "Values are USD amounts.")
                + " Each fiscal year uses its Q4 (year-end) value, or the latest reported"
                " quarter when Q4 is not yet available."
            ),
        }


def _to_float(val) -> float | None:
    try:
        return float(val) if val not in (None, "null") else None
    except (TypeError, ValueError):
        return None
