# WP-RESEARCH-010 — Controller-to-OpenCode Research E2E

Date: 2026-11-04
Repository: `C:\Vijay_GitHub\opencode-automation-controller` (branch `master`, no commits; all untracked)
Mode: DEV only. Controlled controller restart + live isolated research instance (port 4098) authorized
for this task. No PROD changes, no commits/pushes.

## 1. Initial and final service state, PIDs and ports

### Initial state (recorded before changes)
- Controller: PID 33028 (parent) / 6492 (child), cmd `python src/opencode_bridge/cli.py --port 8799`,
  health `{"ok": true, "service": "mcp_server"}`, exposed 19 tools (no research tools).
- Dev OpenCode 4096: PID 7132 (untouched). Dev OpenCode 4097: PID 29924 (untouched).
- Port 4098: FREE at start.

### Final state
- Controller: PID **30120** (new, restarted), cmd `python src/opencode_bridge/cli.py --port 8799`,
  env `OPENCODE_RESEARCH_BASE_URL=http://127.0.0.1:4098`, `RESEARCH_AUTO_EXECUTE=1`, `PYTHONPATH=src`,
  health `{"ok": true, "service": "mcp_server"}`, exposed 22 tools (incl. 3 research tools).
- Dev OpenCode 4096: PID 7132 (untouched). Dev OpenCode 4097: PID 29924 (untouched).
- Research OpenCode 4098: started PID 35248 for this task, then stopped; port 4098 FREE at end.
- DB: `C:\Vijay_GitHub\fno-ai-paper-trading-dev\.opencode_bridge\bridge.db` (unchanged path).

## 2. Controller tool inventory before and after restart

- Before: 19 tools — `controller_health, list_chatgpt_projects, get_chatgpt_project,
  set_active_chatgpt_project, discover_chatgpt_conversation, read_chatgpt_messages,
  get_chatgpt_observations, get_chatgpt_reader_state, get_chatgpt_observer_status,
  start_chatgpt_observer, stop_chatgpt_observer, acknowledge_chatgpt_message,
  get_unread_chatgpt_messages, get_chatgpt_message_history, get_controller_capabilities,
  get_task_status, get_execution_result, submit_chatgpt_task, approve_chatgpt_task`.
- After: 22 tools — same 19 plus `submit_research_task`, `get_research_task_status`,
  `get_research_task_result`. Research tools now live.

## 3. Exact model and OpenCode session ID

- Requested model: `opencode-go/beam-free` (providerID `opencode-go`, modelID `beam-free`).
- Selected model (from session): `opencode-go/beam-free` (matches requested).
- Agent: `research` (research_mode=True, deny-all + websearch/webfetch allowlist).
- OpenCode session ID: **`ses_e5aedb640ffeP2UoNyUYPbftCh`** (created on port 4098).
- Research task ID: `res-0b2ccd2a729c`. Idempotency key: `comviva-poc-e2e-002`.

## 4. MCP request and response evidence (secrets redacted)

- `submit_research_task` → `{"ok": true, "research_id": "res-0b2ccd2a729c", "duplicate": false,
  "status": "pending"}`.
- Polling `get_research_task_status`: `pending` → `running` (started_at 1793770800.33) → `completed`
  (completed_at 1793770873.47), error null.
- `get_research_task_result` → status `completed`, session_id `ses_e5aedb640ffeP2UoNyUYPbftCh`,
  result with 12 evidence items, output (3015 chars), no error.
- Idempotency: re-submitting with the same idempotency key `comviva-poc-e2e-002` returned
  `{"ok": true, "research_id": "res-0b2ccd2a729c", "duplicate": true, "status": "completed"}` —
  no duplicate execution started.
- No Authorization header, token or secret appears in any persisted field or report.

## 5. Tool-call evidence and source URLs

