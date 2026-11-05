# WP-431B — Configurable ChatGPT Project Selection and Read-Only Conversation Reader

**Date:** 2026-11-03
**Repository:** `C:\Vijay_GitHub\opencode-automation-controller` (`master`, no commits; all work untracked)
**Verdict:** **PASS (mock/local integration).** Live Edge verification **BLOCKED** — CDP unavailable (DevToolsActivePort absent, no listener on 9222-9226). No live browser attachment, project discovery or message reading was performed. No messages were sent. No tasks were executed.

---

## 1. Executive verdict

**PASS (mock/local).** The configurable ChatGPT Project registry, read-only conversation reader, observation persistence and controller/MCP integration are implemented and verified through 37 focused tests + 201 regression tests = 238 total, all passing. Live Edge verification is **BLOCKED** — the operator has not enabled remote debugging via `edge://inspect`.

---

## 2. Architecture and files changed

### New module: `src/opencode_bridge/chatgpt_project_reader.py`
- `ChatGPTProjectRegistry` — manages configured ChatGPT Projects in SQLite. Tables: `chatgpt_projects`, `chatgpt_project_state`, `chatgpt_observations`. Supports registration, listing, get, active project selection, polling toggle, read state tracking, observation persistence with deduplication and edit detection.
- `ChatGPTProjectReader` — read-only reader wrapping `PlaywrightChatGPTAdapter`. Discovers conversations, reads messages, persists observations. Never sends messages or creates conversations.
- Validation functions: `validate_project_key`, `validate_project_url`, `derive_project_id`.

### Modified: `src/opencode_bridge/mcp_server.py`
- Added 8 read-only MCP tools: `list_chatgpt_projects`, `get_chatgpt_project`, `set_active_chatgpt_project`, `discover_chatgpt_conversation`, `read_chatgpt_messages`, `get_chatgpt_observations`, `get_chatgpt_reader_state`.
- `MCPServer.__init__` accepts optional `project_registry` and `project_reader`.

### Modified: `src/opencode_bridge/chatgpt_interface.py` (no changes needed — reused as-is)

### New tests: `tests/test_wp431b_project_reader.py` (37 tests)

---

## 3. Configuration example and operator instructions

### Register a project
```python
from opencode_bridge.chatgpt_project_reader import ChatGPTProjectRegistry
from opencode_bridge.db import BridgeDB

db = BridgeDB(path)
registry = ChatGPTProjectRegistry(db)

# Palmistry is auto-registered as default on init
# Register additional projects:
registry.register_project(
    project_key="my-project",
    display_name="My ChatGPT Project",
    project_url="https://chatgpt.com/g/g-p-abc123def456/project",
    enabled=True,
    read_only=True,
    polling_interval_seconds=0,  # disabled by default
    excluded_titles=["OpenCode Automation Testing"],
)
```

### Select active project
```python
registry.set_active_project("my-project")
```

### Read messages (read-only)
```python
from opencode_bridge.chatgpt_interface import PlaywrightChatGPTAdapter
from opencode_bridge.browser_automation import MockBrowserAdapter

adapter = PlaywrightChatGPTAdapter(browser)
reader = ChatGPTProjectReader(adapter, registry, "my-project")
result = reader.read_messages(max_messages=10)
# result contains: project_key, conversation_id, conversation_title, messages, user_message_count
```

### Polling (disabled by default)
```python
registry.set_polling_enabled(True)  # explicit opt-in
# Polling interval configured per-project (polling_interval_seconds)
# Default: 0 (disabled)
```

### Validation rules
- Project key: alphanumeric, hyphens, underscores, dots; max 64 chars.
- Project URL: must start with `https://chatgpt.com/g/g-p-` and contain `/project`.
- Project ID: derived from URL (e.g., `g-p-6ae87c1e48b08191a2cd33139c40639f`).
- Fail closed for malformed or unsupported configuration.

---

## 4. Project selection behaviour

