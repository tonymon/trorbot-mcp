# Ground-truth evaluation

Eight analyst questions, each answered by a real MCP tool call and checked against
an answer computed independently from raw Fiscal Data API rows.

| # | Case | Question | Tool |
|---|---|---|---|
| 1 | `agency_count` | How many agencies have reported TROR data since FY2016? | `list_agencies` |
| 2 | `doj_fy2024_q4_rate` | DOJ compliance rate, FY2024 Q4 | `query_receivables` |
| 3 | `cfo_largest_decline` | CFO Act agency with the largest rate decline, FY2021→FY2025 | `get_delinquency_trends` |
| 4 | `cfo_largest_improvement` | CFO Act agency with the largest rate improvement, FY2021→FY2025 | `get_delinquency_trends` |
| 5 | `ssa_series_2021_2025` | SSA year-by-year compliance rate, FY2021–FY2025 | `get_delinquency_trends` |
| 6 | `dod_fy2025_eligible_debt` | DoD total eligible debt, FY2025 year-end | `query_receivables` |
| 7 | `full_compliance_fy2025_q4` | Agencies at 100% compliance, FY2025 Q4 | `query_receivables` |
| 8 | `cfo_mean_rate_trend` | Mean CFO-agency compliance rate trend, FY2021–FY2025 | `get_delinquency_trends` |

## Method

- **Ground truth** ([cases.py](cases.py)) is computed from
  [fixtures/raw_snapshot.json](fixtures/raw_snapshot.json) — every agency-level row
  for FY2021 onward plus all agency names since FY2016 — using plain Python over raw
  rows. It shares no code with the server. "Fiscal year value" means the Q4
  (year-end) row.
- **Answers** come from calling the tool through an in-memory FastMCP client and
  reading its structured output, the same way an agent would.
- **Scoring**: numbers must match within 0.01% (relative); agency names and labels
  must match exactly; lists and objects must match element by element.
- Results, including per-case latency and HTTP request counts, go to
  [results.json](results.json).

This is a tool-level eval: it tests that each tool returns correct answers for
the arguments an agent should send. It does not test whether a model chooses those
arguments.

## Running

```bash
uv run python eval/run_eval.py            # offline replay of committed fixtures (also runs in pytest)
uv run python eval/run_eval.py --live     # live API: tools vs. ground truth recomputed from a fresh snapshot
uv run python eval/run_eval.py --record   # refresh snapshot, expected.json, and tool cassettes
```

`--live` is the one that proves the server works against today's data;
replay mode keeps CI deterministic and offline.

## Baseline

[baseline_66124de.json](baseline_66124de.json) is a `--live` run against the
initial commit, before the pagination and quarter fixes. It scored **3/8**:

- `agency_count` returned **10** agencies instead of 71 (only the first page was read).
- `ssa_series_2021_2025` reported FY2024 as **54.31%** instead of the Q4 value
  **53.33%** (later quarters overwrote earlier ones in arbitrary order).
- The three CFO-agency cases failed because the CFO filter and government-wide
  aggregate did not exist yet.