- 12 tool calls, all `status: completed`, no errors:
  - 11 × `websearch` (queries on the Comviva NGAGE CPaaS Director PM role, recruiter talent-acquisition
    contacts, Naukri/LinkedIn/Comviva careers, email evidence, etc.)
  - 1 × `webfetch` (URL: `https://in.linkedin.com/jobs/view/director-product-management-ngage-cpaas-at-comviva-4474132885`,
    retrieved the LinkedIn job page)
- No `bash`/`write`/`edit`/`read`/`glob`/`grep`/`list`/`task`/`todowrite` invoked.
- Tool inputs/outputs persisted in `result_json.evidence` (redacted, truncated to 4096 chars/field).
- Final structured output includes:
  - Job ID **4474132885** (LinkedIn) and aggregator ID `eadbca7af701cd8a71a39a489a7f8be1f` (Jobleads).
  - Job title: Director - Product Management (NGAGE CPaaS); Company: Comviva; Location: Bengaluru,
    Karnataka, India (on-site); posting date ambiguous (relative "1 month ago"; Jobleads
    `datePosted: 2026-10-21`).
  - Recruiter contacts with publicly evidenced emails: `Anam.khan@comviva.com`,
    `bharti.choudhary1@comviva.com`, `soma.sen@comviva.com` (classified as adjacent — general TA
    posts, not directly tied to this requisition).
  - General product/leadership contacts (Tarun Arora, Deshbandhu Bansal, Aishwarya Patil, Ravi
    Shankar, Jiwateshwar Singh, Jens Voigt) — classified as NOT recruiters for this role.
  - Unavailable info explicitly marked (named job poster, role-specific recruiter email, definitive
    posting date, Comviva-owned career-portal job ID).
  - Source URLs and concise excerpts for every material finding.
- Full output persisted in `result_json.output` (3015 chars).

## 6. Database persistence evidence

- `research_tasks` row `res-0b2ccd2a729c`: status `completed`, `session_id` =
  `ses_e5aedb640ffeP2UoNyUYPbftCh`, `started_at` 1793770800.33, `completed_at` 1793770873.47,
  `error` null, `cancel_requested` 0, `result_json` populated (status completed, 12 evidence items,
  tool_names, requested/selected model beam-free, agent research, duration 73.14 s).
- `result_json.output` contains `4474132885`. `result_json.evidence` contains 12 tool-call records
  with redacted inputs/outputs.
- Idempotency verified: duplicate submit returned `duplicate: true` with the same `research_id` and
  `status: completed`; no second execution.
- Pre-existing pending task `res-2eb40bb981db` preserved (status `pending`, session_id null) — not
  mutated or retried.

## 7. Idempotency and error-handling test results

- Idempotency: PASS (duplicate submit returns duplicate=true, no re-execution).
- Offline failure/timeout/cancellation behavior: covered by `tests/test_wp_research_007.py` (23/23 pass),
  including: empty assistant response → `failed` (empty_output); provider quota/auth error → `failed`;
  timeout → `timeout`; cancellation (pre-execute) → `cancelled`; invalid structured output → `failed`;
  persistence failure → handled without crash; credential redaction.
- No live failure scenario was induced (would require provider quota exhaustion, which did not occur
  with `opencode-go/beam-free`).

## 8. Tests executed and results

- `tests/test_wp_research_007.py`: **23 passed** (29.15 s) — executor, persistence, idempotency,
  cancellation, timeout, empty output, provider error, redaction, permission config, no-fallback,
  concurrency, state integrity.
- Regression: `test_wp_research_005.py` + `test_opencode_bridge_core.py` + `test_wp430_mcp_server.py`:
  **56 passed**.
- Regression: `test_wp423_persistence.py` + `test_wp423_orchestrator.py` + `test_wp425_opencode_execution.py`:
  **69 passed**.
- Total: **148 passed, 0 failed** (excluding pre-existing httpx env gap in `test_opencode_bridge_mcp.py`).

## 9. Changed files