- Multiple named ChatGPT Projects can be registered in the SQLite database.
- One active Project is selected by a stable project key (`set_active_project`).
- Project switching is explicit and auditable (updates `chatgpt_project_state` table with timestamp).
- If the configured Project cannot be found, operations fail closed with `project not registered` error.
- Disabled projects cannot be set as active.
- Palmistry Project is auto-registered as the default on first init (preserving existing configuration).
- No silent Project switching — the reader verifies `project_id` matches between registered config and live UI.

---

## 5. Conversation discovery and selection evidence

- Discovery uses `PlaywrightChatGPTAdapter.discover_latest_conversation()` (existing WP-424 implementation).
- Conversations are discovered from the visible Project conversation list (not stored `/c/<id>` URLs).
- Latest eligible conversation selected by UI ordering (first eligible = newest).
- Exclusion rules are configurable per project (default: `["OpenCode Automation Testing"]`).
- If selection is ambiguous (no eligible conversations), returns explicit error with `reason: no_eligible`.
- Project identity verified: `result["project_id"]` must match registered `project_id`.

---

## 6. Message identity and persistence design

- **Message ID:** Uses `derive_message_id()` (deterministic SHA-256 hash of project_id + conversation_id + content). Labelled `derived_content_hash` — never presented as a UI ID.
- **Role distinction:** User messages (`role="user"`) vs assistant messages (`role="assistant"`). Only user messages count as incoming instructions.
- **Observation persistence:** Each observed message stored in `chatgpt_observations` table with:
  - `observation_id` (deterministic hash)
  - `project_key`, `conversation_id`, `conversation_title`
  - `message_id`, `role`, `content`, `content_hash`
  - `visible_timestamp`, `observed_at`
  - `is_duplicate` (1 if same message_id seen before)
  - `edit_of` (reference to previous observation if content changed)
- **Deduplication:** `UNIQUE INDEX` on `(project_key, conversation_id, message_id, content_hash)`. Duplicate observations return `duplicate: True` without inserting.
- **Edit detection:** If the same `message_id` is observed with different content, `is_duplicate=1` and `edit_of` references the previous observation. Previous content is retained.
- **No overwrite:** Previous observations are never deleted or overwritten.

---

## 7. Controller read operations

New MCP tools (all read-only):
- `list_chatgpt_projects` — list all configured Projects.
- `get_chatgpt_project` — get Project details by key.
- `set_active_chatgpt_project` — explicitly set active Project (auditable).
- `discover_chatgpt_conversation` — discover latest eligible conversation (read-only).
- `read_chatgpt_messages` — read and persist messages from latest conversation (read-only, no message sending).
- `get_chatgpt_observations` — retrieve persisted observations with optional filters (project_key, conversation_id, role, limit).
- `get_chatgpt_reader_state` — get reader state (last read, errors, polling status, active project).

All follow existing MCP conventions: JSON-RPC 2.0, loopback-only, bearer token auth, body bounded.

---

## 8. Polling and recovery behaviour

- **Disabled by default:** `polling_enabled=0` in `chatgpt_project_state`. `polling_interval_seconds=0` per project.
- **Explicit opt-in:** `registry.set_polling_enabled(True)` required.
- **Recovery:** All state persisted in SQLite. After restart, `get_state()` returns `last_read_at`, `last_error`, `active_project_key`. No data loss.
- **No background worker:** No polling thread starts automatically. Polling is a future milestone (WP-432+).
- **Bounded retries:** Configured per-project via `polling_interval_seconds`. Not implemented as automatic retry yet.
- **Fail-closed:** If browser attachment or Project identity verification fails, the reader returns an explicit error and updates `last_error` in state.

---

## 9. Tests run and results

