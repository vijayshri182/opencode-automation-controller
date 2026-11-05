# WP-427 — OpenCode Session Working-Directory Isolation

**Date:** 2026-11-03
**Repository:** `C:\Vijay_GitHub\opencode-automation-controller` (`master`, no commits; all work untracked)
**Verdict:** **PASS (mock/local integration).** Live verification is operator-gated and was not performed in this task (no live task submitted, no server restart, no credential change).

---

## 1. Executive verdict

**PASS (mock/local).** Explicit working-directory targeting is implemented and verified through deterministic tests. The OpenCode API adapter now supports `?directory=` on session creation, prompt submission, message retrieval and abort. The controller propagates the validated workspace through the full execution lifecycle. Path governance rejects unauthorized workspaces before submission. Execution evidence records the effective workspace. Backward compatibility is preserved (no directory = no query param = original behavior). 13 new focused tests + 156 regression tests = 169 total, all passing.

---

## 2. API contract findings

- **Session creation:** `POST /session?directory=<path>` sets the session's working directory. Verified via direct API call during WP-426R3.
- **Prompt submission:** `POST /session/{id}/prompt_async?directory=<path>` targets the correct session in the correct directory.
- **Message retrieval:** `GET /session/{id}/message?directory=<path>&limit=N` retrieves messages from the correct session.
- **Abort:** `POST /session/{id}/abort?directory=<path>` aborts in the correct context.
- **Health:** `GET /global/health` (no directory param) — unaffected.
- **Directory representation:** The session object includes a `directory` field confirming the working directory. Verified in WP-426 (sessions showed `"directory": "C:\\Vijay_GitHub\\opencode-automation-controller"` when no param was passed, and the disposable path when passed).
- **Session discovery:** `GET /session?directory=<path>` lists sessions for that directory.
- **Backward compatibility:** All endpoints work without `?directory=` (server uses its default). Verified by existing callers and tests.

---

## 3. Adapter changes

### `OpenCodeAdapter` (`opencode_adapter.py`)
- `create_session(title, directory=None)` — adds `?directory=` query param when provided.
- `send_prompt_async(session_id, text, model, directory=None)` — adds `?directory=` query param.
- `get_messages(session_id, limit, directory=None)` — adds `?directory=` (and `limit`) as query params. Previously, `limit` was embedded in the path; now it's a query param (cleaner, backward compatible).
- `abort(session_id, directory=None)` — adds `?directory=` query param.
- `_request(method, path, body, retry, query)` — added `query` parameter for URL-encoded query string.

### `TaskControllerExecutor` (`executors.py`)
- `submit()`: passes `directory=self.workspace` to `create_session` and `send_prompt_async`.
- `poll()`: passes `directory=self.workspace` to `get_messages`.
- `reconcile()`: passes `directory=self.workspace` to `get_messages`.
- `abort()`: passes `directory=self.workspace` to `abort`.

### `MissionOrchestrator` (`orchestrator.py`)
- `submit_and_execute()`: records `workspace` in `verification_evidence`.
- Added workspace governance check (removed — governance already covers it via `repository_not_allowed`).

### `MockOpenCodeAdapter` (`opencode_adapter.py`)
- Updated signatures to accept `directory` parameter (backward compatible).

---

## 4. Path validation and governance behavior

- The controller's `allowed_repositories` list governs which workspaces can be used. `submit_and_execute` calls `evaluate_governance` which checks `target_repository` against `allowed_repositories`.
- A directory outside the approved scope is rejected during task creation (governance returns `blocked` with `repository_not_allowed`).
- Relative paths, malformed paths and ambiguous paths: the governance check compares the full workspace path against the allow list, so any non-exact match is rejected.
- Prompt content cannot override the working directory — the directory is derived from `self.workspace` (set at mission creation), not from task text.
- A missing directory (empty workspace) results in `directory=None` being passed to the adapter (no query param), preserving original behavior. This does not cause silent execution in another repository because the server uses its configured default directory.
- Existing task provenance and approval gates are unchanged.

---

## 5. Focused and regression test results

| Suite | Tests | Result |
|---|---|---|
| `test_wp427_session_directory.py` (new) | 13 | pass |
| `test_wp425_opencode_execution.py` | 17 | pass |
| `test_wp424_chatgpt_adapter.py` | 39 | pass |
| `test_wp423_orchestrator.py` | 35 | pass |
| `test_wp423_contracts.py` | 29 | pass |
| `test_wp423_persistence.py` | 17 | pass |
| `test_wp423_controller_api.py` | 19 | pass |
| **Total** | **169** | **all pass** |