- `src/opencode_bridge/research_executor.py` — MODIFIED: configurable `model_provider`/`model_id`
  (default `opencode-go`/`beam-free`), model passed to `send_prompt_async`, requested/selected model
  persisted in result.
- `src/opencode_bridge/config.py` — MODIFIED: added `opencode_research_model_provider()` /
  `opencode_research_model_id()`.
- `src/opencode_bridge/cli.py` — MODIFIED: use absolute imports for research executor wiring (fixes
  relative-import failure in script mode).
- `src/opencode_bridge/mcp_server.py` — MODIFIED (WP-RESEARCH-007): optional `research_executor` param
  + optional auto-execute thread.
- `src/opencode_bridge/db.py` — MODIFIED (WP-RESEARCH-007): `cancel_requested`/`cancelled_at` columns +
  migration + `cancel_research_task()`.
- `tests/test_wp_research_007.py` — NEW (23 tests).
- `reports/wp_research_010.md` — NEW (this report).
- `reports/evidence/wp_research_010/` — NEW (controller.out.log, controller.err.log, serve.out.log,
  serve.err.log, e2e_summary.json, wp009_probe_results.json).
- Helper scripts: `scripts/tmp_wp_research_010_e2e.py`, `scripts/tmp_wp_research_010_summary.py`,
  `scripts/tmp_e2e_check.py`, `scripts/tmp_e2e_persist.py`.
- No `.env`, credential, provider, auth or PROD changes. No commits/pushes.

## 10. Remaining gaps and final verdict

### Remaining gaps
1. The live controller was restarted (authorized) and now exposes research tools, but the original
   controller process (PID 33028/6492) was stopped; the new process (PID 30120) runs with
   `RESEARCH_AUTO_EXECUTE=1`. If the operator wants the prior (non-auto-execute) behavior, restart
   without that env var.
2. The `ResearchExecutor` model selection is constructor-configurable but not yet exposed as an MCP
   parameter; submit uses the executor's configured model. A future WP could add a `model` field to
   `submit_research_task`.
3. Failure/timeout/cancellation were validated offline (mocks), not live (live run succeeded).
4. The pending task `res-2eb40bb981db` remains pending (preserved, not retried) — operator may retry
   or cancel separately.

### Final verdict: **PASS**

All WP-RESEARCH-010 acceptance criteria met:
1. Three research MCP tools registered and live (22 tools total): **PASS**.
2. Research request accepted and persisted (`res-0b2ccd2a729c`, pending → running → completed): **PASS**.
3. Worker executed through isolated OpenCode adapter (session `ses_e5aedb640ffeP2UoNyUYPbftCh`,
   model `opencode-go/beam-free`): **PASS**.
4. Actual websearch (11) + webfetch (1) tool calls retrieved and persisted (12 evidence items): **PASS**.
5. Final structured research result retrievable through MCP (`get_research_task_result`): **PASS**.
6. Failures and provider quota errors correctly represented (offline tests + persisted error field): **PASS**.
7. Idempotency and bounded execution work (duplicate submit → duplicate=true; timeout_seconds 180): **PASS**.
8. All automated regression tests pass (148 passed): **PASS**.
9. Existing ChatGPT controller functionality unaffected (no changes to chatgpt tools/executor): **PASS**.

A mocked test is not an end-to-end PASS — the live E2E above (res-0b2ccd2a729c, completed, with real
websearch/webfetch tool calls and job ID 4474132885) is the end-to-end proof. The offline failure/
timeout/cancellation tests separately validate those paths with mocks.

### Exact next recommended action
Operator-gated: (1) optionally restart the controller without `RESEARCH_AUTO_EXECUTE` if synchronous
execution is not desired; (2) optionally extend `submit_research_task` to accept a `model` field;
(3) use the now-live research tools for read-only research tasks; (4) no commits/pushes, no service
restarts without authorization, no credential changes.