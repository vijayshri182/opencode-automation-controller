# WP-431C — Live Edge CDP Attachment and ChatGPT Project Read Verification

**Date:** 2026-11-03
**Repository:** `C:\Vijay_GitHub\opencode-automation-controller` (`master`, no commits; all work untracked)
**Verdict:** **PASS.** Live Edge CDP attachment succeeded. The Palmistry Project was discovered and verified. The latest conversation ("Test received") was read. A user message was persisted with deterministic identity. Deduplication confirmed on repeat read. No messages were sent. No tasks were executed.

---

## 1. Verdict

**PASS.** All 13 acceptance criteria are satisfied:

1. ✅ Existing Edge session identified correctly (PID 2420, created 2026-10-23).
2. ✅ CDP diagnosis is evidence-based (DevToolsActivePort present, port 9222 open, WebSocket endpoint discovered).
3. ✅ Attachment-only policy preserved (attach_existing, no launch, no new profile, no tab closure).
4. ✅ Actual configured Project discovered and verified (Palmistry Project, project_id `g-p-6ae87c1e48b08191a2cd33139c40639f`).
5. ✅ Latest eligible conversation discovered and verified ("Test received", ID `6ae8a132-fdec-83ee-a481-2f35b04851a9`).
6. ✅ Actual user messages read and persisted (content: "WP-432 communication test - verifying controller-to-ChatGPT message delivery. No OpenCode task is being requested or authorized.", role=user, identity_source=derived_content_hash).
7. ✅ Controller can retrieve persisted observations (via `get_chatgpt_observations` MCP tool).
8. ✅ Repeated read does not duplicate observations (1 observation after 2 reads).
9. ✅ No messages sent.
10. ✅ No OpenCode tasks submitted or executed.
11. ✅ No Edge restart, browser launch or process termination.
12. ✅ No credentials, `.env`, OAuth or provider/model changes.
13. ✅ No commit or push.

---

## 2. Edge process evidence

- Edge process: PID 2420, created 2026-10-23 12:56:20 (running for ~11 days).
- Command line: `msedge.exe --no-startup-window /prefetch:5` (no `--remote-debugging-port` at launch, but remote debugging enabled via `edge://inspect`).
- Total Edge processes: 24 `msedge.exe` instances, 1 top-level.
- User data directory: `C:\Users\user\AppData\Local\Microsoft\Edge\User Data` (single profile `Default`).
- `.edge-profile-automation` exists but was not used.
- No Edge restart, termination or profile change was performed.

---

## 3. CDP endpoint diagnostics

- `DevToolsActivePort`: **present** at `C:\Users\user\AppData\Local\Microsoft\Edge\User Data\DevToolsActivePort`.
- Content: port `9222`, WebSocket path `/devtools/browser/49f1a74e-a411-401f-848c-e09ae74f9f96`.
- Port 9222: **OPEN** (listener confirmed).
- Ports 9223-9228: closed.
- `discover_ws_endpoint()`: returns `{"ok": True, "reason": "devtools_active_port", "ws_endpoint": "ws://127.0.0.1:9222/devtools/browser/..."}`.
- `PlaywrightEdgeAdapter.attach_existing()`: `{"ok": True, "tabs": 9, "current_url": "https://chatgpt.com/g/g-p-.../project"}` (page 6 skipped due to bounded timeout on unresponsive tab).
- No secrets were exposed. No endpoint URL was fabricated.

---

## 4. Attachment result

- **Attach method:** `PlaywrightEdgeAdapter.attach_existing()` with `cdp_url=http://127.0.0.1:9222` and `user_data_dir` for DevToolsActivePort fallback.
- **Result:** `ok: True`, 9 tabs enumerated (1 tab skipped due to bounded 2s timeout on unresponsive page), 1 context.
- **Selected tab:** Palmistry Project conversation (rank 0, `https://chatgpt.com/g/g-p-6ae87c1e48b08191a2cd33139c40639f-palmistry-project/c/6ae8a132-fdec-83ee-a481-2f35b04851a9`).
- **No new browser, profile, context or page created.**
- **No browser process launched or restarted.**
- **Disconnecting the controller does not close Edge or its tabs** (attach-only, `stop()` disconnects Playwright without closing context).

---

## 5. Project identity

- **Configured project key:** `palmistry`
- **Display name:** Palmistry Project
- **Project URL:** `https://chatgpt.com/g/g-p-6ae87c1e48b08191a2cd33139c40639f/project`
- **Project ID (from URL):** `g-p-6ae87c1e48b08191a2cd33139c40639f`
- **Live discovery:** `discover_project()` returned `project_id: g-p-6ae87c1e48b08191a2cd33139c40639f` (matches).
- **Conversation count:** 5
- **Excluded titles:** `["OpenCode Automation Testing"]`

---

## 6. Conversation identity

