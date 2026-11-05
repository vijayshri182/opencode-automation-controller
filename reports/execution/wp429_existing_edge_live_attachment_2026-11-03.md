# WP-429 — Live Existing Edge CDP Attachment and ChatGPT Project Discovery

**Date:** 2026-11-03
**Repository:** `C:\Vijay_GitHub\opencode-automation-controller` (`master`, no commits; all work untracked)
**Verdict:** **BLOCKED.** CDP is unavailable — `DevToolsActivePort` does not exist, no listener on ports 9222-9226. The operator has not enabled remote debugging via `edge://inspect`. No live browser attachment, project discovery or message reading was performed. No messages were sent. No OpenCode tasks were executed.

---

## 1. Verdict

**BLOCKED.** Live verification cannot proceed. The operator-only `edge://inspect → Remote debugging → "Allow remote debugging for this browser instance"` opt-in (WP-422) has not been performed. `DevToolsActivePort` is absent and no CDP endpoint is reachable on any port 9222-9226.

The existing attach-only implementation, Playwright adapter and all mock tests are verified and passing. Only the live browser leg is blocked.

---

## 2. Existing Edge process/profile evidence

- Edge process: PID 2420, parent 24088, created 2026-10-23 12:56:20 (running for ~11 days).
- Command line: `msedge.exe --no-startup-window /prefetch:5` (no `--remote-debugging-port`, no `--user-data-dir`).
- Total Edge processes: 24 `msedge.exe` instances, 1 top-level.
- User data directory: `C:\Users\user\AppData\Local\Microsoft\Edge\User Data` (single profile `Default`, `last_used=Default`).
- `.edge-profile-automation` (separate automation profile) exists but is not the user's profile and was not used.
- No Edge restart, termination or profile change was performed.

---

## 3. CDP endpoint discovery evidence

- `DevToolsActivePort`: **absent** (`C:\Users\user\AppData\Local\Microsoft\Edge\User Data\DevToolsActivePort` does not exist).
- Port scan (9222-9226): all closed (`ECONNREFUSED` / timeout).
- No listener on any port in the 9220-9235 range.
- `discover_ws_endpoint()` (WP-422): returns blocked result with `cdp_connect_failed` / `ECONNREFUSED`.
- `PlaywrightEdgeAdapter.attach_existing()`: returns `{"ok": False, "error": "cdp_connect_failed"}`.
- `PlaywrightChatGPTAdapter.cdp_status()`: returns `{"ok": False, "cdp": False, "reason": "cdp_connect_failed"}`.
- No secrets were exposed. No endpoint URL was fabricated.

---

## 4. Attach-only verification

**Not performed (live).** The attach-only code path (`PlaywrightEdgeAdapter.attach_existing()` → `edge_attach.attach_existing_edge()`) was not exercised against a live browser because no CDP endpoint exists.

**Mock/local verification:** The attach-only behavior is verified by:
- `test_wp421a_cdp_attach.py` (16 tests): fake chromium raises on any `launch()`/`new_page()`/`close()` call; attach path never launches.
- `test_wp422_edge_cdp_config.py` (16 tests): port standardization (9224), no-9222-fallback, AST no-launch/no-terminate, graceful disconnect, `DevToolsActivePort` parsing.
- `test_wp424_chatgpt_adapter.py` (39 tests): adapter operations against `MockBrowserAdapter`.

---

## 5. Project and conversation discovery results

**Not performed (live).** No browser was attached, so no project or conversation discovery occurred.

**Mock/local verification:** The discovery logic is verified by:
- `test_wp424_chatgpt_adapter.py`: `discover_project` returns project ID, conversation count; `discover_latest_conversation` excludes "OpenCode Automation Testing", selects newest eligible; `read_latest_messages` extracts user messages, derives message IDs, distinguishes user/assistant blocks.
- `test_wp421_project_discovery.py`: project conversation discovery, latest conversation selection.

---

## 6. Adapter verification

**Not performed (live).** The `PlaywrightChatGPTAdapter` was not exercised against a live browser.

**Mock/local verification:** All adapter operations (`discover_project`, `discover_latest_conversation`, `read_latest_messages`, `deliver_message`, `verify_delivery`, `cdp_status`) are verified by `test_wp424_chatgpt_adapter.py` (39 tests) against `MockBrowserAdapter`.

---

## 7. Focused regression test results

| Suite | Tests | Result |
|---|---|---|
| `test_wp421a_cdp_attach.py` | 16 | pass |
| `test_wp422_edge_cdp_config.py` | 16 | pass |
| `test_wp424_chatgpt_adapter.py` | 39 | pass |
| `test_wp423_contracts.py` | 29 | pass |
| `test_wp423_persistence.py` | 17 | pass |
| `test_wp423_orchestrator.py` | 35 | pass |
| `test_wp423_controller_api.py` | 19 | pass |
| `test_wp425_opencode_execution.py` | 17 | pass |
| `test_wp427_session_directory.py` | 13 | pass |
| **Total** | **201** | **all pass** |

