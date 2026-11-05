# WP-424 — Playwright ChatGPT Communication Adapter

**Date:** 2026-11-03
**Repository:** `C:\Vijay_GitHub\opencode-automation-controller` (`master`, no commits; all work untracked)
**Verdict:** Adapter implemented and verified at mock/integration level. **Live ChatGPT verification BLOCKED** on WP-422's operator-only `edge://inspect` remote-debugging opt-in (CDP unavailable: `ECONNREFUSED 127.0.0.1:9224`, no listener 9220-9235, `DevToolsActivePort` absent). The autonomous development loop is **not** operational and is not claimed to be.

---

## 1. Existing architecture reused

- `ChatGPTInterface` / `PlaywrightChatGPTAdapter` / `FakeChatGPTAdapter` (from WP-423) — the boundary the orchestrator depends on. No controller-architecture change was needed.
- `BrowserAdapter` / `MockBrowserAdapter` / `PlaywrightEdgeAdapter` (WP-419/WP-421) — browser automation primitives; the adapter delegates, never reimplements.
- `PlaywrightChatGPTController` (WP-419) — proven discovery/read logic reused via the optional `controller` injection.
- `edge_attach` / WP-422 CDP discovery — `PlaywrightEdgeAdapter.attach_existing()` is the only sanctioned browser entry point; the adapter consumes `browser.last_attach_info`.
- `BridgeDB` + `MissionOrchestrator` (WP-423) — persistent inbox, delivery queue, state machine, governance.
- Contracts (`contracts.py`) — `build_inbound_message`, `INBOUND_MESSAGE_SCHEMA`.

No existing functionality was recreated. `PlaywrightEdgeAdapter.start()` (the launch path) is never invoked by the adapter.

---

## 2. Adapter operations implemented

All five interface operations are implemented in `PlaywrightChatGPTAdapter`:

- `discover_project(project_url)` — health probe (disconnected/auth), then `browser.discover_project_conversations()`. Returns project id, url, count, conversation list. Blocks on disconnected/auth/no-conversations.
- `discover_latest_conversation(project_url, excluded_titles)` — delegates to `browser.select_latest_project_conversation()` (UI ordering, newest eligible first). Excludes `OpenCode Automation Testing` via `DEFAULT_EXCLUDED_TITLES`. Never returns without a verified conversation id. Never navigates to a stored `/c/<id>` URL.
- `read_latest_messages(project_url, excluded_titles, max_messages)` — uses the injected controller when available (WP-419 discovery+read), otherwise falls back to parsing `You said:` blocks from page text. Builds contract-shaped inbound messages via `build_inbound_message` with `message_identity_source="derived_content_hash"`. Distinguishes user blocks from assistant blocks (only `You said:` is ingested). Returns `task_text` via marker extraction.
- `deliver_message(conversation, content, dedupe_key)` — verifies project identity and conversation selection, checks auth/writeability, submits via composer, waits, verifies appearance. Returns `delivered`/`uncertain`/`failed` with evidence. Never blindly resubmits.
- `verify_delivery(attempt)` — delegates to `browser.verify_submitted()` with a content prefix; used by the orchestrator to reconcile uncertain deliveries.
- `cdp_status()` — reports whether the underlying browser is a borrowed CDP attachment (WP-422) without launching anything.

---

## 3. Files changed

- `src/opencode_bridge/chatgpt_interface.py` — added `cdp_status()`; tightened project-mismatch check (treats unparseable-but-non-empty URL as mismatch); added conversation-selection verification in `deliver_message` (only when a URL is present, so mocks are not falsely blocked).
- `src/opencode_bridge/controller_api.py` — `_read_body` now drains a bounded prefix of oversized bodies and sets `close_connection=True` before sending 413, fixing the under-load ConnectionResetError.
- `tests/test_wp424_chatgpt_adapter.py` — new, 39 focused tests.
- `reports/execution/wp424_playwright_chatgpt_adapter_2026-11-03.md` — this report.
- `C:\Users\user\Documents\Default Project\.opencode\memory.md` — handoff appended.

No changes to `.env`, credentials, providers/models, browser/profiles, Edge, OpenCode, production repository, or existing tests.

---

## 4. Incoming and outgoing message contracts

**Incoming** (built by `build_inbound_message`): `schema_version=wp423.inbound_message.v1`, `message_id` (derived content hash unless a real UI id is exposed), `source="chatgpt"`, `project_id`, `conversation_id`, `message_timestamp` (optional, never invented), `message_content`, `correlation_id`, `received_at`, `message_identity_source` ∈ {`ui`, `derived_content_hash`}. Persisted by the orchestrator via `BridgeDB.ingest_inbound_message` before acknowledgement. Duplicate messages increment `duplicate_count` and are never reprocessed.

**Outgoing** (built by `MissionOrchestrator.build_delivery_content` and persisted as `contracts.delivery` v1): `delivery_id`, `originating_execution_id`, `target_project_id`, `target_conversation_id`, `response_content`, `delivery_status`, `attempts`, `confirmation_evidence`. The adapter receives the persisted `response_content` and returns delivery evidence; the orchestrator updates the row.

---

## 5. Idempotency and recovery evidence

