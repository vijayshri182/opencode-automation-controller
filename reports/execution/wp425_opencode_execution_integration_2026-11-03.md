# WP-425 — Controller-to-OpenCode Execution Integration

**Date:** 2026-11-03
**Repository:** `C:\Vijay_GitHub\opencode-automation-controller` (`master`, no commits; all work untracked)
**Verdict:** Execution integration verified at mock/local-integration level. **Live OpenCode API verification BLOCKED** (no safe disposable workspace established; the existing `test_integration_opencode.py::test_integration_real_task` requires a live OpenCode API server and is pre-existing). The full ChatGPT ↔ OpenCode autonomous loop is **not** operational and is not claimed to be.

---

## 1. Existing components inspected and reused

- `OpenCodeAdapter` (`opencode_adapter.py`) — authenticated HTTP client for the official OpenCode server API. Uses `config.py` (`opencode_base_url`, `opencode_username`, `opencode_password`, `opencode_timeout`, `opencode_max_retries`, `opencode_retry_backoff`). No endpoint or credential was hardcoded.
- `TaskController` + `MockOpenCodeAdapter` — reused for the real-adapter integration test path.
- `TaskControllerExecutor` (`executors.py`) — reuses `TaskController` + `OpenCodeAdapter` behind the WP-423 `ExecutionInterface`. No new client, no provider/model change.
- `MissionOrchestrator` (`orchestrator.py`) — submission, polling, result persistence, reconciliation, state transitions.
- `BridgeDB` (`db.py`) — executions table, idempotency, atomic transactions, restart recovery.
- `contracts.py` — `contracts.execution` v1.
- `state_machine.py` — `OrchState` transitions.
- `FakeOpenCodeExecutor` — deterministic scenario double.

No component was rebuilt. Changes were additive.

---

## 2. Exact integration gaps discovered

1. **No persisted completion timestamp** — the executions table had `submitted_at` but no `started_at`/`completed_at`. Closed: added both columns (migration for old DBs) and populated them in `submit_and_execute` / `_persist_result`.
2. **No direct test of `TaskControllerExecutor`** against a real (mock) adapter — only `FakeOpenCodeExecutor` was exercised. Closed: added `test_task_controller_executor_with_mock_adapter` and friends.
3. **No test asserting timestamps persist** — closed.
4. **No test asserting state-machine consistency at each stage** — closed.

No other gaps were found: submission, session capture, polling, result retrieval, persistence, reconciliation, cooldown, auth, context exhaustion and interrupt handling were already implemented and correct.

---

## 3. Files and functions changed

- `src/opencode_bridge/db.py` — added `started_at`/`completed_at` columns to `executions` (schema + migration); added both to `insert_execution` and `update_execution` mapping.
- `src/opencode_bridge/orchestrator.py` — `submit_and_execute` sets `started_at`; `_persist_result` sets `completed_at`.
- `tests/test_wp425_opencode_execution.py` — new, 17 focused tests.

No changes to `opencode_adapter.py`, `executors.py` (logic), `controller_api.py`, `contracts.py`, `state_machine.py`, or existing tests.

---

## 4. Submission and session tracking behaviour

- `submit_and_execute` persists an execution row **before** calling the adapter (`insert_execution` returns False on conflict → duplicate, no resubmission).
- `TaskControllerExecutor.submit` calls `adapter.create_session(title=...)` then `adapter.send_prompt_async(session_id, prompt)`. If session creation fails → classified error, no session id. If prompt send fails after session creation → `OPENCODE_UNCERTAIN` with `opencode_session_id` persisted (so reconciliation can resume that exact session).
- Session id is persisted via `db.update_execution(opencode_session_id=...)` before state transition to `OPENCODE_EXECUTION`.
- `started_at` is set at submission; `submitted_at` records intent-persistence time.

---

## 5. Result retrieval and persistence guarantees

- `TaskControllerExecutor.poll` calls `adapter.get_messages(session_id)` and extracts the final assistant text via `extract_final_assistant`. Returns `completed` + `execution_output` + `changed_files` (from `git status --porcelain`) + `test_results` + `verification_evidence` (source `task_controller`, git status). Returns `running` if no assistant text yet (bounded by `timeout_seconds`).
- `MissionOrchestrator._collect_result` persists the result via `_persist_result` **only** when `polled.finished` is True, then sets task status to `completed` and enters `RESULT_PERSISTED`. Delivery never starts before this.
- `completed_at` is recorded at persistence time.
- `verification_evidence` carries provenance (`source`, `git_status`) and is distinguishable from controller-generated summaries.

---

## 6. Idempotency and reconciliation evidence

- **Persist-before-submit:** execution row exists before the adapter is called. A crash between intent and submission leaves a row with no session id → classified as failed/uncertain on recovery, never a silent duplicate.
- **Uncertain submission:** session id persisted even when prompt outcome is unknown → `RECONCILIATION_REQUIRED`; `recover()` calls `executor.reconcile()` (uses the persisted session id, never invents one) and `_collect_result` resumes polling the same session.
- **Interrupted execution:** `poll` failure → `EXECUTION_INTERRUPTED` + checkpoint; recovery collects the result without resubmitting.
- **Duplicate prevention:** `insert_execution` UNIQUE on `task_id`; second call returns `duplicate=True` with the original row. Verified: `submit_calls` stays at 1.
- **Delivery failure never re-executes:** `deliver_result` reuses the persisted execution; `submit_calls` stays at 1 across delivery retries (verified in `test_no_duplicate_execution_after_delivery_failure`).
- **No exactly-once claim:** the OpenCode API is treated as at-least-once for submissions; the controller guarantees at-most-once *from its side* via the UNIQUE constraint and reconcile-before-resubmit. If the API itself created a session but the response was lost, reconciliation via the persisted id recovers it; if no id was persisted, the outcome is `uncertain`/`RECONCILIATION_REQUIRED`, not a blind retry.

