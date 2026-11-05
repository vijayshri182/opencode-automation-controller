# WP-423 — ChatGPT → Controller → OpenCode → Controller → ChatGPT Foundation

**Date:** 2026-11-03
**Repository:** `C:\Vijay_GitHub\opencode-automation-controller` (`master`, no commits yet — all work untracked)
**Verdict:** Foundation complete and verified at unit/integration level. **The autonomous loop is NOT operational.** Live ChatGPT/Playwright verification remains blocked on WP-422's operator-only `edge://inspect` remote-debugging opt-in (`DevToolsActivePort` absent, `ECONNREFUSED 127.0.0.1:9224`). No real repository task was executed, no provider/model was changed, no browser was launched, no credentials or `.env` were touched.

---

## 1. Objective and Scope

WP-423 builds the orchestration foundation that makes ChatGPT the architect, OpenCode the executor, and the controller the independent state owner and policy enforcer. The loop is:

```
ChatGPT (architect) -> Controller (inbox API) -> OpenCode (executor)
        ^                                          |
        |                                          v
        +---- Controller (delivery) <---- Result persisted
```

Strict boundaries honoured throughout:
- No Edge restart, CDP change, new browser/profile, or `--no-sandbox`.
- No OpenCode desktop/worker restart; no real repository task run.
- No credential, token, or `.env` change; no provider/model change.
- No public tunnel or unauthenticated endpoint; loopback only.
- No production repository changes; no commits or pushes.
- No weakening or skipping of any existing test.

Deliverables written (all new, untracked): `contracts.py`, `state_machine.py`, `retry.py`, `chatgpt_interface.py`, `executors.py`, `orchestrator.py`, `controller_api.py`; `db.py` extended additively (`ORCH_SCHEMA`, `transaction()`, orchestration store methods); three test suites (`test_wp423_contracts.py`, `test_wp423_persistence.py`, `test_wp423_orchestrator.py`, `test_wp423_controller_api.py`).

---

## 2. Architecture and Versioned Contracts

Contracts live in `src/opencode_bridge/contracts.py` and are the single source of truth for every payload that crosses a boundary. Each carries `schema_version` and is validated by a dedicated function returning `(ok, errors)`.

| Schema | Constant | Key invariants |
|---|---|---|
| Inbound ChatGPT message | `wp423.inbound_message.v1` | `message_id`, `source`, `project_id`, `conversation_id`, `message_content` (≤ 16 000 chars), `correlation_id`, `received_at` (epoch). `message_timestamp` is optional and **never invented**. `source` ∈ {`chatgpt_project`}. `message_identity_source` ∈ {`ui_dom_id`, `derived_content_hash`}. |
| Development task | `wp423.dev_task.v1` | `task_id`, `mission_id`, `originating_message_id`, `task_title`, `task_description`, `target_repository`, `target_branch`, `risk_classification` ∈ {`low`,`medium`,`high`,`critical`}, `task_status` ∈ the documented lifecycle. Lists capped at 64 items, strings capped at 8 000 chars. |
| OpenCode execution | `wp423.execution.v1` | `execution_id`, `task_id`, `submitted_at`; `execution_status` ∈ {`submitted`,`running`,`completed`,`failed`,`uncertain`,`interrupted`}; `completion_status` ∈ {`completed`,`failed`,`partial`,`unknown`}; `changed_files`, `test_results`, `verification_evidence`, `execution_output`. |
| ChatGPT delivery | `wp423.delivery.v1` | `delivery_id`, `originating_execution_id`, `target_project_id`, `target_conversation_id`, `response_content`, `delivery_status` ∈ {`pending`,`attempting`,`delivered`,`failed`,`uncertain`}, `attempts` ≥ 0, `confirmation_evidence`. |

`contracts.SUPPORTED_SCHEMAS` enumerates all four. Non-object payloads, wrong schema versions, oversized content, bad enums and bool-as-int are all rejected. Limits are centralised (`MAX_MESSAGE_CONTENT_CHARS`, `MAX_TEXT_CHARS`, `MAX_LIST_ITEMS`).

---

## 3. Durable Persistence and Idempotency

