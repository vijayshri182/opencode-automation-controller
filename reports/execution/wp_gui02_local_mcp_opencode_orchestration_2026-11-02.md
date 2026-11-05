# WP-GUI02 — Local MCP/OpenCode Orchestration Bridge

**Date:** 2026-11-02
**Repository:** `C:\Vijay_GitHub\opencode-automation-controller` (new utility repo)
**Target authorized workspace:** `C:\Vijay_GitHub\fno-ai-paper-trading-dev` (branch `dev/phase-13`)
**F&O DEV:** read-only reference; PROD untouched.

## 1. New repository location and Git status

- Path: `C:\Vijay_GitHub\opencode-automation-controller`
- Git: initialized (no commits, no remote).
- Working tree: untracked project files (no commits made).

## 2. Project structure

```
opencode-automation-controller/
  README.md
  .gitignore
  src/opencode_bridge/        (config, models, db, safety, opencode_adapter, controller, mcp_server, cli)
  tests/                      (core + MCP tests)
  docs/                      (architecture, mcp_tool_contract, security, tunnel checklist, design/WP-GUI01)
  config/example.env
  reports/execution/wp_gui02_...md
```

## 3. Implemented MCP tools

submit_task, approve_task, reject_task, get_task_status, get_task_result, list_recent_tasks, cancel_task.

Schemas documented in docs/mcp_tool_contract.md. No arbitrary shell/filesystem/process/repo-management tools.

## 4. OpenCode API verification status

Verified from official docs (opencode.ai/docs/server) and local CLI help:
- `opencode serve` HTTP API: /global/health, /session, /session/:id/prompt_async, /session/:id/message, /session/:id/abort.
- Adapter implemented against these endpoints. Mock adapter provided for deterministic tests.
- Real adapter requires OPENCODE_SERVER_PASSWORD and a running server; not exercised in tests.

## 5. Task lifecycle and persistence

SQLite tables: tasks, approvals, audit_events. Lifecycle implemented:
DRAFT -> VALIDATED -> AWAITING_APPROVAL -> QUEUED -> RUNNING -> COMPLETED/FAILED/BLOCKED/CANCELLED.
Approval bound to content hash; modification invalidates approval. Duplicate submission protection via idempotency key. Restart recovery marks interrupted running tasks as failed. Single worker, async polling, cancellation, timeouts.

## 6. Test results

15 tests passed, 1 warning (starlette deprecation). Coverage: validation, DEV/PROD path, approval/invalidation, duplicate, async status/result, failed task, cancel, persistence/recovery, missing result, secret redaction, working-tree preservation, MCP health/tools/validation/auth.

## 7. Safety validation

- Hard-coded DEV workspace; PROD rejected.
- No .env/secret reading; redaction.
- No commit/push/deploy/session launch/live orders.
- Supervised mode only; continuous chaining disabled.
- Path allowlist documented as not an OS sandbox.

## 8. Dependencies requiring authorization

- MCP Python SDK not installed; implemented JSON-RPC over HTTP manually (no install).
- Secure MCP Tunnel and ChatGPT workspace permissions not configured (out of scope).
- OpenCode permission config needs DEV path added for unattended runs.

## 9. Exact next implementation step

Phase 3: configure Secure MCP Tunnel + ChatGPT custom MCP server and perform end-to-end same-conversation loop; add GUI monitoring; harden cancellation/recovery/timeouts.