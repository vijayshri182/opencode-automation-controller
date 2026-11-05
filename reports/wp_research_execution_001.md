# WP-RESEARCH-EXECUTION-001 — Secure Research Execution Pipeline (Implementation and Offline Validation)

Date: 2026-11-04
Repository: `C:\Vijay_GitHub\opencode-automation-controller` (branch `master`, no commits; all files untracked)
Mode: DEV only; implementation + offline validation with mocks/fakes. No live service, no commit/push.

## 1. Initial repository state and existing changes

- HEAD: `master` (no commits; working tree contains many pre-existing untracked files and modifications).
- Pre-existing research infrastructure reused (not rebuilt): `research_task` / `research_result` contracts and
  validators; `BridgeDB` research methods (`insert_research_task`, `get_research_task`,
  `get_research_task_by_idempotency`, `update_research_task`, `list_research_tasks`,
  `cancel_research_task`); `OpenCodeAdapter` (research_mode, agent, tools); MCP tool definitions
  (`submit_research_task`, `get_research_task_status`, `get_research_task_result`); research agent
  config (`config/research_agent.md`, `C:\Users\user\.config\opencode-research\opencode.jsonc`).
- Existing pending task `res-2eb40bb981db` preserved (not mutated, not retried).
- Live controller (PID 33028/6492) exposes 19 tools (no research tools — predates WP-RESEARCH-002);
  on-disk code now includes them. Not restarted (operator-gated).

## 2. Files changed and implementation summary

| File | Change |
|---|---|
| `src/opencode_bridge/research_executor.py` | **NEW** — `ResearchExecutor` + `_redact_value`/`_collect_secrets` helpers. |
| `src/opencode_bridge/db.py` | Added `cancel_requested`/`cancelled_at` columns to `research_tasks` (schema + migration); added `cancel_research_task()` helper. |
| `src/opencode_bridge/config.py` | Added `opencode_research_workspace()`. |
| `src/opencode_bridge/mcp_server.py` | Added optional `research_executor` param to `MCPServer.__init__`; submit path optionally spawns a daemon execution thread when `RESEARCH_AUTO_EXECUTE` is truthy. |
| `src/opencode_bridge/cli.py` | Wires a `ResearchExecutor` when a research base URL is configured. |
| `tests/test_wp_research_007.py` | **NEW** — 23 tests (see §5). |

No other production files modified. No `.env`, credential, provider or auth changes.

### 2.1 ResearchExecutor design

- `execute(research_id)` loads the task; returns cached result if already `completed`.
- Refuses to run if cancelled or already running (in-memory lock + DB cancel flag).
- Persists `status=running` + `started_at` before execution (fail-closed on DB error).
- Uses the dedicated research adapter (must have `research_mode=True`; otherwise raises — no fallback).
- Creates an OpenCode session in the research workspace with the research agent and the
  websearch/webfetch-only tool allowlist.
- Submits the prompt via `send_prompt_async`.
- Polls `get_messages` with bounded deadline (`timeout_seconds`, max 600), cancel-aware.
- Classifies: provider error (HTTP/adapter or assistant `info.error`), timeout (no assistant within
  deadline), empty output (assistant present but no text), invalid structured result, cancelled.
- Extracts assistant final text + actual tool calls (name, call_id, status, redacted input/output/error).
- Builds a `research_result` (validated via `validate_research_result`), adds execution metadata
  (started_at, duration, selected provider/model, agent, tool_names, tool_count).
- Persists `status=completed`, `session_id`, `completed_at`, `result_json` (idempotent: keeps existing
  if already completed).
- All tool inputs/outputs/errors are redacted (`_redact_value`): sensitive keys → `[REDACTED]`,
  collected secret values scrubbed from all strings, fields truncated to 4096 chars.
- Cancellation via `cancel()` (in-memory + DB flag), checked during polling.

## 3. MCP tools and schemas exposed

The three research tools were already defined in `mcp_server.py` (WP-RESEARCH-002) and now have an
executor wired behind them:

- `submit_research_task` — validates prompt/idempotency_key/timeout/max_results, dedups by
  idempotency key, inserts a `pending` row, optionally spawns a daemon execution thread when
  `RESEARCH_AUTO_EXECUTE` is truthy.
- `get_research_task_status` — returns status, created_at, started_at, completed_at, error.
- `get_research_task_result` — returns status, session_id, result (parsed `result_json`), error.

Schemas reuse `RESEARCH_TASK_SCHEMA` / `RESEARCH_RESULT_SCHEMA` from `contracts.py` (no competing
contracts). Result evidence items carry type (`SEARCH_SNIPPET`/`FULL_PAGE`), tool, call_id, status,
redacted input/output/error.

## 4. Execution architecture and state transitions

States: `pending → running → {completed, failed, cancelled, timeout}` (terminal). Transitions:
- `pending` → `running` (on execute start, persists started_at).
- `running` → `completed` (assistant output present and validated).
- `running` → `failed` (provider error, empty output, invalid result, exception).
- `running` → `timeout` (deadline exceeded with no assistant).
- `running` → `cancelled` (cancel requested during polling).
- `completed` → cached (idempotent re-execution returns existing result without re-running).
- `failed`/`timeout`/`cancelled` → re-runnable on next execute.

Idempotency: `insert_research_task` uses `ON CONFLICT DO NOTHING` on the unique idempotency key;
`submit_research_task` returns the existing row on duplicate. Executor refuses concurrent duplicate
execution via an in-memory lock keyed by research_id.

## 5. Database changes

- `research_tasks` gained `cancel_requested INTEGER NOT NULL DEFAULT 0` and `cancelled_at REAL`
  (schema updated for new DBs; ALTER TABLE migration for existing DBs, idempotent).