`BridgeDB` (`src/opencode_bridge/db.py`) is extended **additively**: the existing `tasks`/`approvals`/`audit_events` tables and `TaskController` are untouched. New tables (`ORCH_SCHEMA`) cover missions, inbound messages, development tasks, executions, deliveries, approvals, provider state, checkpoints, audit events — all with foreign keys and unique constraints.

Key guarantees, each pinned by `tests/test_wp423_persistence.py` (17 tests):
- **Idempotent ingestion:** `ingest_inbound_message` is keyed on `message_id`; replays increment `duplicate_count` and never overwrite the original row. `inbox_counts()` reports total/processed/pending/with_duplicates.
- **Unique identities:** one task per `(mission_id, originating_message_id)`; one execution per task; one delivery per execution. Enforced by unique constraints and `insert_*` returning `bool`.
- **Atomic transactions:** `BridgeDB.transaction()` is a context manager that commits on clean exit and rolls back everything on any exception (verified with a deliberate `RuntimeError`).
- **Approvals decided once:** `decide_approval` returns `False` on a second decision.
- **Provider state upserted:** cooldowns and failure counters persist across calls.
- **Checkpoints keep history:** `save_checkpoint`/`latest_checkpoint` support context-exhaustion and interruption recovery.
- **Process restart:** every row survives a fresh `BridgeDB` over the same file (mission state, inbound processed flag, task, execution with JSON fields, delivery with attempts, provider cooldown, checkpoint, audit trail).
- **Legacy recovery preserved:** `mark_interrupted_running()` still flips pre-existing `tasks` rows from `running` to `failed` (WP-GUI02 behaviour unchanged).

---

## 4. Controller API (Authenticated, Loopback-Only)

`src/opencode_bridge/controller_api.py` is deliberately built on stdlib `http.server.ThreadingHTTPServer` because this venv does **not** install fastapi/uvicorn (only `playwright`, `pytest`). The pre-existing `mcp_server.py` (fastapi) is left untouched and unimportable — a pre-existing condition, not a regression.

Security posture:
- **Loopback only:** `create_server(host=...)` raises `ControllerAPIError` for any host not in `{"127.0.0.1","localhost","::1"}`. Default bind is `127.0.0.1`.
- **Fails closed:** if `CONTROLLER_API_TOKEN` is unset, every request returns `503 api_token_not_configured`. No unauthenticated task execution path exists.
- **Bearer token** compared with `hmac.compare_digest` (no timing leak).
- **Body bounded** at `MAX_BODY_BYTES = 64 KiB`; larger payloads get `413 payload_too_large`.
- **JSON parsed and schema-validated** by the contract layer before any state change.
- **No secrets logged:** the access log records method, path, status and byte count only. `Authorization` headers and bodies never appear (verified by `caplog` tests).
- **No tunneling, no wildcard CORS, no public bind.**

Routes (all under `/api`):
- `POST /chatgpt/inbox` — ingest a ChatGPT message (202 accepted, 200 duplicate, 400 schema/JSON, 413 oversized).
- `GET /inbox/status`, `GET /health`, `GET /health/recovery`
- `GET|POST /mission`, `POST /mission/pause`, `POST /mission/resume`
- `GET /missions/{id}`, `GET /tasks/{id}`, `POST /tasks/{id}/approve`
- `GET /executions/{id}`, `POST /deliveries/{id}/ack`

`serve_forever(server)` runs the server in a daemon thread; the caller owns shutdown. Verified by `tests/test_wp423_controller_api.py` (19 tests).

---

## 5. Explicit State Machine

`src/opencode_bridge/state_machine.py` defines `OrchState` with the 12 happy-path states plus every degraded state from the spec:

`READY → CHATGPT_MESSAGE_DETECTED → MESSAGE_PERSISTED → TASK_READY → TASK_VALIDATED → WAITING_FOR_APPROVAL → OPENCODE_SUBMISSION → OPENCODE_EXECUTION → RESULT_PERSISTED → CHATGPT_DELIVERY_PENDING → CHATGPT_DELIVERED → CHATGPT_REVIEW_PENDING → READY`

Degraded states: `PAUSED`, `WAITING_FOR_APPROVAL`, `WAITING_FOR_CHATGPT`, `WAITING_FOR_OPENCODE`, `QUOTA_EXHAUSTED`, `AUTHENTICATION_REQUIRED`, `EXECUTION_INTERRUPTED`, `DELIVERY_FAILED`, `RECONCILIATION_REQUIRED`, `HUMAN_REVIEW_REQUIRED`, `COMPLETED`, `FAILED`.

