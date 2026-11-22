# TRORBOT MCP Server

> **GSA MCP Server and SI Agent Government Hackathon 2026 — Dataset Access Server**

An MCP (Model Context Protocol) server that makes Treasury's **publicly available** federal agency delinquent debt referral compliance data, spanning FY2016 to present, easier to use from Claude Desktop, Claude Code, Cursor, or any other MCP-compatible AI client.

The data is the [120 Day Delinquent Debt Referral Compliance Report](https://fiscaldata.treasury.gov/datasets/delinquent-debt-referral-compliance/), which the Bureau of the Fiscal Service publishes quarterly on [Fiscal Data](https://fiscaldata.treasury.gov/) from agencies' Treasury Report on Receivables (TROR) filings. It is public domain: anyone can browse it, download it, or call its API without registering. This server adds no data of its own and has no access to non-public Treasury data or systems. It turns plain-English questions into the right public API calls and calculations.

---

## What This Server Exposes

The public compliance report tracks whether federal agencies meet the requirement, set by the DATA Act of 2014, to refer legally enforceable non-tax debts more than 120 days delinquent to the Treasury Offset Program. This MCP server queries that public dataset on demand: 12,800+ quarterly agency and bureau records from FY2016 to present.

### Tools (7)

| Tool | Credentials | What it does |
|---|---|---|
| `list_agencies` | None | List federal agencies in the public compliance report, with fiscal year coverage |
| `query_receivables` | None | Query published DDR compliance records by agency, fiscal year, and quarter |
| `get_delinquency_trends` | None | Rank agencies by change in compliance rate or debt amounts over a FY window, with a government-wide aggregate. Filter to the 24 CFO Act agencies (`cfo_agencies_only`) or by size (`min_eligible_debt_usd`) |
| `validate_tror_submission` | None | Validate an agency's draft quarterly TROR Form 05 lines: computes the form's derived lines and the Treasury Offset Program compliance rate, runs consistency checks, and compares against the agency's last published quarter. Validates only; nothing is stored or filed |
| `search_program_context` | AWS (S3 Vectors) | Optional: search summaries of publicly reported policy events behind data changes |
| `search_program_guidance` | AWS (S3 Vectors) | Optional: search public program rules, legal authorities, TFM chapters |
| `get_annual_report_insights` | AWS (S3 Vectors) | Optional: search the public Annual TROR Reports to Congress |

The four tools that need no credentials call only the **public Fiscal Data API** (`api.fiscaldata.treasury.gov`), the same API anyone can call directly. Any judge or user can test them immediately. `validate_tror_submission` works only on the draft figures you give it and the public published rates; it stores nothing and files nothing.

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

Set `command` to the full path that `which uv` prints, and `/path/to/trorbot-mcp` to your
clone. Restart Claude Desktop. You'll see a 🔨 icon confirming the server is connected.

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
    "compared_against": "agency-wide: Small Business Administration",
    "published_compliance_rate_amt_pct": 75.877,
    "draft_vs_prior_change_pp": 9.12,
    "direction": "improvement"
  }
}
```

Each check also carries a one-line explanation of the form rule behind it. The receipt
ID is deterministic and marks a draft, not a filing.

TROR is filed by reporting entity, so a draft can be for a single bureau. Pass
`bureau_name` (the exact name from `query_receivables` with `include_bureaus=true`) and the
draft is compared against that bureau's published row instead of the agency-wide row; the
receipt's `compared_against` field says which. Published figures combine all receivable
types (direct loans, defaulted guaranteed loans, administrative), so compare a draft that
covers the same scope.

---

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `FISCAL_DATA_BASE_URL` | No | `https://api.fiscaldata.treasury.gov/services/api/fiscal_service` | Fiscal Data API base URL |
| `TRORBOT_KB_BUCKET` | For KB tools | — | S3 Vectors bucket holding the knowledge-base indexes |
| `TRORBOT_KB_AWS_PROFILE` | No | AWS default chain | AWS profile used for KB search |
| `TRORBOT_KB_REGION` | No | `us-east-1` | Region of the vector bucket and Bedrock embeddings |
| `MCP_TRANSPORT` | No | `stdio` | `stdio` or `http` |
| `HOST` | No | `127.0.0.1` | Interface for HTTP mode; `0.0.0.0` only inside a container behind authentication |
| `PORT` | No | `8080` | Port for HTTP mode |
| `HTTP_TIMEOUT` | No | `30` | Request timeout (seconds) |