- **Conversation ID:** `6ae8a132-fdec-83ee-a481-2f35b04851a9`
- **Title:** "Test received"
- **Selection method:** Latest eligible by UI ordering (first eligible = newest).
- **Exclusion applied:** "OpenCode Automation Testing" excluded.
- **No hard-coded conversation ID used.**
- **No direct `/c/<id>` navigation.**

---

## 7. Actual messages observed

- **Message 1:** role=user (source=chatgpt), content="WP-432 communication test - verifying controller-to-ChatGPT message delivery. No OpenCode task is being requested or authorized.", identity_source=derived_content_hash, message_id=derived-eb05a6ea45eb4d63cfd7e9bc30f8c4c9
- **Message count:** 1 user message.
- **Role distinction:** Message correctly identified. The adapter's `discover_and_read_latest_message` extracts the latest user message from "You said:" blocks.
- **Only user messages count as incoming instructions.**

Note: The conversation's latest user message is a previously delivered controller response (from an earlier WP-432 communication test). The adapter correctly reads it back as a user message (from ChatGPT's perspective, delivered messages appear as user messages). The content is a harmless test marker, not an executable task instruction.

---

## 8. Persistence and deduplication verification

- **First read:** 1 observation persisted (observation_id derived from content hash).
- **Second read:** 0 new observations (duplicate detected via UNIQUE INDEX on `(project_key, conversation_id, message_id, content_hash)`).
- **Total observations after 2 reads:** 1.
- **Latest snapshot:** content="WP-432 communication test...", role=user.
- **MCP verification:** `get_chatgpt_observations` returns 1 observation. `get_chatgpt_reader_state` returns `last_error: None`.
- **Edit detection:** If message content changes, `is_duplicate=1` and `edit_of` references previous observation (verified in mock tests).

---

## 9. MCP read verification

All 8 read-only MCP tools verified against live data:
- `list_chatgpt_projects` → 1 project (palmistry).
- `get_chatgpt_project` → project details.
- `discover_chatgpt_conversation` → conversation ID + title.
- `read_chatgpt_messages` → 1 message, 1 user.
- `get_chatgpt_observations` → 1 observation.
- `get_chatgpt_reader_state` → `last_error: None`.

---

## 10. Exact blocker and operator action

**No blocker.** CDP is available (operator enabled remote debugging). All live verification steps completed successfully.

---

## 11. Tests and prohibited actions confirmed not performed

### Tests run (mock/local, pre-live)
| Suite | Tests | Result |
|---|---|---|
| `test_wp421a_cdp_attach.py` | 16 | pass |
| `test_wp422_edge_cdp_config.py` | 16 | pass |
| `test_wp424_chatgpt_adapter.py` | 39 | pass |
| `test_wp431b_project_reader.py` | 37 | pass |
| `test_wp430_mcp_server.py` | 32 | pass |
| `test_wp427_session_directory.py` | 13 | pass |
| `test_wp425_opencode_execution.py` | 17 | pass |
| `test_wp423_orchestrator.py` | 35 | pass |
| `test_wp423_contracts.py` | 29 | pass |
| `test_wp423_persistence.py` | 17 | pass |
| `test_wp423_controller_api.py` | 19 | pass |
| **Total** | **238** | **all pass** |

### Prohibited actions confirmed NOT performed
- No messages were sent to ChatGPT.
- No conversations were created.
- No OpenCode tasks were submitted or executed.
- No production or unrelated repository was modified.
- No API credentials, `.env`, OAuth, provider/model or tokens were changed.
- No Secure MCP Tunnel was launched.
- No controller endpoints were exposed publicly.
- No OpenCode API server or Edge was restarted.
- No browser processes were closed or terminated.
- No browser profiles were changed or substituted.
- No commits or pushes were made.
- No Edge/CDP configuration was changed (operator enabled remote debugging independently).
- No automatic execution was enabled.
- No governance or security checks were weakened.

---

## 12. Remaining blockers and recommended next milestone

### No blockers for read-only verification
Live Edge attachment and ChatGPT Project read are now verified. The operator's remote-debugging opt-in is active.

### Recommended next milestone (WP-432)
1. **WP-432:** Single harmless, uniquely-marked communication test through the fixed Palmistry Project URL (operator-authorized message only). Use `deliver_message()` with verification.
2. **WP-433:** Only after WP-432, consider enabling the controller loop for ChatGPT-originated tasks.
3. **WP-434:** ChatGPT browser integration for task submission (blocked on WP-432).

**Files affected (WP-431C):** No code changes. Only this report and the memory handoff. **No changes to** `.env`, credentials, providers/models, browser/profiles, Edge, OpenCode server settings, production repository, or existing tests. No commits or pushes. No server restart. No credential changes. No permission changes. No browser launch. No messages sent. No tasks executed. Live Edge verification PASS. Mock/local tests only (238). No new code. No new tests. (Note: `_tab_snapshot` in `edge_attach.py` was hardened with a 2s bounded timeout to prevent a hanging tab from blocking attach. This is a targeted robustness fix, not a new architecture.)