- No new tables. No migration scripts added beyond the inline ALTER (consistent with existing pattern
  for `executions.started_at`/`completed_at`).
- Existing pending task `res-2eb40bb981db` preserved (not mutated, not retried).

## 6. Permission / isolation verification

- `ResearchExecutor._run` raises `OpenCodeError("adapter is not in research_mode; refusing to run")`
  if the adapter is not in research mode → no fallback to the unrestricted dev instance.
- Research adapter uses `opencode_research_base_url()` (dedicated endpoint), `opencode_research_agent()`
  (`research`), `opencode_research_tools()` (websearch+webfetch only, all else false).
- Tool allowlist enforced at adapter construction and passed to `send_prompt_async`.
- Tests: `test_no_fallback_to_unrestricted_instance`, `test_research_permission_config_file`,
  `test_research_json_config_default_deny` verify deny-all + websearch/webfetch allow + bash/write/
  external_directory deny.

## 7. Automated test commands and results

Command (from repo root):
```
PYTHONPATH=src .venv/Scripts/python -m pytest tests/test_wp_research_007.py -q
```

Result: **23 passed in 29.25 s**, 0 failures, 0 errors.

Coverage: MCP tool registration & schemas; submission & retrieval; successful execution (mocked);
tool-call extraction; empty assistant response; provider quota/auth error (assistant error + adapter
exception); timeout & polling termination; cancellation (pre-execute); retry/idempotency (cached
completed, failed re-run); invalid structured output (contract validation); persistence & recovery
(reopen DB); permission config (md + jsonc); no unrestricted fallback; credential redaction
(key-based + secret scrubbing + truncation); concurrent submissions & state integrity; task-state
transitions; persistence failure handling; contract validation; redaction of tool errors.

Regression (existing suites, unchanged):
- `test_wp_research_005.py` + `test_opencode_bridge_core.py` + `test_wp430_mcp_server.py`: 56 passed.
- `test_wp423_persistence.py` + `test_wp423_orchestrator.py` + `test_wp425_opencode_execution.py`: 69 passed.

All automated tests use mocks/fakes; no live provider access, no service start/stop, no real external
communication.

## 8. Live HTTP test details

**Not performed.** Known blocker (from WP-RESEARCH-001..002): the dedicated research instance on
port 4098 returns `AI_APICallError: Free usage limit reached` for free models while the dev instance
on 4097 works. Per task boundaries, I did not restart/reconfigure either instance, did not copy
credentials, did not subscribe/purchase, and did not submit a real research task to the live controller.
The implementation is validated entirely with mocks/fakes. Live execution remains blocked by the
provider quota issue; this is reported separately and is not claimed as working.

## 9. OpenCode session IDs and evidence references

- No live session IDs were created by this WP (no live execution attempted).
- Mocked tests use synthetic session id `sess-1` (deterministic fixture, not a real session).
- Existing persisted research task `res-2eb40bb981db` (status `pending`, never executed) is preserved
  and was not mutated or retried, per task requirements.

## 10. Provider errors and unresolved limitations

- Provider quota blocker (`Free usage limit reached`) on the isolated research instance remains
  unresolved and is out of scope for this WP (operator-gated: subscription/credential provisioning).
- The live controller (PID 33028/6492) predates the research tools; a restart is required to expose
  `submit_research_task` / `get_research_task_status` / `get_research_task_result` live.
- `RESEARCH_AUTO_EXECUTE` defaults off; execution is triggered by calling `ResearchExecutor.execute()`
  (tests) or by setting the env var (operator decision).
- Result evidence is bounded (4096 chars/field, 50 items) and redacted; very large tool outputs are
  truncated.
- Cancellation is in-memory + DB flag; a process restart loses the in-memory set but the DB flag
  persists.

## 11. Security and operational boundary verification

- No credentials printed, copied, logged or committed. `_redact_value` scrubs sensitive keys and any
  collected secret value from all strings; Authorization headers/tokens/keys are never persisted.
- No fallback to the unrestricted dev OpenCode instance (enforced + tested).
- Research adapter requires `research_mode=True`; base URL, agent and tool allowlist come from dedicated
  config helpers (`opencode_research_*`).
- No `.env` changes, no provider/model/auth changes, no PROD changes, no service restart, no commits/pushes.
- No real external communication, no emails, no applications, no resume submissions.
- All automated tests use mocks/fakes; no live provider access required.

## 12. Final verdict

**PARTIAL** — The research execution pipeline is implemented and fully validated offline (23/23 new
tests pass; 125/125 regression tests pass). The three research MCP tools are wired to a secure, bounded,
isolated executor with idempotency, retry safety, redaction and persistence. However, live end-to-end
execution could not be proven because the dedicated research instance remains blocked by the OpenCode
provider free-usage quota issue (reported separately in WP-RESEARCH-001/002). A successful mocked test
is not claimed as a successful live OpenCode search.

## 13. Exact next recommended action

1. Operator provisions usable model quota for the research instance (OpenCode Go subscription or
   credential), then restarts the research instance (port 4098) with `--print-logs`.
2. Operator restarts the controller (operator-gated) so the on-disk research tools become live.
3. Set `RESEARCH_AUTO_EXECUTE=1` (or invoke `ResearchExecutor.execute()` from a worker) and submit one
   read-only research task (e.g. the Comviva Director – Product Management NGAGE CPaaS scenario) to
   verify `pending → running → completed` with a populated `session_id` and `result_json` containing
   actual websearch/webfetch tool calls.
4. If the provider quota issue persists, keep the implementation validated via mocks and report the
   blocker; do not subscribe/purchase without authorization.