| Suite | Tests | Result |
|---|---|---|
| `test_wp431b_project_reader.py` (new) | 37 | pass |
| `test_wp430_mcp_server.py` | 32 | pass |
| `test_wp427_session_directory.py` | 13 | pass |
| `test_wp425_opencode_execution.py` | 17 | pass |
| `test_wp424_chatgpt_adapter.py` | 39 | pass |
| `test_wp423_orchestrator.py` | 35 | pass |
| `test_wp423_contracts.py` | 29 | pass |
| `test_wp423_persistence.py` | 17 | pass |
| `test_wp423_controller_api.py` | 19 | pass |
| **Total** | **238** | **all pass** |

No existing tests were weakened. No assertions were skipped.

---

## 10. Actual live Edge attachment result

**BLOCKED.** CDP unavailable.

- `DevToolsActivePort`: absent (`C:\Users\user\AppData\Local\Microsoft\Edge\User Data\DevToolsActivePort` does not exist).
- Port scan (9222-9226): all closed.
- No listener on any port in 9220-9235 range.
- `discover_ws_endpoint()` returns blocked result with `cdp_connect_failed`.
- `PlaywrightEdgeAdapter.attach_existing()` returns `{"ok": False, "error": "cdp_connect_failed"}`.

**Operator action required:**
1. Open the running Edge browser.
2. Navigate to `edge://inspect`.
3. In the sidebar, select **Remote debugging**.
4. Tick **"Allow remote debugging for this browser instance"**.
5. Accept the per-connection prompt when the controller connects.

This is a per-session grant. It must not be automated.

---

## 11. Actual Project and conversation read result

**Not performed (live).** CDP unavailable. No browser was attached, no Project was discovered, no conversation was read, no messages were persisted from a live source.

**Mock/local verification:** The read logic is verified by:
- `test_reader_discover_conversation` — discovers conversation via mocked browser.
- `test_reader_read_messages_persists` — reads and persists messages via mocked browser.
- `test_reader_discover_project_mismatch` — detects project identity mismatch.
- `test_reader_read_messages_ambiguous` — handles ambiguous responses gracefully.
- `test_mcp_list_projects`, `test_mcp_get_project`, `test_mcp_set_active_project`, `test_mcp_get_observations`, `test_mcp_get_reader_state` — MCP integration verified.

---

## 12. Explicit list of prohibited actions confirmed not performed

- ✅ No messages were sent to ChatGPT.
- ✅ No conversations were created.
- ✅ No OpenCode tasks were submitted or executed.
- ✅ No production or unrelated repository was modified.
- ✅ No API credentials, `.env`, OAuth, provider/model or tokens were changed.
- ✅ No Secure MCP Tunnel was launched.
- ✅ No controller endpoints were exposed publicly.
- ✅ No OpenCode API server or Edge was restarted.
- ✅ No browser processes were closed or terminated.
- ✅ No browser profiles were changed or substituted.
- ✅ No commits or pushes were made.
- ✅ No Edge/CDP configuration was changed.
- ✅ No automatic execution was enabled.
- ✅ No governance or security checks were weakened.

---

## 13. Remaining blockers and recommended next milestone

### Blockers
1. **CDP unavailable:** Operator must enable `edge://inspect` remote debugging. Same blocker as WP-429.
2. **No live verification:** All tests are mock/local. No real browser attachment or message reading occurred.

### Recommended next milestone (WP-432)
1. **Operator action first:** Perform `edge://inspect` remote-debugging opt-in.
2. **WP-432:** Live read-only verification:
   - Attach to Edge via CDP.
   - Discover Palmistry Project.
   - Read latest conversation messages.
   - Persist observations.
   - Retrieve via MCP tools.
   - Prove deduplication on repeat read.
3. **WP-433:** Only after WP-432, consider a single harmless communication test (operator-authorized).
4. **WP-434:** Only after WP-433, consider enabling the controller loop for ChatGPT-originated tasks.

**Files affected (WP-431B):**
- `src/opencode_bridge/chatgpt_project_reader.py` (new: registry, reader, validation, observations)
- `src/opencode_bridge/mcp_server.py` (added 8 read-only MCP tools, registry/reader params)
- `tests/test_wp431b_project_reader.py` (new: 37 tests)
- This report and the memory handoff

