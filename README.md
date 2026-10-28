# TRORBOT MCP Server

> **GSA MCP Server Government Hackathon — Dataset Access Server**
> Submission deadline: November 20, 2026

An MCP (Model Context Protocol) server that gives any Claude Desktop, Cursor, or MCP-compatible LLM client direct access to the **Treasury Report on Receivables (TROR)** dataset — federal agency delinquent debt referral compliance data spanning FY2016 to present.

Built on top of [TRORBOT](https://github.com/tonymon/bedrock-agent-ui), the Bureau of the Fiscal Service's AI assistant for receivables analysis.

---

## What This Server Exposes

The TROR dataset tracks whether federal agencies comply with the **Debt Collection Improvement Act (DCIA)** requirement to refer eligible delinquent debts to the Treasury for cross-servicing or offset within 120 days. This MCP server surfaces that data — 12,800+ quarterly agency compliance records from FY2016 to present — directly to LLMs.

### Tools (6)

| Tool | Credentials | What it does |
|---|---|---|
| `list_agencies` | None | List federal agencies reporting TROR data, with fiscal year coverage |
| `query_receivables` | None | Query DDR compliance records by agency, fiscal year, and quarter |
| `get_delinquency_trends` | None | Rank agencies by change in compliance rate or debt amounts over a FY window |
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
Use trorbot get_delinquency_trends to show the top 10 agencies by
change in compliance rate from FY2020 to FY2024.
```

```
Use trorbot get_delinquency_trends to show the year-by-year compliance
rate for "Social Security Administration" from FY2016 to FY2024.
```

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

## Development

```bash
# Run tests
uv run pytest tests/ -v

# Watch mode
uv run pytest tests/ -v --tb=short -q
```

### Project structure

```
trorbot-mcp/
├── src/trorbot_mcp/
│   ├── app.py          # FastMCP server entry point
│   ├── config.py       # pydantic-settings configuration
│   ├── models.py       # Pydantic input models
│   ├── utils.py        # Shared HTTP helpers
│   ├── tools/          # 6 MCP tools
│   ├── prompts/        # 2 MCP prompts
│   └── resources/      # 1 MCP resource
├── tests/
│   └── test_tools.py   # 12 smoke tests
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
| No credentials to demo | 3 of 6 tools are fully public |
| MCP primitives | All three used: tools, prompts, resources |
| Useful to analysts | Compliance trends, agency benchmarking, policy context |
| Extensible | KB tools light up with TRORBOT credentials for narrative context |

---

## License

Public domain. Data sourced from the U.S. Department of the Treasury, Bureau of the Fiscal Service.