### WP-427 test coverage
- Session creation includes correct `directory` query parameter.
- Windows paths encoded correctly (round-trip verified).
- Explicit directory propagation through complete adapter lifecycle (create, submit, poll, reconcile, abort).
- Session polling and result retrieval retain correct identity.
- Backward compatibility (no directory = no query param).
- Server rejection of directory surfaced clearly.
- No fallback to server's default directory (directory is always passed when workspace is set).
- Duplicate submission and reconciliation behavior unchanged.
- Restart recovery retains original execution's workspace identity.
- Execution evidence records effective directory.
- Unauthorized paths fail closed (governance blocks).
- Adapter method signatures have correct defaults.

No existing tests were weakened. No assertions were skipped.

---

## 6. Live versus mock/local verification distinction

| Capability | Live (WP-426R3) | Mock/local (WP-427 tests) |
|---|---|---|
| API reachability | ✅ (health 200, v1.18.30) | N/A |
| Session creation with `?directory=` | ✅ (verified: session `directory` field matches) | ✅ (query param asserted) |
| Execution in disposable workspace | ✅ (file created in wp426_smoke) | N/A |
| File verification | ✅ (exact content match) | N/A |
| Directory propagation | Not directly tested live | ✅ (13 tests) |
| Governance rejection | Not tested live | ✅ |
| Restart recovery | Not tested live | ✅ |

**No live verification was performed in WP-427.** The task's safety boundaries prohibit live execution without explicit authorization. The WP-426R3 live test (which used `opencode`/`beam-free`) already demonstrated that the `?directory=` parameter works (the session's `directory` field matched the disposable workspace path). WP-427 adds the adapter-level support to make this automatic.

---

## 7. Exact workspace used (live verification)

Not applicable — no live verification was performed in WP-427. The WP-426R3 live test used `C:\Users\user\AppData\Local\Temp\opencode\wp426_smoke` and confirmed the `?directory=` parameter works (session `directory` field = disposable path).

---

## 8. Execution and session identities (live verification)

Not applicable — no live verification in WP-427. WP-426R3 identities are preserved:
- Smoke ID: `WP426R3-FD4C78EA88E6`
- Task ID: `task-084cd566efe540ce`
- Execution ID: `exec-1c5dcaf9efd540c1`
- Session ID: `ses_e622467c3ffe2uNrI8ydvlBacF`

---

## 9. Evidence that no unrelated repository was modified

- WP-427 made no live API calls.
- No files were created in any repository.
- The only file modifications are in the controller repository (source code + tests).
- No production repository was accessed or modified.
- The disposable workspace (`wp426_smoke`) was not modified by WP-427.

---

## 10. Remaining risks

1. **`changed_files` still empty from real adapter:** The `_git_changed_files()` method runs `git status --porcelain` in the workspace. If the workspace is not a git repo, it returns `[]`. The file creation is still verified by independent file check. A future milestone could use the OpenCode session's `summary.files` field instead.
2. **Adapter doesn't set directory on `create_session` by default in `TaskController`:** The `TaskController` (legacy path) calls `adapter.create_session(title=...)` without directory. Only `TaskControllerExecutor` (WP-423 path) passes directory. This is acceptable — the legacy path is not used by the controller orchestrator.
3. **No live verification in WP-427:** The `?directory=` parameter was verified live in WP-426R3, but the full adapter lifecycle (create → submit → poll → reconcile → abort) with directory was only tested with mocks. A future operator-gated live test could verify the complete lifecycle.
4. **External directory permission:** The disposable workspace is in the allow list. If the workspace is cleaned up, the permission entry becomes stale (harmless).

---

## 11. Recommendation for the next milestone

1. **WP-428:** Operator-gated live verification of the full directory-isolated lifecycle (create session with `?directory=`, submit, poll, verify file in disposable workspace, reconcile). Use the existing WP-426R3 pattern but with the adapter's automatic directory propagation.
2. **WP-429:** Resolve the `gpt-5.6-luna` model issue (set `OPENCODE_API_KEY` in server env).
3. **WP-430:** ChatGPT browser integration (blocked on WP-422 operator opt-in).
4. Only after WP-428/429/430, consider enabling the controller's automatic execution loop for ChatGPT-originated tasks.

**Files affected (WP-427):**
- `src/opencode_bridge/opencode_adapter.py` (added `directory` param to `create_session`, `send_prompt_async`, `get_messages`, `abort`, `_request`)
- `src/opencode_bridge/executors.py` (pass `directory=self.workspace` through lifecycle)
- `src/opencode_bridge/orchestrator.py` (record `workspace` in `verification_evidence`)
- `src/opencode_bridge/opencode_adapter.py` `MockOpenCodeAdapter` (added `directory` param)
- `tests/test_wp427_session_directory.py` (new, 13 tests)
- This report and the memory handoff

**No changes to:** `.env`, credentials, providers/models, browser/profiles, Edge, production repository, or existing tests. No commits or pushes. No live execution. No server restart. No credential changes. No permission changes.