**No changes to:** `.env`, credentials, providers/models, browser/profiles, Edge, OpenCode server settings, production repository, or existing tests. No commits or pushes. No live execution. No server restart. No credential changes. No permission changes. No browser interaction. No ChatGPT messages sent. No tasks executed. No live Edge verification. Mock/local tests only.<|end|><|start|>write to=assistant<|channel|>analysis <|constrain|>xml<|message|><rfl:parameter name="content">
# WP-431B — Configurable ChatGPT Project Selection and Read-Only Conversation Reader

**Date:** 2026-11-03
**Repository:** `C:\Vijay_GitHub\opencode-automation-controller` (`master`, no commits; all work untracked)
**Verdict:** **PASS (mock/local integration).** Live Edge verification **BLOCKED** — CDP unavailable (DevToolsActivePort absent, no listener on 9222-9226). No live browser attachment, project discovery or message reading was performed. No messages were sent. No tasks were executed.

---

## 1. Executive verdict

**PASS (mock/local).** The configurable ChatGPT Project registry, read-only conversation reader, observation persistence and controller/MCP integration are implemented and verified through 37 focused tests + 201 regression tests = 238 total, all passing. Live Edge verification is **BLOCKED** — the operator has not enabled remote debugging via `edge://inspect`.

---

## 2. Architecture and files changed

### New module: `src/opencode_bridge/chatgpt_project_reader.py`
- `ChatGPTProjectRegistry` — manages configured ChatGPT Projects in SQLite. Tables: `chatgpt_projects`, `chatgpt_project_state`, `chatgpt_observations`. Supports registration, listing, get, active project selection, polling toggle, read state tracking, observation persistence with deduplication and edit detection.
- `ChatGPTProjectReader` — read-only reader wrapping `PlaywrightChatGPTAdapter`. Discovers conversations, reads messages, persists observations. Never sends messages or creates conversations.
- Validation functions: `validate_project_key`, `validate_project_url`, `derive_project_id`.

### Modified: `src/opencode_bridge/mcp_server.py`
- Added 8 read-only MCP tools: `list_chatgpt_projects`, `get_chatgpt_project`, `set_active_chatgpt_project`, `discover_chatgpt_conversation`, `read_chatgpt_messages`, `get_chatgpt_observations`, `get_chatgpt_reader_state`.
- `MCPServer.__init__` accepts optional `project_registry` and `project_reader`.

### New tests: `tests/test_wp431b_project_reader.py` (37 tests)

---

## 3. Configuration example and operator instructions

### Register a project
```python
from opencode_bridge.chatgpt_project_reader import ChatGPTProjectRegistry
from opencode_bridge.db import BridgeDB

db = BridgeDB(path)
registry = ChatGPTProjectRegistry(db)

# Palmistry is auto-registered as default on init
# Register additional projects:
registry.register_project(
    project_key="my-project",
    display_name="My ChatGPT Project",
    project_url="https://chatgpt.com/g/g-p-abc123def456/project",
    enabled=True,
    read_only=True,
    polling_interval_seconds=0,  # disabled by default
    excluded_titles=["OpenCode Automation Testing"],
)
```

### Select active project
```python
registry.set_active_project("my-project")
```

### Read messages (read-only)
```python
from opencode_bridge.chatgpt_interface import PlaywrightChatGPTAdapter
from opencode_bridge.browser_automation import MockBrowserAdapter

adapter = PlaywrightChatGPTAdapter(browser)
reader = ChatGPTProjectReader(adapter, registry, "my-project")
result = reader.read_messages(max_messages=10)
# result contains: project_key, conversation_id, conversation_title, messages, user_message_count
```

### Polling (disabled by default)
```python
registry.set_polling_enabled(True)  # explicit opt-in
# Polling interval configured per-project (polling_interval_seconds)
# Default: 0 (disabled)
```

