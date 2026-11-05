# WP-430 — Direct ChatGPT-to-Controller Integration (MCP-First Architecture)

**Date:** 2026-11-03
**Repository:** `C:\Vijay_GitHub\opencode-automation-controller` (`master`, no commits; all work untracked)
**Verdict:** **PASS (local MCP integration verified).** The MCP server adapter is implemented and verified against a local test client. Actual ChatGPT connectivity is **not** claimed — no supported ChatGPT client connection was completed. The autonomous ChatGPT ↔ OpenCode loop is **not** operational.

---

## 1. Executive verdict

**PASS (local MCP integration verified).** A dedicated MCP server adapter (`mcp_server.py`) exposes the existing controller services via Streamable HTTP (JSON-RPC 2.0). Six tools are implemented: `controller_health`, `get_controller_capabilities`, `get_task_status`, `get_execution_result`, `submit_chatgpt_task`, `approve_chatgpt_task`. All delegate to the existing `MissionOrchestrator` and `BridgeDB` — no business logic is duplicated. 32 focused tests pass. Live ChatGPT connectivity is **not** claimed.

---

## 2. Existing components inspected and reused

- `MissionOrchestrator` — task creation, governance, submission, execution, delivery, recovery.
- `BridgeDB` — persistent inbox, tasks, executions, deliveries, approvals, provider state, checkpoints.
- `contracts.py` — versioned contract validation.
- `state_machine.py` — explicit state transitions.
- `TaskControllerExecutor` / `FakeOpenCodeExecutor` — execution interface.
- `ChatGPTInterface` / `PlaywrightChatGPTAdapter` — preserved as legacy/fallback.
- `controller_api.py` — loopback auth pattern reused for MCP HTTP wrapper.

No component was rebuilt. The MCP layer is a thin transport + schema + auth adapter.

---

## 3. Architecture

```
ChatGPT (or any MCP client)
  → Streamable HTTP (JSON-RPC 2.0) → /mcp endpoint
  → MCPServer (auth, schema validation, tool dispatch)
  → MissionOrchestrator / BridgeDB (existing controller services)
  → TaskControllerExecutor → OpenCodeAdapter → OpenCode API
  → Controller returns status and execution evidence via MCP response
```

No second orchestration engine. The MCP adapter delegates entirely to the existing controller.

---

## 4. MCP tools implemented

### Read-only tools
- `controller_health` — returns controller status report (state, mission, providers, inbox, etc.).
- `get_task_status` — returns task status, execution ID, execution status, state by task_id.
- `get_execution_result` — returns persisted execution result (output, changed files, test results, timestamps, evidence) by execution_id or task_id.
- `get_controller_capabilities` — returns supported tools, execution mode, persistence type, governance status.

### Task intake tool
- `submit_chatgpt_task` — accepts structured message (message_id, project_id, conversation_id, message_content, correlation_id, repository, branch). Validates schema, checks repository/branch governance, persists task identity before execution, returns task_id, approval_required, state. Duplicate messages return existing task identity.

### Approval tool
- `approve_chatgpt_task` — requires explicit `approved_by` (separate from submission). Binds to persisted task. Rejects if task not in approvable state. Preserves `WAITING_FOR_APPROVAL` governance model.

---

## 5. Security and transport

- **Loopback only:** `MCPServerHTTP` raises if host is not in `{"127.0.0.1", "localhost", "::1"}`. Default bind: `127.0.0.1`.
- **Bearer token auth:** `hmac.compare_digest` (no timing leak). Fails closed if token unset (401).
- **Body bounded:** `MAX_BODY_BYTES = 64 KiB`. Oversized → 413.
- **No credentials logged:** access log records method/path only.
- **No tunnel/exposure:** No tunnel launched, no port published, no firewall changed.
- **Request limits:** body size limit. Timeouts via http.server defaults.
- **Replay protection:** idempotent submission via `message_id` primary key.
- **Audit logging:** all operations audited via `BridgeDB.audit_orch`.

### ChatGPT connectivity requirements (documented, not implemented)
- ChatGPT custom MCP requires HTTPS endpoints.
- ChatGPT Free plan does **not** support custom MCP servers (requires Plus/Team/Enterprise).
- OpenAI Secure MCP Tunnel can expose a local server privately, but was **not** launched (operator approval required).
- Static bearer tokens may not be accepted by all ChatGPT MCP clients; OAuth 2.1 is recommended for production.

---

## 6. ChatGPT response workflow

Asynchronous execution flow:
1. ChatGPT calls `submit_chatgpt_task` → receives task_id, approval_required, state.
2. If approval required, a human calls `approve_chatgpt_task` (separate tool, separate authorization).
3. ChatGPT calls `get_task_status` → receives task_status, execution_status, state.
4. ChatGPT calls `get_execution_result` → receives actual persisted output, changed files, test results, timestamps, evidence.

No Playwright needed for result delivery — the MCP response itself carries the result.

---

## 7. Tests

32 focused tests in `test_wp430_mcp_server.py`:

| Category | Tests | Result |
|---|---|---|
| Tool definitions | 2 | pass |
| JSON-RPC dispatch | 5 | pass |
| controller_health | 1 | pass |
| get_controller_capabilities | 1 | pass |
| submit_chatgpt_task | 6 | pass |
| get_task_status | 3 | pass |
| get_execution_result | 2 | pass |
| approve_chatgpt_task | 4 | pass |
| Auth (HTTP) | 2 | pass |
| Oversized body (HTTP) | 1 | pass |
| Health endpoint (HTTP) | 1 | pass |
| Unknown path (HTTP) | 1 | pass |
| Persistence across restart | 1 | pass |
| No duplicate execution | 1 | pass |
| **Total** | **32** | **pass** |

Full regression: WP-423 (100) + WP-424 (39) + WP-425 (17) + WP-427 (13) + WP-430 (32) = 201 tests, all pass.

No mocks presented as live connectivity. Live ChatGPT connection is **not** claimed.

---

## 8. Live verification boundaries

- **Local MCP protocol:** Verified (JSON-RPC 2.0, tool discovery, tool calls, auth, oversized body, persistence, no duplicate execution).
- **Actual ChatGPT connectivity:** **Not performed.** No supported ChatGPT client connection was completed. ChatGPT Free plan does not support custom MCP servers.
- **Actual OpenCode execution:** Verified in WP-426 (separate milestone). WP-430 tests use `FakeOpenCodeExecutor`.
- **Secure MCP Tunnel:** Not launched (operator approval required).
- **No server restart, credential change, external exposure or production modification.**

---

## 9. Security and operator setup guide

### Operator setup for ChatGPT custom MCP (future, not performed)

1. **Plan requirement:** ChatGPT Plus/Team/Enterprise (Free plan does not support custom MCP).
2. **Transport:** Streamable HTTP over HTTPS. The controller's MCP endpoint is loopback-only; OpenAI Secure MCP Tunnel (or equivalent) is needed for private server exposure.
3. **Authentication:** The MCP server uses Bearer token auth. ChatGPT may require OAuth 2.1 for production use. Static bearer tokens may not be accepted by all clients.
4. **Endpoint:** `POST /mcp` (JSON-RPC 2.0). `GET /health` for health check.
5. **Tools:** 6 tools (4 read-only, 1 intake, 1 approval).
6. **No tunnel launched, no port published, no firewall changed.**

### Security properties
- Loopback by default (no external exposure).
- Bearer token with `hmac.compare_digest` (no timing leak).
- Fails closed on auth failure (401).
- Body bounded at 64 KiB (413 on oversized).
- No credentials/tokens/headers logged.
- Idempotent submission (message_id primary key).
- Governance enforced on every task (repository, branch, scope, credentials, destructive ops, production boundaries).
- Approval separate from submission (human authorization required for write tasks).

---

## 10. ChatGPT Free-plan limitations

- ChatGPT Free plan does **not** support custom MCP servers.
- Custom MCP requires ChatGPT Plus, Team or Enterprise.
- Even with a paid plan, the server must be reachable via HTTPS (OpenAI Secure MCP Tunnel or equivalent).
- Static bearer token auth may not be accepted; OAuth 2.1 is recommended.
- The current conversation (this session) **cannot** invoke the new MCP tools — they are not connected.

---

## 11. Remaining risks

1. **Live ChatGPT connectivity unverified:** No actual ChatGPT client connection was completed. The MCP protocol is verified locally only.
2. **OAuth 2.1 not implemented:** The MCP server uses static bearer token auth. Production use may require OAuth 2.1.
3. **HTTPS not configured:** The server is HTTP loopback only. A tunnel or reverse proxy is needed for ChatGPT connectivity.
4. **ChatGPT Free plan limitation:** Users on Free plan cannot use custom MCP servers.
5. **No autonomous loop:** The full ChatGPT ↔ OpenCode loop is not operational. WP-431+ milestones needed.

---

## 12. Recommendation for WP-431

1. **Operator action:** Upgrade to ChatGPT Plus/Team/Enterprise if custom MCP is needed.
2. **Operator action:** Set up OpenAI Secure MCP Tunnel (or equivalent) for HTTPS exposure (operator approval required).
3. **WP-431:** Implement OAuth 2.1 for MCP authentication (if needed for ChatGPT compatibility).
4. **WP-432:** Live ChatGPT connection test (operator-gated, no task execution).
5. **WP-433:** Single harmless communication test through MCP (operator-authorized).
6. Only after WP-433, consider enabling the controller loop for ChatGPT-originated tasks.

**Files affected (WP-430):**
- `src/opencode_bridge/mcp_server.py` (new: MCPServer, MCPServerHTTP, 6 tools, JSON-RPC dispatch, auth, transport)
- `tests/test_wp430_mcp_server.py` (new: 32 tests)
- This report and the memory handoff

**No changes to:** `.env`, credentials, providers/models, browser/profiles, Edge, OpenCode server settings, production repository, or existing tests. No commits or pushes. No server restart. No tunnel launched. No port published. No credential changes. No browser interaction. No live task execution. No live ChatGPT connection claimed.