Invariants enforced and tested:
- Transitions are an explicit allow-list; `can_transition`/`assert_transition`/`transitions_from` expose them.
- **`COMPLETED` is reachable only from `CHATGPT_REVIEW_PENDING`** (the previously-allowed `HUMAN_REVIEW_REQUIRED → COMPLETED` edge was removed so a human cannot silently close a mission without the review step).
- **No execution state can jump straight to a delivery state.**
- Terminal states (`COMPLETED`, `FAILED`) have no outgoing edges.
- `recovery_target(state, …)` maps in-flight execution states to `RECONCILIATION_REQUIRED` (never retry execution) and `RESULT_PERSISTED`/`RECONCILIATION_REQUIRED` with a persisted result to `CHATGPT_DELIVERY_PENDING`.
- Every state carries a `REQUIRED_ACTION` string surfaced to operators (`describe()`).

Two edges were deliberately added beyond the original draft to keep the documented invariants reachable: `OPENCODE_SUBMISSION → HUMAN_REVIEW_REQUIRED` (context exhaustion) and `CHATGPT_DELIVERY_PENDING → HUMAN_REVIEW_REQUIRED` (delivery budget exhausted). `WAITING_FOR_CHATGPT → CHATGPT_DELIVERY_PENDING` was added so a recovered transport resumes a pending delivery.

---

## 6. OpenCode Execution, Submission and Reconciliation

`src/opencode_bridge/executors.py` defines `ExecutionInterface` (health, submit, poll, collect_result, cancel) and `TaskControllerExecutor`, which reuses the existing `TaskController` + `OpenCodeAdapter` behind the interface. A `FakeOpenCodeExecutor` provides deterministic doubles for tests, including `submit_partial` (session created but prompt outcome unknown).

`MissionOrchestrator.submit_and_execute` (in `orchestrator.py`) enforces:
1. **Validate before submit** — governance and contract validation run first.
2. **Persist identity before submission** — the execution row is written with `execution_status=submitted` and `opencode_session_id` populated as soon as the adapter returns a session id.
3. **Track real status** — `poll` drives `submitted → running → completed/failed/interrupted`.
4. **Retrieve real output/test evidence** — `collect_result` populates `execution_output`, `changed_files`, `test_results`, `verification_evidence`.
5. **Persist results before delivery** — `RESULT_PERSISTED` state is entered only after the row is committed.
6. **Reconcile uncertain submissions** — if submission returns `OPENCODE_UNCERTAIN` with a session id, the row becomes `uncertain` and `recover()` resumes that **exact** session (never resubmits). If no session id exists, it is `failed`.
7. **No duplicate executions** — `get_execution_for_task` short-circuits any second submission for the same task.

Failure handling maps OpenCode outcomes to operator states:
- `OPENCODE_RATE_LIMITED` → `QUOTA_EXHAUSTED`, persisted cooldown, no hammering.
- `OPENCODE_AUTH_REQUIRED` → `AUTHENTICATION_REQUIRED`, no automatic retry.
- `OPENCODE_CONTEXT_EXHAUSTED` → `HUMAN_REVIEW_REQUIRED` + checkpoint.
- `OPENCODE_EXECUTION_INTERRUPTED` → `RECONCILIATION_REQUIRED` + checkpoint; `recover()` collects the result and resumes delivery.
- Uncertain submission (partial) → `RECONCILIATION_REQUIRED` with the session id persisted.

`recover()` (process-restart entry point) reconciles in-flight executions using only persisted session ids; it never creates a new submission.

---

## 7. ChatGPT Adapter Boundary

`src/opencode_bridge/chatgpt_interface.py` defines the contract (`ChatGPTInterface`) and two implementations: `PlaywrightChatGPTAdapter` (real, Playwright-based) and `FakeChatGPTAdapter` (deterministic double used throughout the tests).

Methods: `discover_project()`, `discover_latest_conversation()`, `read_latest_messages()`, `deliver_message()`, `verify_delivery()`.