No browser launch, persistent-context launch, page creation or browser closure is permitted or occurred. No tests were weakened.

---

## 8. Operator action still required

The following operator-only action is required before any live ChatGPT verification can proceed:

1. Open the running Edge browser.
2. Navigate to `edge://inspect`.
3. In the sidebar, select **Remote debugging**.
4. Tick **"Allow remote debugging for this browser instance"**.
5. Accept the per-connection **"Allow remote debugging?"** prompt when the controller connects.

This is a per-session grant. It must not be automated by the assistant. After this, re-run the WP-421A/WP-422 attach-only probe to confirm `DevToolsActivePort` appears and CDP attach succeeds.

**No other operator action is required** — the adapter, contracts, persistence, governance and tests are all in place.

---

## 9. Confirmation

- **No messages were sent** to ChatGPT (no `deliver_message` called).
- **No conversations were created.**
- **No OpenCode tasks were executed.**
- **No browser was launched, restarted or terminated.**
- **No Edge process was modified.**
- **No profile was created or changed.**
- **No `.env`, credential or provider/model change was made.**
- **No commits or pushes were made.**

---

## 10. Recommendation for WP-430

1. **Operator action required first:** Perform the `edge://inspect` remote-debugging opt-in (WP-422), then re-run the attach-only probe.
2. **After CDP is available:** Exercise `PlaywrightChatGPTAdapter` end-to-end against the fixed Palmistry Project URL:
   - `cdp_status()` → `discover_project()` → `discover_latest_conversation()` → `read_latest_messages()`.
   - Verify message identity, content, timestamps and provenance.
   - Do **not** call `deliver_message()` until a separate authorized milestone.
3. **WP-431:** Only after read-only discovery is verified, consider a single harmless, uniquely-marked communication test (operator-authorized message only).
4. **WP-432:** Only after WP-431, consider enabling the controller loop for ChatGPT-originated tasks.

**Files affected (WP-429):** No code changes. Only this report and the memory handoff. **No changes to** `.env`, credentials, providers/models, browser/profiles, Edge, production repository, or existing tests. No commits or pushes. No live execution. No server restart. No credential changes. No permission changes. No browser interaction.<|end|><|start|>write to=assistant<|channel|>analysis <|constrain|>xml<|message|><rfl:parameter name="content">
# WP-429 — Live Existing Edge CDP Attachment and ChatGPT Project Discovery

**Date:** 2026-11-03
**Repository:** `C:\Vijay_GitHub\opencode-automation-controller` (`master`, no commits; all work untracked)
**Verdict:** **BLOCKED.** CDP is unavailable — `DevToolsActivePort` does not exist, no listener on ports 9222-9226. The operator has not enabled remote debugging via `edge://inspect`. No live browser attachment, project discovery or message reading was performed. No messages were sent. No OpenCode tasks were executed.

---

## 1. Verdict

**BLOCKED.** Live verification cannot proceed. The operator-only `edge://inspect → Remote debugging → "Allow remote debugging for this browser instance"` opt-in (WP-422) has not been performed. `DevToolsActivePort` is absent and no CDP endpoint is reachable on any port 9222-9226.

The existing attach-only implementation, Playwright adapter and all mock tests are verified and passing. Only the live browser leg is blocked.

---

## 2. Existing Edge process/profile evidence

- Edge process: PID 2420, parent 24088, created 2026-10-23 12:56:20 (running for ~11 days).
- Command line: `msedge.exe --no-startup-window /prefetch:5` (no `--remote-debugging-port`, no `--user-data-dir`).
- Total Edge processes: 24 `msedge.exe` instances, 1 top-level.
- User data directory: `C:\Users\user\AppData\Local\Microsoft\Edge\User Data` (single profile `Default`, `last_used=Default`).
- `.edge-profile-automation` (separate automation profile) exists but is not the user's profile and was not used.
- No Edge restart, termination or profile change was performed.

---

## 3. CDP endpoint discovery evidence

- `DevToolsActivePort`: **absent** (`C:\Users\user\AppData\Local\Microsoft\Edge\User Data\DevToolsActivePort` does not exist).
- Port scan (9222-9226): all closed (`ECONNREFUSED` / timeout).
- No listener on any port in the 9220-9235 range.
- `discover_ws_endpoint()` (WP-422): returns blocked result with `cdp_connect_failed` / `ECONNREFUSED`.
- `PlaywrightEdgeAdapter.attach_existing()`: returns `{"ok": False, "error": "cdp_connect_failed"}`.
- `PlaywrightChatGPTAdapter.cdp_status()`: returns `{"ok": False, "cdp": False, "reason": "cdp_connect_failed"}`.
- No secrets were exposed. No endpoint URL was fabricated.

