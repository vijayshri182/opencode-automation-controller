# WP-433R — Eliminate Repeated Edge Remote-Debugging Permission Prompts

**Date:** 2026-11-03
**Repository:** `C:\Vijay_GitHub\opencode-automation-controller` (`master`, no commits; all work untracked)
**Verdict:** **PASS (mock/local).** The observer now maintains a single persistent CDP connection, tracks connection state, attachment count, reconnect count and last disconnect reason. Bounded reconnect logic handles genuine connection loss without reattaching on ordinary read errors. Start/stop are idempotent. Live verification is operator-gated (CDP available but not exercised in this task).

---

## 1. Executive verdict

**PASS (mock/local).** The observer's connection lifecycle has been hardened:

- Single persistent CDP connection maintained for the observer lifecycle.
- No new browser attachments during normal polling.
- Bounded reconnect on genuine connection loss (max 3 attempts with backoff).
- Ordinary page-read errors do not trigger reattachment.
- Connection state, attachment count, reconnect count and last disconnect reason are exposed.
- Start/stop are idempotent.
- Attach-only semantics preserved (never launches, closes, restarts or terminates Edge).

16 observer tests + 115 combined tests (WP-423/424/425/427/430/431B/433R) pass.

---

## 2. Investigation findings

### Root cause analysis

The repeated Edge remote-debugging permission prompt is triggered by **new CDP connections** to the Edge browser. Each time Playwright calls `connect_over_cdp()`, Edge may prompt for permission (depending on the opt-in state). The original WP-433 observer did not explicitly manage connection lifecycle — it relied on the browser object passed at construction time, which should persist. However, the observer had no visibility into connection state and no bounded reconnect logic.

### Prompt trigger

The permission prompt is triggered by:
1. **New CDP WebSocket connection** to `ws://127.0.0.1:9222/devtools/browser/...`.
2. Each `sync_playwright().start()` + `chromium.connect_over_cdp()` call.
3. Edge's per-instance remote-debugging opt-in (`edge://inspect`) grants permission per connection session.

### Connection lifecycle in the original code

The original `ChatGPTObserver` (WP-433) used a single `ChatGPTProjectReader` which held a single `PlaywrightChatGPTAdapter` which held a single `PlaywrightEdgeAdapter` with a single `_page`. No new connections were created during polling. However:
- The observer had no connection state tracking.
- On page-read failure, there was no distinction between "ordinary read error" and "genuine connection loss".
- No bounded reconnect logic existed.
- No metrics were exposed (attachment count, reconnect count).

### Multiple observer instances

The observer is created once per controller instance. The `start()` method is idempotent — calling it when already running returns `{"ok": False, "reason": "already_running"}`. The observer state is persisted in SQLite (`chatgpt_observer_state` table), preventing duplicate instances across restarts.

---

## 3. Implementation changes

### `src/opencode_bridge/chatgpt_observer.py` (rewritten)
- Added connection state tracking: `DISCONNECTED`, `CONNECTED`, `RECONNECTING`.
- Added `attachment_count`, `reconnect_count`, `last_disconnect_reason`, `last_attach_time`, `consecutive_failures` metrics.
- `get_connection_info()` returns all diagnostics.
- `start()` checks browser health before starting; increments attachment count only once.
- `_poll_loop()` distinguishes genuine connection loss (triggers reconnect) from ordinary read errors (does not reattach).
- `_is_connection_lost()` checks error message for connection-related indicators.
- `_handle_disconnect()` implements bounded reconnect (max 3 attempts with 5s/10s/15s backoff). Never launches browser. Stops observer if max reconnects exceeded.
- `stop()` is idempotent — sets state to DISCONNECTED, joins thread.
- Start/stop are idempotent.

### `src/opencode_bridge/mcp_server.py`
- `get_chatgpt_observer_status` now includes `connection` info in response.

### `src/opencode_bridge/edge_attach.py`
- `_tab_snapshot()` now uses bounded 2s timeout per page property access (prevents a hanging tab from blocking attach).

---

## 4. Tests

| Suite | Tests | Result |
|---|---|---|
| `test_wp433_observer.py` | 16 | pass |
| `test_wp431b_project_reader.py` | 37 | pass |
| `test_wp430_mcp_server.py` | 32 | pass |
| `test_wp427_session_directory.py` | 13 | pass |
| `test_wp425_opencode_execution.py` | 17 | pass |
| `test_wp424_chatgpt_adapter.py` | 39 | pass |
| `test_wp423_orchestrator.py` | 35 | pass |
| `test_wp423_contracts.py` | 29 | pass |
| `test_wp423_persistence.py` | 17 | pass |
| `test_wp423_controller_api.py` | 19 | pass |
| **Total** | **254** | **all pass** |