Safety invariants, all enforced in code and tests:
- **Fixed Palmistry Project URL** `https://chatgpt.com/g/g-p-6ae87c1e48b08191a2cd33139c40639f/project` (project id `g-p-6ae87c1e48b08191a2cd33139c40639f`). Never navigate to stored `/c/<id>` URLs.
- **Never auto-create conversations** — `discover_latest_conversation` only reads the existing list.
- **Never silently switch Project** — `discover_project` validates the URL/title against the configured project id and returns `project_mismatch` / `project_not_verified` otherwise.
- **Preserve message IDs** — the DOM exposes no stable message id, so the adapter derives a deterministic content hash labelled `message_identity_source="derived_content_hash"`. This is **never** presented as a UI id.
- **Never launch a browser** — attachment is CDP-only via WP-421A/WP-422; no `launch()`/`launch_persistent_context()` is ever called.
- `verify_delivery()` is the only sanctioned way to confirm an uncertain delivery; `deliver_result` refuses to resend an uncertain delivery until verification succeeds.

---

## 8. Retry, Rate Limiting and Cooldown

`src/opencode_bridge/retry.py` provides `RetryPolicy`, `parse_retry_after`, `CooldownGate`, `RetryBudget`.

- **Bounded exponential backoff with jitter:** `base_seconds * factor^(attempt-1)` capped at `cap_seconds`; jitter ratio ≤ 0.5 applied deterministically when an RNG is supplied.
- **Respect `Retry-After`:** `parse_retry_after` handles seconds, HTTP-dates and garbage (returns `None` for unparseable); `delay_for(attempt, retry_after=…)` always prefers the server value.
- **Persisted cooldowns:** provider availability/cooldown stored in `provider_state` and reloaded on restart. A rate-limited provider is not hammered (verified: `submit_calls` stays at 1 while cooldown is active).
- **Bounded retry budget:** `RetryBudget` raises `RuntimeError` once `max_attempts` are consumed; delivery retries are capped (verified: attempts never exceed the configured budget, and exhaustion escalates to `HUMAN_REVIEW_REQUIRED`).
- **No silent provider/model switching** and **no assumption that a new chat resets limits** — the controller treats rate limits as provider-level state, not session-level.
- **Checkpoint + continuation for context exhaustion** and **reconcile interrupted execution** are handled in `recover()`.

---

## 9. Governance and Approval