Copy `.env.example` to `.env` and fill in values. The four public-data tools (`list_agencies`, `query_receivables`, `get_delinquency_trends`, `validate_tror_submission`) work without any credentials.

---

## Data Source

**[120 Day Delinquent Debt Referral Compliance Report](https://fiscaldata.treasury.gov/datasets/delinquent-debt-referral-compliance/)** on Treasury's public [Fiscal Data](https://fiscaldata.treasury.gov/) site

- Public dataset page, with CSV/JSON/XML downloads and a data dictionary: https://fiscaldata.treasury.gov/datasets/delinquent-debt-referral-compliance/
- API endpoint: `GET https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v2/debt/tror/data_act_compliance`
- Coverage: FY2016 Q1 — present (~12,800 agency and bureau quarterly records)
- Published by: Bureau of the Fiscal Service, from agencies' Treasury Report on Receivables (TROR) filings
- Update cadence: Quarterly (~45–60 days after quarter close)
- License: Public domain; no registration, API key, or credentials required

Every figure the public-data tools return can be checked against this page.

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
Fiscal Data API    Amazon S3 Vectors
(public, no auth)  (optional KB tools)
       │               │
  TROR DDR         3 indexes, queries
  compliance       embedded with Titan
  FY2016–present   Text Embeddings V2
```

---

## Knowledge Bases

The three knowledge-base tools are **optional and off by default**. They search an Amazon S3 Vectors bucket that you configure, one index per knowledge base. **No knowledge-base content is included in this repository**, and without a configured bucket these tools send no requests. The indexes are meant to hold publicly available documents only:

| Index | Tool | Contents (all publicly available) |
|---|---|---|
| `context-events` | `search_program_context` | Summaries of publicly reported news and agency announcements that explain changes in the data |
| `program-documentation` | `search_program_guidance` | DCIA and DATA Act text, GAO-02-313, Fiscal Service public FAQs (AWG, Cross-Servicing, CRS, TOP), TROR instructional workbooks |
| `annual-tror-reports` | `get_annual_report_insights` | Annual TROR Reports to Congress, tagged by `fiscal_year` |

A search embeds the question with Amazon Titan Text Embeddings V2 (1,024 dims, the
model the chunks were embedded with) and returns the closest chunks with their source
and a cosine similarity score. [scripts/load_kb_vectors.py](scripts/load_kb_vectors.py)
creates the bucket and indexes and loads them from an export of the chunks and vectors.
At this size the cost is well under $1/month (storage plus ~$2.50 per million queries).

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
│   ├── utils.py        # Shared HTTP helpers (Fiscal Data)
│   ├── kb.py           # Knowledge-base search (S3 Vectors + Titan embeddings)
│   ├── tools/          # 7 MCP tools
│   ├── prompts/        # 2 MCP prompts
│   └── resources/      # 1 MCP resource
├── eval/                     # ground-truth eval: cases, runner, fixtures, results
├── scripts/load_kb_vectors.py  # builds the S3 Vectors knowledge-base indexes
├── tests/
│   ├── test_tools.py         # registration and input-validation tests
│   ├── test_fiscal_tools.py  # tool behavior, replayed from recorded API responses
│   ├── conftest.py           # respx replay fixtures
│   ├── record_cassettes.py   # re-records cassettes from the live API
│   ├── test_eval.py          # runs the eval offline in CI
│   ├── test_kb.py            # KB search with stubbed AWS clients
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
| Real government dataset | Public 120 Day Delinquent Debt Referral Compliance Report on Fiscal Data, 12,800+ records |
| No credentials to demo | 4 of 7 tools are fully public |
| MCP primitives | All three used: tools, prompts, resources |
| Useful to analysts | Compliance trends, agency benchmarking, policy context |
| Extensible | Optional KB tools add narrative context from public documents when an S3 Vectors bucket is configured |

---

## License

Public domain — see [LICENSE](LICENSE) (CC0 1.0). Security posture: [SECURITY.md](SECURITY.md). Data sourced from the U.S. Department of the Treasury, Bureau of the Fiscal Service.