---

## 7. State-machine integration

Verified transitions (all already implemented, tests assert):
- `OPENCODE_SUBMISSION → OPENCODE_EXECUTION` (valid)
- `OPENCODE_EXECUTION → RESULT_PERSISTED` (valid)
- `RESULT_PERSISTED → CHATGPT_DELIVERY_PENDING` (valid)
- `RECONCILIATION_REQUIRED` / `EXECUTION_INTERRUPTED` / `QUOTA_EXHAUSTED` / `AUTHENTICATION_REQUIRED` are reachable and recoverable.
- `RESULT_PERSISTED` is entered only after `_persist_result` commits (verified by code path and tests).
- No ChatGPT message bypasses validation/approval/policy — `run_cycle` calls `evaluate_governance` and the approval gate before `submit_and_execute`.

---

## 8. Recovery and quota handling

- Bounded status polling: `poll(execution, timeout_seconds=...)` returns `running` when the deadline passes without an assistant message.
- Configurable execution timeout: `MissionOrchestrator.task_timeout_seconds` (passed to `poll`).
- Persisted retry budgets: `RetryPolicy` + `RetryBudget` (delivery); OpenCode cooldown via `provider_state`.
- Provider cooldown: rate-limited submission sets `available=False`, `cooldown_until`, `consecutive_failures`; `_gate_provider` blocks until cooldown expires (verified).
- HTTP 429 / Retry-After: `_classify_exception` maps 429/quota/rate-limit → `OPENCODE_RATE_LIMITED`/`OPENCODE_QUOTA_EXHAUSTED`; `retry_after` propagated.
- API disconnection: mapped to `OPENCODE_DISCONNECTED`; recovery via `recover()`.
- Session expiration: `get_messages` failure classified; reconcile returns `found=False` for unknown sessions.
- Context exhaustion: mapped to `OPENCODE_CONTEXT_EXHAUSTED` → `HUMAN_REVIEW_REQUIRED` + checkpoint.
- Interrupted execution reconciliation: checkpoint + `RECONCILIATION_REQUIRED` + `recover()` collects result.

Never silently switches providers or models (verified: no provider/model config touched).

---

## 9. Tests executed and results

| Suite | Tests | Result |
|---|---|---|
| `test_wp425_opencode_execution.py` (new) | 17 | pass |
| `test_wp423_orchestrator.py` | 35 | pass |
| `test_wp423_contracts.py` | 29 | pass |
| `test_wp423_persistence.py` | 17 | pass |
| `test_wp423_controller_api.py` | 19 | pass |
| `test_wp424_chatgpt_adapter.py` | 39 | pass |

Full suite: 197 passed / 1 failed — the single failure is `tests/test_integration_opencode.py::test_integration_real_task` (pre-existing, requires a live OpenCode API server).

No existing test was weakened, skipped or deleted.

---

## 10. Live OpenCode verification

**Blocked / not performed.** No safe disposable workspace was established and no live OpenCode API server was available in this environment (the existing `test_integration_opencode.py::test_integration_real_task` is the pre-existing live-API smoke test and remains failing separately). Verification was restricted to deterministic mocks (`FakeOpenCodeExecutor`, `MockOpenCodeAdapter` via `TaskControllerExecutor`) and is reported as such. No OpenCode API server, desktop application or worker was restarted; no production repository was modified.

---

## 11. Remaining limitations

1. `TaskControllerExecutor.poll` relies on the assistant producing a final text message; if OpenCode returns structured output without a text part, polling times out (returns `running`). A future milestone should support tool-call / structured result extraction.
2. `changed_files` comes from `git status --porcelain` of the workspace, which is a controller-side observation, not OpenCode-reported evidence. Provenance is labelled (`source: task_controller`).
3. `test_results` is empty from the real adapter path (OpenCode does not report test results in the message stream); tests must be parsed from `execution_output` or added separately.
4. Context-exhaustion detection during a long-running prompt is best-effort (classified from exception text).
5. Live verification against a real OpenCode API remains to be done (operator-gated, disposable workspace required).

---

## 12. Recommended WP-426 scope

1. Live OpenCode smoke test against a disposable workspace (operator-gated): submit one uniquely identified harmless task, verify session id, observe execution, retrieve output, persist result, verify no duplicate submission on reconciliation.
2. Structured result extraction from OpenCode messages (tool calls, file changes, test output).
3. Context-exhaustion and session-expiration handling hardening with real API error shapes.
4. Only after WP-426 verification, consider enabling the controller's automatic execution loop for ChatGPT-originated tasks.

**Files affected (new/modified, all untracked):** `src/opencode_bridge/db.py`, `src/opencode_bridge/orchestrator.py`, `tests/test_wp425_opencode_execution.py`, this report, and the memory handoff. **No changes to** `.env`, credentials, providers/models, browser/profiles, Edge, OpenCode, production repository, or existing tests.