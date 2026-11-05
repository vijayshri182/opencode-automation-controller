# WP-CONTROLLER-STARTUP-001 — Minimal MCP Server Startup Repair Specification

## Actual server architecture
- HTTP transport: `MCPServerHTTP` in `mcp_server.py` — a stdlib `ThreadingHTTPServer` wrapper (not FastAPI). `create_http_server()` returns a `ThreadingHTTPServer` with daemon threads.
- Protocol: JSON-RPC 2.0 over HTTP POST at `/mcp`; `GET /health` returns `{"ok": true, "service": "mcp_server"}`.
- Core logic: `MCPServer` (JSON-RPC dispatch + tool calls). Requires an `orchestrator` object exposing `status_report()`, `.db` (BridgeDB), `.state()`, `submit_chatgpt_task`, `approve_chatgpt_task`, etc.
- The orchestrator used by the MCP server is `MissionOrchestrator` (WP-423), NOT `TaskController` (older class used by `cli.py`).

## Constructor and lifecycle contract
- `MCPServerHTTP(mcp_server: MCPServer, host="127.0.0.1", port=8799)` — validates host is loopback.
- `create_http_server()` → `ThreadingHTTPServer`. Caller must `serve_forever()` in a thread and `shutdown()`/`server_close()` on exit.
- `MCPServer(orchestrator, token_provider=None, ...)`. `token_provider` defaults to `controller_api_token` (returns env `MCP_AUTH_TOKEN` or `""`). If empty, `_auth_ok` fails closed (all calls 401).
- Lifecycle: tests instantiate `MCPServerHTTP(mcp, host, port)`, call `create_http_server()`, start a daemon thread with `serve_forever()`, then `shutdown()` + `server_close()`. No signal handling, no graceful shutdown hook, no logging beyond `logger.info`.

## Exact root cause of the broken CLI
`cli.py` (line 15) imports `set_controller` and `app` from `mcp_server`, but neither symbol exists there. Additionally, `cli.py` builds a `TaskController` (older class) and runs `uvicorn.run(app, ...)` (FastAPI app that doesn't exist). The MCP server is stdlib-based and requires a `MissionOrchestrator`. So `cli.py` is entirely stale relative to the current `mcp_server`/`MissionOrchestrator` architecture.

## Proposed minimal code changes (for operator authorization)
1. Replace `cli.py` body to:
   - Load config, DB (`BridgeDB`), OpenCode adapter (real or mock per `OPENCODE_MOCK`), and construct a `MissionOrchestrator` (db, chat adapter, executor, workspace, retry policies) — mirroring `tests/test_wp430_mcp_server.py::make_orchestrator` but with real adapters.
   - Construct `MCPServer(orchestrator, token_provider=lambda: mcp_auth_token())`.
   - Construct `MCPServerHTTP(mcp, host, port)`, call `create_http_server()`, start `serve_forever()` in a thread or main thread.
   - Handle `KeyboardInterrupt` → `server.shutdown()` + `server.server_close()`.
2. Ensure `OPENCODE_BASE_URL`/`OPENCODE_SERVER_PASSWORD` are read (already via config + .env).
3. Ensure host is loopback (already validated by MCPServerHTTP).
4. Add a `--db` override (already in cli args) and `--mock` flag (already).

Alternatively, create a new minimal entry point (e.g., `python -m opencode_bridge.mcp_server --port 8799`) that performs the above wiring, leaving `cli.py` deprecated.

## Test plan
- Import smoke: `python -c "from opencode_bridge.mcp_server import MCPServer, MCPServerHTTP; ..."` (already passes with deps installed).
- Unit: instantiate MCPServerHTTP with a test orchestrator, start serve_forever in a thread, GET /health → 200, POST /mcp initialize → capabilities, then shutdown. (Pattern already in test_wp430_mcp_server.py.)
- Integration: start with real OpenCode adapter (mock first), verify controller_health returns OpenCode connectivity status.
- Auth: missing token → 401; valid token → 200 (test_wp430_mcp_server already covers).
- No duplicate instance: bind failure on occupied port should error cleanly.

## Startup command proposed (NOT executed)
```powershell
cd C:\Vijay_GitHub\opencode-automation-controller
$env:PYTHONPATH = "src"
$env:OPENCODE_BASE_URL = "http://127.0.0.1:4097"
$env:OPENCODE_SERVER_PASSWORD = "<from .env>"
$env:MCP_AUTH_TOKEN = "<configured>"
$env:OPENCODE_MOCK = "0"
python -m opencode_bridge.cli --port 8799   # after cli.py repair
```

## Network/security considerations
- Loopback only (host validated). No external exposure.
- Bearer token auth (fails closed if unset).
- Max body 64KB (MAX_BODY_BYTES). Oversized → 413 + connection close.
- No TLS (local only, acceptable).
- daemon_threads=True; shutdown via server.shutdown().

## Git preservation evidence
- Branch: master, no commits. Working tree: untracked files preserved. No tracked files modified by this diagnosis. No secrets printed.

## Verdict: READY FOR CODE-CHANGE AUTHORIZATION
All blockers are now identified. The minimal repair is a cli.py rewrite (or new entry point) wiring MissionOrchestrator + MCPServer + MCPServerHTTP.serve_forever. Dependencies and auth token are configured (WP-CONTROLLER-ENV-001). OpenCode server reachable on 4097. No other blockers. Operator authorization required before modifying cli.py.