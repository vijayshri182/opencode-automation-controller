# WP-CONTROLLER-STARTUP-002 — Repair and Validate Controller CLI

## Root cause and repair summary
`cli.py` imported non-existent `app`/`set_controller` from `mcp_server` and ran `uvicorn` (FastAPI), but the actual server is `MCPServerHTTP` (stdlib `ThreadingHTTPServer`) requiring a `MissionOrchestrator`. Rewrote `cli.py` to construct `MissionOrchestrator` + `MCPServer` + `MCPServerHTTP`, call `serve_forever()`, and handle `KeyboardInterrupt` with graceful shutdown.

## Files changed
- `src/opencode_bridge/cli.py` — full rewrite (imports fixed, build_server/build_orchestrator helpers, serve_forever, graceful shutdown).

## Constructor/lifecycle wiring
- `build_orchestrator(db, workspace, mock=...)` → `MissionOrchestrator(db, chat, executor, mission_id=..., workspace=..., allowed_repositories=[workspace], retry_policy=..., delivery_retry_policy=..., task_timeout_seconds=300.0)`.
- `build_server(host, port, db_path, mock, workspace)` → validates loopback host, creates DB, orchestrator, `MCPServer(orchestrator, token_provider=lambda: mcp_auth_token())`, `MCPServerHTTP(mcp, host, port)`.
- `main()` → parses args, calls `build_server`, `create_http_server()`, `serve_forever()`, catches KeyboardInterrupt, shuts down + closes.

## Tests and exact results
- Manual verification (in-process, not production start): health 200, no-auth 401, valid auth 200 with 19 tools (including controller_health), invalid auth 401. PASS.
- `test_wp430_mcp_server.py` + `test_auth_basic.py` + `test_wp423_contracts.py` + `test_wp423_controller_api.py`: 82 passed.
- JS/Python parse: OK.

## Authentication and network-safety validation
- Loopback host enforced (ValueError otherwise).
- Bearer token required; missing/invalid → 401; valid → 200.
- Max body 64KB enforced (413).
- No external network exposure.

## Final Git status
- No commits (repo has no commits). Working tree: existing untracked files preserved; `cli.py` modified (was untracked, now modified). No source files deleted. Temp file removed.

## Remaining limitations
- ChatGPT adapter in real mode uses a placeholder `FakeChatGPTAdapter` (live ChatGPT loop requires Edge CDP, not available in CLI startup). OpenCode adapter is real when not in mock mode.
- No signal handling beyond KeyboardInterrupt (no SIGTERM handler). Acceptable for local dev.
- DB path defaults into the DEV F&O repo workspace.

## Exact proposed startup command
```powershell
cd C:\Vijay_GitHub\opencode-automation-controller
$env:PYTHONPATH = "src"
$env:OPENCODE_BASE_URL = "http://127.0.0.1:4097"
$env:OPENCODE_SERVER_PASSWORD = "<from .env>"
$env:MCP_AUTH_TOKEN = "<configured>"
$env:OPENCODE_MOCK = "0"
python -m opencode_bridge.cli --port 8799
```

## Explicit confirmation
No service was started during this task. The verification used an in-process test server (port 0, ephemeral) that was shut down. Controller remains stopped.

## Verdict: READY FOR OPERATOR STARTUP AUTHORIZATION