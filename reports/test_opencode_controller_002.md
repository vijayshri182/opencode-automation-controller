# TEST-OPENCODE-CONTROLLER-002 — Controller Startup Preflight

## Repository baseline
- Repo: `C:\Vijay_GitHub\opencode-automation-controller`, branch `master`, no commits (all files untracked).
- Working tree: substantial uncommitted work (WP-421..WP-434). Preserved (no reset/stash/commit).
- HEAD: none.

## Startup procedure and its source
- Source: `README.md` "Quick start" + "Secure startup" sections; `src/opencode_bridge/cli.py`.
- Supported command (mock mode):
  ```
  cd C:\Vijay_GitHub\opencode-automation-controller
  $env:PYTHONPATH = "src"
  $env:OPENCODE_MOCK = "1"
  python -m opencode_bridge.cli --mock --port 8799
  ```
- Secure (real OpenCode) mode:
  ```
  $env:PYTHONPATH = "src"
  $env:OPENCODE_BASE_URL = "http://127.0.0.1:4097"
  $env:OPENCODE_SERVER_PASSWORD = "<strong local password>"
  $env:OPENCODE_MOCK = "0"
  $env:MCP_AUTH_TOKEN = "<token>"
  python -m opencode_bridge.cli --port 8799
  ```
- DB path default: `DEV_WORKSPACE/.opencode_bridge/bridge.db` = `C:\Vijay_GitHub\fno-ai-paper-trading-dev\.opencode_bridge\bridge.db`. Note: this points into the DEV F&O repo workspace, not the controller repo.

## Port and endpoint mapping
- **8799** (default, `MCP_DEFAULT_PORT`): FastAPI/uvicorn MCP server (`mcp_server.py`). Endpoint `POST /mcp` (JSON-RPC 2.0). Health `GET /health` (if exposed). This is the primary controller API.
- **8798** (`DEFAULT_PORT` in `controller_api.py`): stdlib `ThreadingHTTPServer` controller API — **not started by the CLI** (separate module, not wired in `cli.py`). Loopback only.
- **4097**: OpenCode server (running, HTTP 200 on /health). `.env` sets `OPENCODE_BASE_URL=http://127.0.0.1:4097`. README recommends 4096; .env overrides to 4097 (matches running server).

## Environment/dependency readiness
- `.env` present: `OPENCODE_BASE_URL=http://127.0.0.1:4097`, `OPENCODE_SERVER_PASSWORD=...` (value present, not printed). No `MCP_AUTH_TOKEN`, no `OPENCODE_MOCK`.
- **BLOCKER 1 — Missing dependencies**: controller `.venv` contains only `playwright`. `fastapi`, `uvicorn`, `aiosqlite`, `requests` are NOT installed. They exist in system Python 3.13 and the ai-career-agent venv, but not in the controller venv. Starting with the controller venv would fail with `ModuleNotFoundError`.
- **BLOCKER 2 — No auth token**: `MCP_AUTH_TOKEN` unset → `mcp_auth_token()` returns `""` → `_auth_ok()` returns `False` (fails closed). Even if started, all tool calls would be rejected as unauthorized.
- OpenCode server reachable on 4097 (HTTP 200 with basic auth).

## Real-versus-mock adapter assessment
- `use_mock_adapter()` returns True only if `OPENCODE_MOCK` in (`1`,`true`,`yes`). Currently unset → **real adapter** (`OpenCodeAdapter`) would be used. This is the desired mode for E2E verification, but it requires a reachable OpenCode server (confirmed on 4097) and valid credentials.
- Mock mode (`--mock`) is available for offline testing but would not demonstrate real websearch execution.

## Risks and prerequisites
- Dependencies must be installed in the controller venv (or use a Python environment that has them) — operator decision.
- `MCP_AUTH_TOKEN` must be set (operator-chosen secret) before startup; otherwise all tool calls fail.
- DB path points into the DEV F&O repo (`fno-ai-paper-trading-dev/.opencode_bridge/bridge.db`); ensure that workspace exists and is writable.
- Port 8799 must be free (confirmed: not in use).
- OpenCode server must remain running on 4097 with matching credentials.
- Starting the controller creates/uses a SQLite DB and may spawn an auto-worker (OpenCode calls). No production code changes, but runtime state is created.

## Exact proposed startup command (NOT executed)
```powershell
cd C:\Vijay_GitHub\opencode-automation-controller
$env:PYTHONPATH = "src"
$env:OPENCODE_BASE_URL = "http://127.0.0.1:4097"
$env:OPENCODE_SERVER_PASSWORD = "<from .env / approved secret store>"
$env:MCP_AUTH_TOKEN = "<operator-chosen token>"
$env:OPENCODE_MOCK = "0"
python -m opencode_bridge.cli --port 8799
```
(Using system Python or a venv with fastapi/uvicorn/aiosqlite/requests installed.)

## Post-start verification procedure
1. `GET http://127.0.0.1:8799/health` → expect 200.
2. MCP `initialize` → expect capabilities with tools list.
3. MCP `tools/call` `controller_health` → expect OpenCode connectivity status.
4. MCP `tools/call` `get_controller_capabilities` → confirm tool list.
5. Submit a task via `submit_chatgpt_task` (ChatGPT-originated) and poll `get_task_status` / `get_execution_result` until terminal state.
6. Verify websearch execution evidence in the result and OpenCode session ID.

## Explicit statement
**No service was started. No files, configuration, environment variables, or secrets were modified. No dependencies were installed. No tasks were executed.** This is a read-only preflight.

## Additional blocker discovered (startup entry point broken)
- `src/opencode_bridge/cli.py` imports `set_controller` and `app` from `mcp_server`, but neither exists in `mcp_server.py`. The documented `python -m opencode_bridge.cli` startup command **will fail with ImportError**.
- The actual HTTP server is `MCPServerHTTP` (stdlib `ThreadingHTTPServer`) in `mcp_server.py`, instantiated manually in tests (`MCPServerHTTP(mcp, host=..., port=...)` + `serve_forever()`). There is no CLI entry point for it.
- Therefore even after fixing dependencies and auth token, the documented startup command will not work. The operator must either fix `cli.py` or start `MCPServerHTTP` programmatically.

## Verdict: BLOCKED
Blockers:
1. Controller `.venv` missing required dependencies (fastapi, uvicorn, aiosqlite, requests) — RESOLVED in WP-CONTROLLER-ENV-001 (installed).
2. `MCP_AUTH_TOKEN` not configured (controller fails closed) — RESOLVED in WP-CONTROLLER-ENV-001 (configured, value not shown).
3. **NEW**: `cli.py` startup entry point is broken (imports non-existent `app`/`set_controller`). No working CLI to start the MCP HTTP server. Operator must repair cli.py or start MCPServerHTTP manually.
4. DB path points into the DEV F&O repo (`fno-ai-paper-trading-dev/.opencode_bridge/bridge.db`) — confirm workspace exists.

Operator must repair the startup entry point before TEST-OPENCODE-CONTROLLER-001 can be rerun. No service was started in this preflight.