### Validation rules
- Project key: alphanumeric, hyphens, underscores, dots; max 64 chars.
- Project URL: must start with `https://chatgpt.com/g/g-p-` and contain `/project`.
- Project ID: derived from URL (e.g., `g-p-6ae87c1e48b08191a2cd33139c40639f`).
- Fail closed for malformed or unsupported configuration.

---

## 4. Project selection behaviour

- Multiple named ChatGPT Projects can be registered in the SQLite database.
- One active Project is selected by a stable project key (`set_active_project`).
- Project switching is explicit and auditable (updates `chatgpt_project_state` table with timestamp).
- If the configured Project cannot be found, operations fail closed with `project not registered` error.
- Disabled projects cannot be set as active.
- Palmistry Project is auto-registered as the default on first init (preserving existing configuration).
- No silent Project switching — the reader verifies `project_id` matches between registered config and live UI.

---

## 5. Conversation discovery and selection evidence

- Discovery uses `PlaywrightChatGPTAdapter.discover_latest_conversation()` (existing WP-424 implementation).
- Conversations are discovered from the visible Project conversation list (not stored `/c/<id>` URLs).
- Latest eligible conversation selected by UI ordering (first eligible = newest).
- Exclusion rules are configurable per project (default: `["OpenCode Automation Testing"]`).
- If selection is ambiguous (no eligible conversations), returns explicit error with `reason: no_eligible`.
- Project identity verified: `result["project_id"]` must match registered `project_id`.

---

## 6. Message identity and persistence design

- **Message ID:** Uses `derive_message_id()` (deterministic SHA-256 hash of project_id + conversation_id + content). Labelled `derived_content_hash` — never presented as a UI ID.
- **Role distinction:** User messages (`role="user"`) vs assistant messages (`role="assistant"`). Only user messages count as incoming instructions.
- **Observation persistence:** Each observed message stored in `chatgpt_observations` table with:
  - `observation_id` (deterministic hash)
  - `project_key`, `conversation_id`, `conversation_title`
  - `message_id`, `role`, `content`, `content_hash`
  - `visible_timestamp`, `observed_at`
  - `is_duplicate` (1 if same message_id seen before)
  - `edit_of` (reference to previous observation if content changed)
- **Deduplication:** `UNIQUE INDEX` on `(project_key, conversation_id, message_id, content_hash)`. Duplicate observations return `duplicate: True` without inserting.
- **Edit detection:** If the same `message_id` is observed with different content, `is_duplicate=1` and `edit_of` references the previous observation. Previous content is retained.
- **No overwrite:** Previous observations are never deleted or overwritten.

---

## 7. Controller read operations

New MCP tools (all read-only):
- `list_chatgpt_projects` — list all configured Projects.
- `get_chatgpt_project` — get Project details by key.
- `set_active_chatgpt_project` — explicitly set active Project (auditable).
- `discover_chatgpt_conversation` — discover latest eligible conversation (read-only).
- `read_chatgpt_messages` — read and persist messages from latest conversation (read-only, no message sending).
- `get_chatgpt_observations` — retrieve persisted observations with optional filters (project_key, conversation_id, role, limit).
- `get_chatgpt_reader_state` — get reader state (last read, errors, polling status, active project).

All follow existing MCP conventions: JSON-RPC 2.0, loopback-only, bearer token auth, body bounded.

---

## 8. Polling and recovery behaviour

- **Disabled by default:** `polling_enabled=0` in `chatgpt_project_state`. `polling_interval_seconds=0` per project.
- **Explicit opt-in:** `registry.set_polling_enabled(True)` required.
- **Recovery:** All state persisted in SQLite. After restart, `get_state()` returns `last_read_at`, `last_error`, `active_project_key`. No data loss.
- **No background worker:** No polling thread starts automatically. Polling is a future milestone (WP-432+).
- **Bounded retries:** Configured per-project via `polling_interval_seconds`. Not implemented as automatic retry yet.
- **Fail-closed:** If browser attachment or Project identity verification fails, the reader returns an explicit error and updates `last_error` in state.

---

## 9. Tests run and results