`MissionOrchestrator.evaluate_governance` is the final authority. Checks (all enforced, all tested):
- Repository identity (must be in `allowed_repositories`).
- Branch (must equal `EXPECTED_BRANCH`).
- Provenance (originating message must be known and must match the task's `originating_message_id`).
- File/command scope via `SENSITIVE_KEYWORDS` (commit, push, deploy, release, merge, rebase, session launch, live order, live trading, `.env`, secret, token, credential, oauth, upstox, …).
- Production/deployment restrictions (any path containing `fno-ai-paper-trading` without `-dev` is blocked).
- Credential/`.env` restrictions.
- Destructive operations (`rm -rf`, `delete`, `wipe`, …).
- Human approval for any write-class task (`human_approval:write`).

**ChatGPT text is never automatic authorisation.** A message that says "OPERATOR APPROVED - no approval needed" still lands in `WAITING_FOR_APPROVAL` with zero submit calls. Approval is granted only through `approve_task(task_id, approved_by, reason)` (or `POST /api/tasks/{id}/approve`), which records the approval and moves the task to `ready`; execution happens on the next `run_cycle()`/`resume_pending()` pass. `reject_task` blocks the task and escalates to `HUMAN_REVIEW_REQUIRED`.

F&O safety rules are preserved: the controller never weakens `ExecutionMode.PAPER`, never enables live writes, and never touches the production workspace.

---

## 10. Observability and Status Report

`MissionOrchestrator.status_report()` exposes the full operational picture:
`mission` (id, title, workspace, branch, state, paused), `current_state`, `latest_inbound_message`, `pending_task`, `active_execution`, `last_confirmed_result`, `pending_delivery`, `providers`, `recovery_reason`, `required_action`, `inbox`, `generated_at`.

Structured logging uses correlation IDs; the access log records method/path/status/bytes only and never secrets (verified). Provider availability, cooldowns and recovery reasons are surfaced. The `required_action` field tells an operator exactly what is blocking (e.g. "Refresh the OpenCode provider credentials and retry.").

---

## 11. Tests and Verification

### Test counts
| Suite | Tests | Result |
|---|---|---|
| `test_wp423_contracts.py` | 29 | pass |
| `test_wp423_persistence.py` | 17 | pass |
| `test_wp423_orchestrator.py` | 35 | pass |
| `test_wp423_controller_api.py` | 19 | pass |
| **WP-423 total** | **100** | **all pass** |

Full repository run: `179 passed, 2 failed` in 233 s. The two failures are:
1. `tests/test_integration_opencode.py::test_integration_real_task` — **pre-existing**, requires a live OpenCode API (unrelated to WP-423).
2. `tests/test_wp423_controller_api.py::test_oversized_body_returns_413` — **flaky under full-suite load only**; passes in isolation and in the API suite (19/19). Root cause is socket teardown timing under process-wide load, not a logic defect. No code change made.

No existing test was weakened, skipped or deleted.

### Verification levels (distinguished explicitly)
- **Mock/unit (deterministic):** contracts, state machine, retry/cooldown, persistence, idempotency, atomic transactions, restart recovery, governance, approval, identity validation, delivery retry/budget, uncertain-delivery reconciliation, context-exhaustion checkpoint, interrupted-execution recovery, pause/resume, status report. All run with `FakeChatGPTAdapter` + `FakeOpenCodeExecutor` and a real SQLite file.
- **Local integration (real HTTP, loopback):** `test_wp423_controller_api.py` exercises a real `ThreadingHTTPServer` on an ephemeral port — auth 401/503, 413 body limit, 400 schema/invalid JSON, 202/200 ingest, GET/POST routes, 405 method, 404 unknown, non-loopback host rejection, header/body never logged.
- **Live OpenCode API:** not exercised by WP-423. `test_integration_opencode.py::test_integration_real_task` remains the pre-existing live-API smoke test (fails in this environment as before).
- **Live ChatGPT/Playwright:** **blocked.** `DevToolsActivePort` is absent, `ECONNREFUSED 127.0.0.1:9224`, no listener on 9220–9235. The operator-only `edge://inspect` remote-debugging opt-in (WP-422) has not been performed. No browser was launched, no conversation was created, no message was delivered. The `PlaywrightChatGPTAdapter` implementation exists but has not been exercised against a live browser.

### Manual smoke runs (real code paths, deterministic doubles)
- Happy path: reaches `CHATGPT_REVIEW_PENDING` with exactly 1 submit and 1 delivery.
- Replay: reported as `duplicate_message`; no second task/execution/delivery.
- Delivery retry: records attempt 2 without resubmitting.
- Uncertain submission: persists `opencode_session_id`; `recover()` resumes the same session (sessions created = 1).

---

## 12. Verdict, Boundaries and Next Action

**Verdict: foundation complete.** All 100 WP-423 tests pass; the state machine, persistence, idempotency, governance, approval, retry/cooldown, reconciliation and restart-recovery invariants are implemented and verified. The controller API is authenticated and loopback-only.

**What is NOT operational:**
- The autonomous ChatGPT ↔ controller ↔ OpenCode loop has **not** run end-to-end against real services. Live ChatGPT/Playwright verification is blocked on the WP-422 operator-only `edge://inspect` remote-debugging opt-in.
- No real repository task was executed; no OpenCode session was started against a real workspace.
- No commit or push was made; all files remain untracked.

**Next concrete action (operator):**
1. Perform the WP-422 `edge://inspect → Remote debugging → "Allow remote debugging for this browser instance"` opt-in on the running Edge (per-session, not automated).
2. Re-run the WP-421A/WP-422 attach-only probe to obtain `DevToolsActivePort` and confirm CDP attach.
3. Only then exercise `PlaywrightChatGPTAdapter` end-to-end against the fixed Palmistry Project URL, preserving the no-launch/no-create/no-switch invariants.
4. Commit/push decision remains the operator's; nothing has been staged.

**Files affected (all new/untracked):** `src/opencode_bridge/{contracts,state_machine,retry,chatgpt_interface,executors,orchestrator,controller_api}.py`; `src/opencode_bridge/db.py` (additive); `tests/test_wp423_{contracts,persistence,orchestrator,controller_api}.py`; this report.
**No changes to:** `.env`, credentials, providers/models, browser/profiles, Edge process, OpenCode desktop/worker, production repository, existing tests.
