"""Run the TRORBOT ground-truth eval.

Modes:
  uv run python eval/run_eval.py            # replay: offline, from committed fixtures
  uv run python eval/run_eval.py --live     # live tools vs. ground truth recomputed from a fresh snapshot
  uv run python eval/run_eval.py --record   # refresh the snapshot, expected answers, and tool cassettes

Every case calls a real MCP tool through an in-memory FastMCP client, extracts the
answer from the tool's structured output, and compares it with the ground truth:
numbers must match within 0.01% (relative), names and labels must match exactly.
Results are written to eval/results.json.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
import respx
from fastmcp import Client

EVAL_DIR = Path(__file__).parent
sys.path.insert(0, str(EVAL_DIR))

from cases import CASES  # noqa: E402

from trorbot_mcp import utils  # noqa: E402
from trorbot_mcp.app import mcp  # noqa: E402
from trorbot_mcp.config import settings  # noqa: E402

FIXTURES = EVAL_DIR / "fixtures"
SNAPSHOT_PATH = FIXTURES / "raw_snapshot.json"
EXPECTED_PATH = EVAL_DIR / "expected.json"
RESULTS_PATH = EVAL_DIR / "results.json"
CASSETTE_DIR = FIXTURES / "tool_cassettes"

TROR_URL = settings.fiscal_data_base_url.rstrip("/") + "/v2/debt/tror/data_act_compliance"
REL_TOL = 1e-4  # 0.01%

SNAPSHOT_FIELDS = (
    "record_date,record_fiscal_year,record_fiscal_quarter,agency_nm,cfo_agency_indicator,"
    "total_eligible_debt_amt,eligible_debt_referred_amt,compliance_rate_amt"
)


# ── ground-truth snapshot (plain httpx; deliberately bypasses server code) ──


def fetch_snapshot() -> dict:
    def pages(params: dict) -> list[dict]:
        rows, page = [], 1
        with httpx.Client(timeout=60) as http:
            while True:
                resp = http.get(TROR_URL, params={**params, "page[size]": 1000, "page[number]": page})
                resp.raise_for_status()
                body = resp.json()
                rows.extend(body["data"])
                if page >= int(body["meta"]["total-pages"]):
                    return rows
                page += 1

    names = pages({"fields": "agency_nm", "filter": "agency_bureau_indicator:eq:Agency"})
    rows = pages({
        "fields": SNAPSHOT_FIELDS,
        "filter": "agency_bureau_indicator:eq:Agency,record_fiscal_year:gte:2021",
        "sort": "agency_nm,record_fiscal_year,record_fiscal_quarter",
    })
    return {
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "latest_record_date": max(r["record_date"] for r in rows),
        "agency_names": sorted({r["agency_nm"] for r in names}),
        "rows": rows,
    }


def compute_expected(snapshot: dict) -> dict:
    return {case.id: case.ground_truth(snapshot) for case in CASES}


# ── scoring ─────────────────────────────────────────────────────────────


def matches(actual, expected) -> bool:
    if isinstance(expected, bool) or isinstance(expected, str):
        return actual == expected
    if isinstance(expected, (int, float)):
        return isinstance(actual, (int, float)) and math.isclose(actual, expected, rel_tol=REL_TOL, abs_tol=1e-9)
    if isinstance(expected, list):
        return isinstance(actual, list) and len(actual) == len(expected) and all(map(matches, actual, expected))
    if isinstance(expected, dict):
        return isinstance(actual, dict) and actual.keys() == expected.keys() and all(
            matches(actual[k], expected[k]) for k in expected
        )
    return actual == expected


# ── tool calls: live, recording, or replayed ────────────────────────────


async def run_cases(expected: dict, mode: str) -> list[dict]:
    results = []
    async with Client(mcp) as client:
        for case in CASES:
            interactions: list[dict] = []
            cassette = CASSETTE_DIR / f"{case.id}.json"

            async def capture(response, _log=interactions):
                await response.aread()
                _log.append({"params": dict(response.request.url.params), "response": response.json()})

            utils._fiscal_client = None
            router = None
            if mode == "replay":
                recorded = json.loads(cassette.read_text())
                router = respx.mock(assert_all_called=False)
                router.get(TROR_URL).mock(side_effect=_replayer(recorded, interactions))
                router.start()
            elif mode == "record":
                utils._get_fiscal_client().event_hooks["response"] = [capture]

            started = time.perf_counter()
            try:
                result = await client.call_tool(case.tool, {"params": case.args}, raise_on_error=False)
                latency_ms = round((time.perf_counter() - started) * 1000, 1)
                if result.is_error:
                    actual, error = None, result.content[0].text
                else:
                    actual, error = case.extract(result.structured_content), None
            except Exception as e:  # extractor failures count as a failed case
                latency_ms = round((time.perf_counter() - started) * 1000, 1)
                actual, error = None, f"{type(e).__name__}: {e}"
            finally:
                if router:
                    router.stop()

            if mode == "record":
                cassette.write_text(json.dumps(interactions, indent=1) + "\n")

            passed = error is None and matches(actual, expected[case.id])
            results.append({
                "id": case.id,
                "question": case.question,
                "tool": case.tool,
                "args": case.args,
                "expected": expected[case.id],
                "actual": actual,
                "pass": passed,
                "error": error,
                "latency_ms": latency_ms,
                "http_requests": None if mode == "live" else len(interactions),
            })
    return results


def _replayer(recorded: list[dict], log: list[dict]):
    def respond(request: httpx.Request) -> httpx.Response:
        params = dict(request.url.params)
        for item in recorded:
            if item["params"] == params:
                log.append(item)
                return httpx.Response(200, json=item["response"])
        raise AssertionError(f"no recorded response for {params}")

    return respond


async def main(mode: str) -> int:
    if mode == "replay":
        snapshot = json.loads(SNAPSHOT_PATH.read_text())
        expected = json.loads(EXPECTED_PATH.read_text())
    else:
        snapshot = fetch_snapshot()
        expected = json.loads(json.dumps(compute_expected(snapshot)))
        if mode == "record":
            FIXTURES.mkdir(exist_ok=True)
            CASSETTE_DIR.mkdir(exist_ok=True)
            SNAPSHOT_PATH.write_text(json.dumps(snapshot, separators=(",", ":")) + "\n")
            EXPECTED_PATH.write_text(json.dumps(expected, indent=2) + "\n")

    results = await run_cases(expected, mode)
    passed = sum(r["pass"] for r in results)
    report = {
        "run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "mode": mode,
        "data_snapshot": {"fetched_at": snapshot["fetched_at"], "latest_record_date": snapshot["latest_record_date"]},
        "tolerance": "numbers within 0.01% relative; names exact",
        "summary": {
            "passed": passed,
            "total": len(results),
            "accuracy": round(passed / len(results), 4),
            "median_latency_ms": round(statistics.median(r["latency_ms"] for r in results), 1),
        },
        "cases": results,
    }
    RESULTS_PATH.write_text(json.dumps(report, indent=2) + "\n")

    for r in results:
        requests = "" if r["http_requests"] is None else f"  {r['http_requests']} req"
        print(f"{'PASS' if r['pass'] else 'FAIL'}  {r['id']:<28} {r['latency_ms']:>8} ms{requests}")
        if not r["pass"]:
            print(f"      expected: {r['expected']}\n      actual:   {r['actual']}\n      error:    {r['error']}")
    print(f"\n{passed}/{len(results)} passed ({mode}) → {RESULTS_PATH.relative_to(EVAL_DIR.parent)}")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--live", action="store_const", dest="mode", const="live")
    group.add_argument("--record", action="store_const", dest="mode", const="record")
    parser.set_defaults(mode="replay")
    sys.exit(asyncio.run(main(parser.parse_args().mode)))