| Suite | Tests | Result |
|---|---|---|
| `test_wp431b_project_reader.py` (new) | 37 | pass |
| `test_wp430_mcp_server.py` | 32 | pass |
| `test_wp427_session_directory.py` | 13 | pass |
| `test_wp425_opencode_execution.py` | 17 | pass |
| `test_wp424_chatgpt_adapter.py` | 39 | pass |
| `test_wp423_orchestrator.py` | 35 | pass |
| `test_wp423_contracts.py` | 29 | pass |
| `test_wp423_persistence.py` | 17 | pass |
| `test_wp423_controller_api.py` | 19 | pass |
| **Total** | **238** | **all pass** |

No existing tests were weakened. No assertions were skipped.

---

## 10. Actual live Edge attachment result

**BLOCKED.** CDP unavailable.

- `DevToolsActivePort`: absent (`C:\Users\user\AppData\Local\Microsoft\Edge\User Data\DevToolsActivePort` does not exist).
- Port scan (9222-9226): all closed.
- No listener on any port in 9220-9235 range.
- `discover_ws_endpoint()` returns blocked result with `cdp_connect_failed`.
- `PlaywrightEdgeAdapter.attach_existing()` returns `{"ok": False, "error": "cdp_connect_failed"}`.

**Operator action required:**
1. Open the running Edge browser.
2. Navigate to `edge://inspect`.
3. In the sidebar, select **Remote debugging**.
4. Tick **"Allow remote debugging for this browser instance"**.
5. Accept the per-connection prompt when the controller connects.

This is a per-session grant. It must not be automated.

---

## 11. Actual Project and conversation read result

**Not performed (live).** CDP unavailable. No browser was attached, no Project was discovered, no conversation was read, no messages were persisted from a live source.

**Mock/local verification:** The read logic is verified by:
- `test_reader_discover_conversation` — discovers conversation via mocked browser.
- `test_reader_read_messages_persists` — reads and persists messages via mocked browser.
- `test_reader_discover_project_mismatch` — detects project identity mismatch.
- `test_reader_read_messages_ambiguous` — handles ambiguous responses gracefully.
- `test_mcp_list_projects`, `test_mcp_get_project`, `test_mcp_set_active_project`, `test_mcp_get_observations`, `test_mcp_get_reader_state` — MCP integration verified.

---

## 12. Explicit list of prohibited actions confirmed not performed

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
- No Edge/CDP configuration was changed.
- No automatic execution was enabled.
- No governance or security checks were weakened.

---

## 13. Remaining blockers and recommended next milestone

### Blockers
1. **CDP unavailable:** Operator must enable `edge://inspect` remote debugging. Same blocker as WP-429.
2. **No live verification:** All tests are mock/local. No real browser attachment or message reading occurred.

### Recommended next milestone (WP-432)
1. **Operator action first:** Perform `edge://inspect` remote-debugging opt-in.
2. **WP-432:** Live read-only verification:
   - Attach to Edge via CDP.
   - Discover Palmistry Project.
   - Read latest conversation messages.
   - Persist observations.
   - Retrieve via MCP tools.
   - Prove deduplication on repeat read.
3. **WP-433:** Only after WP-432, consider a single harmless communication test (operator-authorized).
4. **WP-434:** Only after WP-433, consider enabling the controller loop for ChatGPT-originated tasks.

**Files affected (WP-431B):**
- `src/opencode_bridge/chatgpt_project_reader.py` (new: registry, reader, validation, observations)
- `src/opencode_bridge/mcp_server.py` (added 8 read-only MCP tools, registry/reader params)
- `tests/test_wp431b_project_reader.py` (new: 37 tests)
- This report and the memory handoff

**No changes to:** `.env`, credentials, providers/models, browser/profiles, Edge, OpenCode server settings, production repository, or existing tests. No commits or pushes. No live execution. No server restart. No credential changes. No permission changes. No browser interaction. No ChatGPT messages sent. No tasks executed. No live Edge verification. Mock/local tests only.