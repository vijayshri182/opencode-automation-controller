# WP-GUI03 — Secure MCP Tunnel and ChatGPT Integration

**Date:** 2026-11-02
**Repository:** `C:\Vijay_GitHub\opencode-automation-controller`
**Target authorized workspace:** `C:\Vijay_GitHub\fno-ai-paper-trading-dev` (branch `dev/phase-13`)

## Status classification summary

| Item | Status |
|---|---|
| Repository/root verification | PASS |
| MCP server startup & tool discovery | PASS |
| All five required tools present | PASS |
| MCP tool schemas | PASS |
| Task submission/status/result | PASS |
| Approval enforcement | PASS |
| Duplicate protection | PASS |
| Error & timeout handling | PASS |
| Secret redaction | PASS |
| Restart recovery | PASS |
| Real OpenCode API health (v1.18.30) | PASS |
| Local-only binding (127.0.0.1) | PASS |
| Authenticated MCP access (optional bearer) | PASS |
| Tunnel product availability | PASS (documented) |
| ChatGPT custom MCP connection | BLOCKED — USER AUTHORIZATION REQUIRED |
| Secure MCP Tunnel creation/config | BLOCKED — USER AUTHORIZATION REQUIRED |
| Same-conversation round trip demonstrated | BLOCKED — USER AUTHORIZATION REQUIRED |
| Continuous autonomous chaining | NOT ENABLED (by design) |

## Phase A — Integration readiness audit

- MCP server: FastAPI on 127.0.0.1 only; JSON-RPC 2.0 at `/mcp`; health at `/health`. Supports initialize, tools/list, tools/call, ping, notifications/initialized.
- MCP protocol: ChatGPT supports SSE and streaming HTTP. Current server responds with JSON for POST (streaming HTTP compatible). GET /mcp SSE stream is not implemented; if ChatGPT requires a server-to-client SSE stream, add a GET handler. Classified as a minor compatibility risk.
- OpenCode adapter real path verified: `opencode serve` health returned `{'healthy': True, 'version': '1.18.30'}`.
- Auth: optional `MCP_AUTH_TOKEN` bearer; if unset, no app-level auth (tunnel/workspace permissions still apply).
- Payload limits: tunnel 10 MiB serialized envelope, 120 s request deadline, 600 req/min. Controller returns compact digests; long work is async.
- Polling/timeouts: implemented with configurable timeout and cancellation.

## Phase B — Prepared configuration

- `config/example.env` documents local env vars (no secrets).
- `MCP_AUTH_TOKEN` optional; if set, ChatGPT must be configured with matching static credentials or OAuth depending on chosen auth mode.
- No inbound listeners; all bindings loopback.
- No PROD workspace access; authorized workspace hard-coded to DEV.

## Phase C — Integration tests

Full suite: 20 passed, 1 warning (starlette deprecation). Covers validation, DEV/PROD, approval/invalidation, duplicate, async status/result, failed/interrupted tasks, cancellation, persistence/recovery, missing/malformed result, secret redaction, working-tree preservation, MCP health/tools/validation/auth, timeout, restart recovery, size limit.

## Phase D — Supervised end-to-end validation

Not performed. Requires user-authorized account/workspace/tunnel actions. Local supervised loop (submit → approve → run → result) is covered by tests but is not a ChatGPT round trip.

## Exact manual steps (user authorization required)

1. Create tunnel in OpenAI Platform tunnel settings; associate with target ChatGPT workspace + Platform org.
2. Grant Tunnels Read/Manage/Use permissions to operator.
3. Install and run `tunnel-client` outbound (no inbound ports).
4. In ChatGPT Plugins: Add custom MCP server → Connection: Tunnel → select tunnel → configure auth → acknowledge risk → Create as plugin → install.
5. Verify tool discovery and run a harmless test task; retrieve result in same conversation.
6. Confirm approval cannot be bypassed and PROD cannot be targeted.

## Limitations

- No same-conversation round trip demonstrated yet.
- Path allowlist is not an OS sandbox.
- Real OpenCode execution not exercised with a live task (only health).
- ChatGPT SSE GET stream not implemented; may be needed depending on client.