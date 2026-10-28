# Security Policy

## Reporting a vulnerability

Please report suspected vulnerabilities privately to the repository maintainers
rather than opening a public issue. Include the affected file or tool, steps to
reproduce, and the impact you observed. Do not include real credentials or
non-public data in a report.

| Version (Branch) | Supported          |
| ---------------- | ------------------ |
| main             | :white_check_mark: |
| other            | :x:                |

## Deployment posture

- **Transport:** the supported deployment is **stdio** — the server runs as a
  local subprocess of the MCP client (Claude Desktop, Claude Code, or an internal
  AI Lab host). No network listener is opened in this mode.
- **HTTP mode** (`MCP_TRANSPORT=http`) exposes `/mcp` **without authentication**.
  It exists for local testing only. Before any networked use, front it with
  authentication and complete your agency's ATO review.
- **Data:** the Fiscal Data tools read only public, published Treasury data. The
  server does not store, cache, or log tool results.

## Secrets

- `TRORBOT_API_URL` and `TRORBOT_API_KEY` (optional knowledge-base tools) are read
  from environment variables or a git-ignored `.env` file. Never commit them.
- Without these values the KB tools return a structured "unavailable" error; no
  request is sent.

## Outbound request controls

All HTTP calls go through `src/trorbot_mcp/utils.py`:

- API origins come from operator configuration (`config.py` / `.env`), never from
  tool arguments. Tools pass only fixed relative paths; anything absolute,
  protocol-relative, or containing `..` is rejected.
- Redirects are not followed, and proxy settings from the environment are ignored.
- Every request has an explicit timeout (`HTTP_TIMEOUT`, default 30 seconds).
- Multi-page fetches return an error if any page fails — partial results are never
  returned silently.

## Errors and logging

- Tool errors are structured `{"error", "hint"}` dicts. They never contain
  upstream response bodies, headers, full URLs, query strings, credentials, or
  stack traces.
- Unexpected exceptions are logged by exception type name only.

## Input handling

- Every tool argument is validated by a Pydantic model (types, ranges, lengths)
  before any request is made.
- Treat all tool arguments and retrieved content as untrusted. Knowledge-base
  passages are returned as data and should not be treated as instructions by the
  calling agent.