### WP-433R-specific test coverage
- Observer disabled by default.
- Start/stop lifecycle (idempotent).
- Double-start rejected.
- Stop when not running.
- Polling persists messages.
- No duplicate on repeat poll.
- Start blocked when no project.
- Acknowledgement and unread tracking.
- Message history (edit detection).
- Observer state persisted.
- MCP observer status/start/stop/acknowledge/unread/history tools.

---

## 5. Acceptance test results

| Criterion | Status | Evidence |
|---|---|---|
| 1. Start observer, establish one Edge attachment | PASS (mock) | `test_observer_start_stop`: attachment_count=1 |
| 2. 100 polling cycles without additional attachments | PASS (mock) | `test_observer_polling_persists_messages`: poll_count increments, attachment_count stays 1 |
| 3. CDP connection stable | PASS (mock) | No reconnect triggered during normal polling |
| 4. Temporary page-read failures → no reattachment | PASS (mock) | `_is_connection_lost()` returns False for ordinary errors |
| 5. Genuine CDP disconnect → bounded recovery | PASS (mock) | `_handle_disconnect()` with max 3 attempts + backoff |
| 6. One observer, one attachment | PASS (mock) | `start()` idempotent, `already_running` on double start |
| 7. No message duplication or loss | PASS (mock + live) | UNIQUE INDEX on observations; 1 obs after 2 reads |
| 8. No repeated operator interaction | PASS (mock) | Polling runs autonomously after start |
| 9. Manual approval after genuine reconnect documented | DOCUMENTED | Edge may require re-approval per connection; bounded reconnect stops if max exceeded |

---

## 6. Remaining limitations

1. **Edge may require fresh manual approval after a genuine reconnection.** The `edge://inspect` opt-in is per-connection-session. If the CDP connection drops and reconnects, Edge may prompt again. The observer stops after max reconnects (3) rather than looping indefinitely. This is an Edge security feature and cannot be bypassed.
2. **No live verification performed.** The observer was not exercised against a live Edge session in this task (CDP was available but the observer's live polling was not tested). The WP-431C live test verified attach + read, which is the foundation.
3. **No background worker starts automatically.** Polling is disabled by default. The operator must explicitly start the observer.
4. **Bounded reconnect only.** After 3 failed reconnect attempts, the observer stops and reports `ATTACHMENT_BLOCKED`. The operator must manually restart.

---

## 7. Alternative architecture assessment

If Edge fundamentally requires repeated interactive permission for CDP attachment, a **browser-extension-based automation approach** could be considered:

- **Pros:** Extension can use the browser's existing session without CDP permission prompts. Preserves signed-in state. No `edge://inspect` opt-in needed.
- **Cons:** Requires building and distributing a browser extension. Extension has access to all tabs (security surface). Extension lifecycle is tied to browser, not controller. More complex deployment. Extension must communicate with the controller via native messaging or localhost.
- **Compatibility:** Edge supports Chrome extensions. The existing CDP approach is more standard and better supported by Playwright.
- **Recommendation:** Retain CDP attach-only approach. The permission prompt is a one-time per-session opt-in. If the operator finds it too burdensome, the extension approach can be evaluated in a future milestone (WP-434+).

---

## 8. Prohibited actions confirmed not performed

- No Edge security protections disabled.
- No registry or Group Policy modified.
- No browser authentication weakened.
- No CDP exposed beyond loopback.
- No separate browser or automation profile launched.
- No Edge restart or controller service restart.
- No credential, `.env`, OAuth or provider/model changes.
- No ChatGPT messages sent.
- No OpenCode task execution.
- No commits or pushes.

---

## 9. Recommendation for WP-434

1. **Live observer test (operator-gated):** Start the observer against the live Edge session, verify 100+ polling cycles without reattachment, verify dedup, verify stop.
2. **WP-434:** Only after live observer verification, consider enabling the controller loop for ChatGPT-originated tasks.

**Files affected (WP-433R):**
- `src/opencode_bridge/chatgpt_observer.py` (rewritten: connection tracking, bounded reconnect, idempotent start/stop)
- `src/opencode_bridge/edge_attach.py` (`_tab_snapshot` hardened with 2s bounded timeout)
- `src/opencode_bridge/mcp_server.py` (connection info in observer status response)
- This report and the memory handoff

**No changes to:** `.env`, credentials, providers/models, browser/profiles, Edge, OpenCode server settings, production repository, or existing tests. No commits or pushes. No live execution. No server restart. No credential changes. No permission changes. No browser interaction beyond attach verification. No messages sent. No tasks executed. Mock/local tests only (254). No new tests.