- `derive_message_id` is a deterministic SHA-256 of `(project_id, conversation_id, content)` → stable across re-reads → ingestion is idempotent.
- `BridgeDB.ingest_inbound_message` keyed on `message_id`; replays increment `duplicate_count`, never overwrite.
- `deliver_message` returns `uncertain` (not a silent retry) on submit failure/unverified appearance; the orchestrator maps this to `RECONCILIATION_REQUIRED` and calls `verify_delivery` before any resend.
- `verify_delivery` inspects conversation history (via `browser.verify_submitted`) for the original content prefix before retrying.
- Controller restart during ingestion/delivery: all state lives in SQLite; `MissionOrchestrator.recover()` reconciles in-flight executions and pending deliveries without new submissions (verified in WP-423 tests, 35 passing).
- No conversation creation, no stored `/c/<id>` navigation, no silent project switch (verified by tests: `test_adapter_does_not_create_conversations`, `test_deliver_message_never_navigates_to_c_url`, `test_discover_project_never_navigates_to_stored_c_url`).

---

## 6. Focused and regression test results

| Suite | Tests | Result |
|---|---|---|
| `test_wp424_chatgpt_adapter.py` (new) | 39 | pass |
| `test_wp423_contracts.py` | 29 | pass |
| `test_wp423_persistence.py` | 17 | pass |
| `test_wp423_orchestrator.py` | 35 | pass |
| `test_wp423_controller_api.py` | 19 | pass |
| `test_wp422_edge_cdp_config.py` | 16 | pass |
| `test_wp421a_cdp_attach.py` | 16 | pass |
| `test_wp421_project_discovery.py` | (existing) | pass |
| `test_playwright_bridge_mock.py` | (existing) | pass |
| `test_wp423_*` + `test_wp424_*` combined | 100 + 39 = 139 | pass |

Full repository run: `180 passed, 1 failed` — the single failure is `tests/test_integration_opencode.py::test_integration_real_task` (pre-existing, requires a live OpenCode API; unrelated to WP-424). The previously-flaky `test_oversized_body_returns_413` now passes in the full suite after the drain fix (see §7).

No existing test was weakened, skipped or deleted.

---

## 7. Oversized-body test investigation

**Symptom:** `test_oversized_body_returns_413` failed with `ConnectionResetError: [WinError 10054]` only under full-suite load (passed in isolation and in the API suite).

**Root cause:** server lifecycle / test isolation (timing), not a logic defect. The handler checked `Content-Length`, sent 413 and returned without reading the request body. The client (urllib) was still transmitting the ~64 KiB body when the server closed the socket, so the OS delivered a RST that arrived before (or instead of) the 413 response under load.

**Fix (no assertion weakened):** `ControllerAPI._read_body` now drains a bounded prefix (`min(length, MAX_BODY_BYTES + 4096)`) of the oversized body before sending 413, and sets `close_connection = True`. This lets the client's send complete so the 413 is delivered cleanly. Memory is still bounded (never more than ~4 KiB beyond the limit).

**Classification:** timing/server-lifecycle, not an assertion or logic defect. The unrelated live OpenCode API integration failure (`test_integration_real_task`) remains separately classified.

---

## 8. CDP availability

**Blocked.** `DevToolsActivePort` absent; `ECONNREFUSED 127.0.0.1:9224`; no listener on 9220-9235; Edge PID 2420 running without `--remote-debugging-port`. The operator-only `edge://inspect → Remote debugging → "Allow remote debugging for this browser instance"` opt-in (WP-422) has not been performed. `PlaywrightEdgeAdapter.attach_existing()` returns `cdp_connect_failed` and the adapter's `cdp_status()` reports `ok=False` with the exact reason. No fallback launch occurs.

---

## 9. Live browser verification evidence

**Not performed.** No browser was launched, no conversation was created, no message was sent, no development task was executed. The `PlaywrightChatGPTAdapter` is exercised only against `MockBrowserAdapter` and `FakeChatGPTAdapter` doubles. Mock tests do **not** prove live ChatGPT communication.

---

## 10. Remaining blockers

1. WP-422 operator-only `edge://inspect` remote-debugging opt-in (gating all live verification).
2. No real end-to-end cycle has been run against ChatGPT or OpenCode.
3. Commit/push decision remains the operator's (nothing staged).

---

## 11. Recommended next milestone

1. Operator performs the WP-422 `edge://inspect` opt-in and re-runs the WP-421A/WP-422 attach-only probe to confirm `DevToolsActivePort` + CDP attach.
2. Run a single harmless, uniquely-marked communication test through the fixed Palmistry Project URL (operator-authorized message only), verifying delivery and response via `verify_delivery`.
3. Only after a verified real cycle, consider enabling the controller loop; keep all approval/governance gates in place.
4. Commit/push decision remains the operator's.

**Files affected (new/modified, all untracked):** `src/opencode_bridge/chatgpt_interface.py`, `src/opencode_bridge/controller_api.py`, `tests/test_wp424_chatgpt_adapter.py`, this report, and the memory handoff. **No changes to** `.env`, credentials, providers/models, browser/profiles, Edge process, OpenCode, production repository, or existing tests.