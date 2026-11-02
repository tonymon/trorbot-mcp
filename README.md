# TRORBOT MCP Server

> **GSA MCP Server Government Hackathon — Dataset Access Server**
> Submission deadline: November 20, 2026

An MCP (Model Context Protocol) server that gives any Claude Desktop, Cursor, or MCP-compatible LLM client direct access to the **Treasury Report on Receivables (TROR)** dataset — federal agency delinquent debt referral compliance data spanning FY2016 to present.

Built on top of [TRORBOT](https://github.com/tonymon/bedrock-agent-ui), the Bureau of the Fiscal Service's AI assistant for receivables analysis.

---

## What This Server Exposes

The TROR dataset tracks whether federal agencies comply with the **Debt Collection Improvement Act (DCIA)** requirement to refer eligible delinquent debts to the Treasury for cross-servicing or offset within 120 days. This MCP server surfaces that data — 12,800+ quarterly agency compliance records from FY2016 to present — directly to LLMs.

### Tools (7)

| Tool | Credentials | What it does |
|---|---|---|
| `list_agencies` | None | List federal agencies reporting TROR data, with fiscal year coverage |
| `query_receivables` | None | Query DDR compliance records by agency, fiscal year, and quarter |
| `get_delinquency_trends` | None | Rank agencies by change in compliance rate or debt amounts over a FY window, with a government-wide aggregate. Filter to the 24 CFO Act agencies (`cfo_agencies_only`) or by size (`min_eligible_debt_usd`) |
| `validate_tror_submission` | None | Validate an agency's draft quarterly TROR Form 05 lines: computes the form's derived lines and the Treasury Offset Program compliance rate, runs consistency checks, and compares against the agency's last published quarter. Validates only; nothing is stored or filed |
| `search_program_context` | TRORBOT API | Search analyst-curated policy events explaining data changes |
| `search_program_guidance` | TRORBOT API | Search program rules, legal authorities, TFM chapters |
| `get_annual_report_insights` | TRORBOT API | Search Annual TROR Reports to Congress |

The first three tools hit the **public Fiscal Data API** (`api.fiscaldata.treasury.gov`) with no credentials required. Any judge or user can test them immediately.

### Prompts (2)

| Prompt | What it does |
|---|---|
| `analyze_agency_performance` | Guides a 5-step structured analysis of an agency's compliance trend |
| `explain_collection_program` | Explains a debt collection program using guidance + recent policy context |

### Resource (1)

| URI | What it contains |
|---|---|
| `trorbot://fiscal-year-metadata` | Current FY, data coverage, quarter definitions, freshness notes |

---

## Quickstart

### Prerequisites

- [uv](https://docs.astral.sh/uv/getting-started/installation/) — Python package manager
- Python 3.11+

### Install

```bash
git clone https://github.com/tonymon/trorbot-mcp.git
cd trorbot-mcp
uv sync
```

### Run in stdio mode (Claude Desktop)

```bash
cp .env.example .env
uv run trorbot-mcp
```

### Run as HTTP server

```bash
MCP_TRANSPORT=http PORT=8080 uv run trorbot-mcp
```

---

## Claude Desktop Configuration

Add this to `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "trorbot": {
      "command": "/opt/homebrew/bin/uv",
      "args": [
        "run",
        "--directory",
        "/path/to/trorbot-mcp",
        "trorbot-mcp"
      ],
      "env": {
        "MCP_TRANSPORT": "stdio"
      }
    }
  }
}
```

Restart Claude Desktop. You'll see a 🔨 icon confirming the server is connected.

---

## Example Prompts (Claude Desktop)

```
Use trorbot list_agencies to find agencies with "Defense" in the name.
```

```
Use trorbot query_receivables to get FY2024 Q4 DDR compliance data
for "Department of Defense".
```

```
Use trorbot get_delinquency_trends to show which CFO Act agencies
improved or declined the most in compliance rate from FY2021 to FY2025.
```

```
Use trorbot get_delinquency_trends to show the year-by-year compliance
rate for "Social Security Administration" from FY2016 to FY2025.
```

---

## Agency Submission Demo

Today agencies compile TROR Form 05 figures by hand from several financial systems
and key them into a web portal. Errors surface after filing. An agency's AI agent
connected to TRORBOT MCP can check its draft first:

1. **Confirm the agency name.** `list_agencies` returns the exact name Fiscal Data uses.
2. **Pull the prior quarter.** `query_receivables` returns the agency's last published
   compliance figures for comparison.
3. **Assemble the draft.** The agent gathers the quarter's figures from the agency's
   systems of record.
4. **Validate before filing.** `validate_tror_submission` returns a receipt with
   computed rates, check results and the change from the last published quarter,
   before anyone touches the form.

The tool's inputs follow TROR Form 05 line by line:

- **Part I-A** (fiscal-year-to-date): beginning FY balance, new receivables, accruals,
  collections, adjustments, amounts written off.
- **Part I-C**: total delinquencies, excluding currently-not-collectible (CNC) debt.
- **Part II-B section 1** (Treasury Offset Program, 120 days under the DATA Act): debt
  over 120 days delinquent, CNC debt, ineligible debt (bankruptcy, forbearance or
  appeals, foreclosure, other), exceptions (foreign sovereign, litigation, other), and
  debt referred directly or through Cross-Servicing. Each line takes dollars and a count.

From these it computes the form's derived lines (ending balance, 1C, 1H, 1M, 1P) and the
compliance rate, debt referred ÷ debt required to be referred, which is the measure
Fiscal Data publishes.

Example prompt:

```
I'm preparing the Small Business Administration's FY2026 Q4 TROR submission.
Validate these draft figures with trorbot validate_tror_submission:
Part I-A: beginning FY balance $9.0B, new receivables $800M, accruals $40M,
collections $650M, written off $40M. Total delinquent $1.5B (60,000 accounts).
Part II-B: over 120 days $1.1B (44,000), CNC $150M (6,000), bankruptcy $30M (1,200),
forbearance $20M (800), referred directly to TOP $700M (28,000),
referred via Cross-Servicing $320M (13,280).
```

The receipt (abridged; the draft figures are illustrative, the prior quarter is SBA's
published FY2026 Q3 rate):

```json
{
  "validation_status": "passed",
  "receipt_id": "TROR-DRAFT-2026-Q4-SMALL-BUSINESS-ADMIN-47796C",
  "computed_lines": {
    "ending_balance_usd": 9150000000.0,
    "total_over_120_and_cnc": {"usd": 1250000000.0, "count": 50000},
    "eligible_for_offset": {"usd": 1200000000.0, "count": 48000},
    "required_to_be_referred": {"usd": 1200000000.0, "count": 48000},
    "referred_to_top": {"usd": 1020000000.0, "count": 41280},
    "remaining_to_be_referred": {"usd": 180000000.0, "count": 6720},
    "compliance_rate_amt_pct": 85.0,
    "compliance_rate_cnt_pct": 86.0
  },
  "checks": [
    {"rule": "ending_balance_not_negative", "result": "pass"},
    {"rule": "over_120_within_total_delinquent", "result": "pass"},
    {"rule": "ineligible_within_over_120_and_cnc", "result": "pass"},
    {"rule": "exceptions_within_eligible", "result": "pass"},
    {"rule": "referred_within_required", "result": "pass"},
    {"rule": "quarter_has_closed", "result": "pass"}
  ],
  "prior_quarter": {
    "found": true,
    "period": "FY2026 Q3",
    "published_compliance_rate_amt_pct": 75.877,
    "draft_vs_prior_change_pp": 9.12,
    "direction": "improvement"
  }
}
```

Each check also carries a one-line explanation of the form rule behind it. The receipt
ID is deterministic and marks a draft, not a filing.

---

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `FISCAL_DATA_BASE_URL` | No | `https://api.fiscaldata.treasury.gov/services/api/fiscal_service` | Fiscal Data API base URL |
| `TRORBOT_API_URL` | For KB tools | — | TRORBOT API Gateway URL |
| `TRORBOT_API_KEY` | For KB tools | — | TRORBOT API key |
| `MCP_TRANSPORT` | No | `stdio` | `stdio` or `http` |
| `PORT` | No | `8080` | Port for HTTP mode |
| `HTTP_TIMEOUT` | No | `30` | Request timeout (seconds) |

Copy `.env.example` to `.env` and fill in values. The first three tools (`list_agencies`, `query_receivables`, `get_delinquency_trends`) work without any credentials.

---

## Data Source

**[Fiscal Data API — 120 Day Delinquent Debt Referral Compliance Report](https://fiscaldata.treasury.gov/)**

- Endpoint: `GET /services/api/fiscal_service/v2/debt/tror/data_act_compliance`
- Coverage: FY2016 Q1 — present (~12,800 agency-quarter records)
- Published by: Bureau of the Fiscal Service
- Update cadence: Quarterly (~45–60 days after quarter close)
- License: Public domain, no auth required

### Key Fields

| Field | Type | Description |
|---|---|---|
| `agency_nm` | String | Federal agency name |
| `record_fiscal_year` | Year | Fiscal year (Oct–Sep) |
| `record_fiscal_quarter` | Quarter | 1=Oct–Dec, 2=Jan–Mar, 3=Apr–Jun, 4=Jul–Sep |
| `total_eligible_debt_amt` | USD | Debt eligible for 120-day referral |
| `eligible_debt_referred_amt` | USD | Debt actually referred |
| `compliance_rate_amt` | % | Referred ÷ eligible (dollar basis) |
| `compliance_rate_cnt` | % | Referred ÷ eligible (count basis) |

---

## Architecture

```
Claude Desktop / Cursor / any MCP client
        │
        │  MCP protocol (stdio or HTTP/SSE)
        ▼
┌─────────────────────────────────────┐
│         TRORBOT MCP Server          │
│         (FastMCP, Python)           │
│                                     │
│  Tools          Prompts  Resources  │
│  ├ list_agencies                    │
│  ├ query_receivables    fiscal-year │
│  ├ get_delinquency_trends  metadata │
│  ├ validate_tror_submission         │
│  ├ search_program_context           │
│  ├ search_program_guidance          │
│  └ get_annual_report_insights       │
└──────────────┬──────────────────────┘
               │
       ┌───────┴───────┐
       ▼               ▼
Fiscal Data API    TRORBOT API
(public, no auth)  (optional KB tools)
       │               │
  TROR DDR         Bedrock KBs
  compliance       (OpenSearch
  FY2016–present    Serverless)
```

---

## Evaluation

8 ground-truth analyst questions answered through the live tools and scored against
answers computed independently from raw API rows — **8/8 passing** (the initial
commit scored 3/8). See [eval/README.md](eval/README.md).

```bash
uv run python eval/run_eval.py --live
```

---

## Development

```bash
uv sync --group dev

# Run tests (offline — Fiscal Data responses are replayed from tests/cassettes/)
uv run pytest tests/ -v

# Lint
uv run ruff check .

# Re-record cassettes from the live API (only when upstream data or a query changes)
uv run python tests/record_cassettes.py
```

### Project structure

```
trorbot-mcp/
├── src/trorbot_mcp/
│   ├── app.py          # FastMCP server entry point
│   ├── config.py       # pydantic-settings configuration
│   ├── models.py       # Pydantic input models
│   ├── utils.py        # Shared HTTP helpers
│   ├── tools/          # 7 MCP tools
│   ├── prompts/        # 2 MCP prompts
│   └── resources/      # 1 MCP resource
├── eval/                     # ground-truth eval: cases, runner, fixtures, results
├── tests/
│   ├── test_tools.py         # registration and input-validation tests
│   ├── test_fiscal_tools.py  # tool behavior, replayed from recorded API responses
│   ├── conftest.py           # respx replay fixtures
│   ├── record_cassettes.py   # re-records cassettes from the live API
│   ├── test_eval.py          # runs the eval offline in CI
│   └── cassettes/            # recorded Fiscal Data API responses
├── pyproject.toml
└── .env.example
```

---

## Hackathon Alignment

**Category:** Dataset Access Server

**Judging criteria met:**

| Criteria | How |
|---|---|
| Real government dataset | TROR DDR compliance — public Fiscal Data API, 12,800+ records |
| No credentials to demo | 4 of 7 tools are fully public |
| MCP primitives | All three used: tools, prompts, resources |
| Useful to analysts | Compliance trends, agency benchmarking, policy context |
| Extensible | KB tools light up with TRORBOT credentials for narrative context |

---

## License

Public domain — see [LICENSE](LICENSE) (CC0 1.0). Security posture: [SECURITY.md](SECURITY.md). Data sourced from the U.S. Department of the Treasury, Bureau of the Fiscal Service.
