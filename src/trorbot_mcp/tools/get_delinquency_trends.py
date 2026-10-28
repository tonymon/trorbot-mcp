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
from trorbot_mcp.utils import fetch_fiscal

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


async def _fetch_all_pages(filters: list[str], fields: str) -> list[dict]:
    """Pull all pages for a filter set (up to 1 000 rows to stay responsive)."""
    rows: list[dict] = []
    page = 1
    while True:
        params: dict = {
            "page[size]": 100,
            "page[number]": page,
            "fields": fields,
            "sort": "agency_nm,record_fiscal_year",
            "filter": ",".join(filters),
        }
        raw = await fetch_fiscal(_TROR_PATH, params)
        if "error" in raw:
            return []
        rows.extend(raw.get("data", []))
        total = int(raw.get("meta", {}).get("total-count", 0))
        if len(rows) >= total or len(rows) >= 1000:
            break
        page += 1
    return rows


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

        Returns:
          { metric, window, trend_direction (up/down/flat), agency_trends: [...],
            start_fy, end_fy, note }
        Each agency_trend: { agency_name, start_value, end_value, change_abs,
                             change_pct, direction, series: [{fy, value}] }
        """
        metric_field = _METRIC_FIELD[params.metric]
        fields = f"agency_nm,record_fiscal_year,{metric_field}"

        filters = [
            f"record_fiscal_year:gte:{params.fiscal_year_start}",
            f"record_fiscal_year:lte:{params.fiscal_year_end}",
            "agency_bureau_indicator:eq:Agency",
        ]
        if params.agency_name:
            filters.append(f"agency_nm:eq:{params.agency_name}")

        rows = await _fetch_all_pages(filters, fields)

        if not rows:
            return {
                "error": "No data returned for the requested range.",
                "hint": "Check that agency_name exactly matches a name from list_agencies.",
            }

        # Group: {agency_name: {fy: value}}
        grouped: dict[str, dict[int, float]] = {}
        for row in rows:
            name = row.get("agency_nm", "")
            fy = int(row.get("record_fiscal_year", 0))
            raw_val = row.get(metric_field)
            try:
                val = float(raw_val) if raw_val not in (None, "null") else None
            except (TypeError, ValueError):
                val = None
            if not name or val is None:
                continue
            grouped.setdefault(name, {})[fy] = val

        # Compute trend per agency
        start_fy = params.fiscal_year_start
        end_fy = params.fiscal_year_end

        agency_trends = []
        for name, fy_map in grouped.items():
            fys = sorted(fy_map)
            if len(fys) < 2:
                continue
            start_val = fy_map.get(start_fy) or fy_map[fys[0]]
            end_val = fy_map.get(end_fy) or fy_map[fys[-1]]
            change_abs = end_val - start_val
            change_pct = (change_abs / start_val * 100) if start_val else None
            direction = "up" if change_abs > 0.001 else ("down" if change_abs < -0.001 else "flat")
            series = [{"fy": fy, "value": round(fy_map[fy], 4)} for fy in fys]
            agency_trends.append({
                "agency_name": name,
                "start_value": round(start_val, 4),
                "end_value": round(end_val, 4),
                "change_abs": round(change_abs, 4),
                "change_pct": round(change_pct, 2) if change_pct is not None else None,
                "direction": direction,
                "series": series,
            })

        # Sort by absolute change magnitude; apply top_n when not scoped to one agency
        agency_trends.sort(key=lambda x: abs(x["change_abs"]), reverse=True)
        if not params.agency_name:
            agency_trends = agency_trends[: params.top_n]

        # Government-wide trend direction: majority direction
        directions = [a["direction"] for a in agency_trends]
        gov_direction = max(set(directions), key=directions.count) if directions else "flat"

        is_pct_metric = params.metric == TrendMetric.compliance_rate

        return {
            "metric": _METRIC_LABEL[params.metric],
            "window": f"FY{start_fy}–FY{end_fy}",
            "trend_direction": gov_direction,
            "agency_trends": agency_trends,
            "start_fy": start_fy,
            "end_fy": end_fy,
            "agencies_analyzed": len(grouped),
            "note": (
                "Values are percentages (0–100)." if is_pct_metric
                else "Values are USD amounts."
            ),
        }