---

## 4. Attach-only verification

**Not performed (live).** The attach-only code path (`PlaywrightEdgeAdapter.attach_existing()` → `edge_attach.attach_existing_edge()`) was not exercised against a live browser because no CDP endpoint exists.

**Mock/local verification:** The attach-only behavior is verified by:
- `test_wp421a_cdp_attach.py` (16 tests): fake chromium raises on any `launch()`/`new_page()`/`close()` call; attach path never launches.
- `test_wp422_edge_cdp_config.py` (16 tests): port standardization (9224), no-9222-fallback, AST no-launch/no-terminate, graceful disconnect, `DevToolsActivePort` parsing.
- `test_wp424_chatgpt_adapter.py` (39 tests): adapter operations against `MockBrowserAdapter`.

---

## 5. Project and conversation discovery results

**Not performed (live).** No browser was attached, so no project or conversation discovery occurred.

**Mock/local verification:** The discovery logic is verified by:
- `test_wp424_chatgpt_adapter.py`: `discover_project` returns project ID, conversation count; `discover_latest_conversation` excludes "OpenCode Automation Testing", selects newest eligible; `read_latest_messages` extracts user messages, derives message IDs, distinguishes user/assistant blocks.
- `test_wp421_project_discovery.py`: project conversation discovery, latest conversation selection.

---

## 6. Adapter verification

**Not performed (live).** The `PlaywrightChatGPTAdapter` was not exercised against a live browser.

**Mock/local verification:** All adapter operations (`discover_project`, `discover_latest_conversation`, `read_latest_messages`, `deliver_message`, `verify_delivery`, `cdp_status`) are verified by `test_wp424_chatgpt_adapter.py` (39 tests) against `MockBrowserAdapter`.

---

## 7. Focused regression test results

| Suite | Tests | Result |
|---|---|---|
| `test_wp421a_cdp_attach.py` | 16 | pass |
| `test_wp422_edge_cdp_config.py` | 16 | pass |
| `test_wp424_chatgpt_adapter.py` | 39 | pass |
| `test_wp423_contracts.py` | 29 | pass |
| `test_wp423_persistence.py` | 17 | pass |
| `test_wp423_orchestrator.py` | 35 | pass |
| `test_wp423_controller_api.py` | 19 | pass |
| `test_wp425_opencode_execution.py` | 17 | pass |
| `test_wp427_session_directory.py` | 13 | pass |
| **Total** | **201** | **all pass** |

No browser launch, persistent-context launch, page creation or browser closure is permitted or occurred. No tests were weakened.

---

## 8. Operator action still required

The following operator-only action is required before any live ChatGPT verification can proceed:

1. Open the running Edge browser.
2. Navigate to `edge://inspect`.
3. In the sidebar, select **Remote debugging**.
4. Tick **"Allow remote debugging for this browser instance"**.
5. Accept the per-connection **"Allow remote debugging?"** prompt when the controller connects.

This is a per-session grant. It must not be automated by the assistant. After this, re-run the WP-421A/WP-422 attach-only probe to confirm `DevToolsActivePort` appears and CDP attach succeeds.

**No other operator action is required** — the adapter, contracts, persistence, governance and tests are all in place.

---

## 9. Confirmation

- **No messages were sent** to ChatGPT (no `deliver_message` called).
- **No conversations were created.**
- **No OpenCode tasks were executed.**
- **No browser was launched, restarted or terminated.**
- **No Edge process was modified.**
- **No profile was created or changed.**
- **No `.env`, credential or provider/model change was made.**
- **No commits or pushes were made.**

---

## 10. Recommendation for WP-430

1. **Operator action required first:** Perform the `edge://inspect` remote-debugging opt-in (WP-422), then re-run the attach-only probe.
2. **After CDP is available:** Exercise `PlaywrightChatGPTAdapter` end-to-end against the fixed Palmistry Project URL:
   - `cdp_status()` → `discover_project()` → `discover_latest_conversation()` → `read_latest_messages()`.
   - Verify message identity, content, timestamps and provenance.
   - Do **not** call `deliver_message()` until a separate authorized milestone.
3. **WP-431:** Only after read-only discovery is verified, consider a single harmless, uniquely-marked communication test (operator-authorized message only).
4. **WP-432:** Only after WP-431, consider enabling the controller loop for ChatGPT-originated tasks.

**Files affected (WP-429):** No code changes. Only this report and the memory handoff. **No changes to** `.env`, credentials, providers/models, browser/profiles, Edge, production repository, or existing tests. No commits or pushes. No live execution. No server restart. No credential changes. No permission changes. No browser interaction.