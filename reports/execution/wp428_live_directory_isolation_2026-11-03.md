# WP-428 — Live OpenCode Directory-Isolation Verification

**Date:** 2026-11-03
**Repository:** `C:\Vijay_GitHub\opencode-automation-controller` (`master`, no commits; all work untracked)
**Verdict:** **PASS.** The WP-427 directory-isolation implementation is verified against the real OpenCode API. The session's effective working directory is confirmed by API metadata, the expected file was created in the disposable workspace with exact content, actual output was retrieved and persisted, and reconciliation caused no duplicate execution.

---

## 1. Executive verdict

**PASS.** All 10 acceptance criteria are satisfied:

1. ✅ Real authenticated OpenCode API used (health `{"healthy": True, "version": "1.18.30"}`).
2. ✅ Explicit `?directory=` parameter used (verified in adapter code + live session metadata).
3. ✅ Actual session created (`ses_e620da1c6ffe75NjYFKOgx3EAg`).
4. ✅ Effective directory independently verified (session `directory` = `C:\Users\user\AppData\Local\Temp\opencode\wp426_smoke`).
5. ✅ Exactly one live task executed (smoke ID `WP428-2AB5E8391909`).
6. ✅ Expected file verified in disposable workspace (`WP428_DIRECTORY_ISOLATION.txt` with exact content).
7. ✅ No unrelated repository modified (no files in controller repo or any other repo).
8. ✅ Actual output and timestamps persisted (`started_at`, `completed_at`, `execution_output`).
9. ✅ Correct terminal controller state (`READY`, task `completed`, execution `completed`).
10. ✅ No duplicate execution (reconciliation preserved session ID and execution ID).

---

## 2. Pre-flight evidence

- **OpenCode API:** `http://127.0.0.1:4097`, version 1.18.30, authenticated via `OPENCODE_SERVER_PASSWORD` from `.env`.
- **Model:** `opencode` / `beam-free` (runtime env override, no `.env` or config file change; authorized by operator).
- **Disposable workspace:** `C:\Users\user\AppData\Local\Temp\opencode\wp426_smoke` (operator-approved, isolated, no credentials).
- **Workspace permission:** `external_directory` allow list includes the disposable path (verified via `/config`).
- **Controller DB:** `C:\Users\user\AppData\Local\Temp\opencode\wp428_orch.db` (fresh, isolated).
- **WP-427 implementation:** `?directory=` query param on `create_session`, `send_prompt_async`, `get_messages`, `abort`. Propagated through `TaskControllerExecutor`.
- **WP-426R3 session reconciled:** Original session `ses_e62518dc0ffeEXENtXkF7SeJ3H` remains as separate evidence.
- **No ambiguously running executions.**

---

## 3. Operator approval evidence

Operator explicitly approved:
- Using `OPENCODE_MODEL_PROVIDER=opencode` and `OPENCODE_MODEL_ID=beam-free` as runtime env override (no config file changes).
- Using the existing disposable workspace `C:\Users\user\AppData\Local\Temp\opencode\wp426_smoke`.
- Submitting exactly one harmless task.

No server restart, credential change, or permission change was performed.

---

## 4. Task, execution and session identities

- **Smoke ID:** `WP428-2AB5E8391909` (unique, generated before submission)
- **Task ID:** `task-663af95e12b54505`
- **Execution ID:** `exec-3f9e7e7e67fe4d36`
- **OpenCode session ID:** `ses_e620da1c6ffe75NjYFKOgx3EAg`
- **Mission ID:** `wp428-mission`

---

## 5. Effective workspace evidence

- **Session creation:** `POST /session?directory=C%3A%5CUsers%5C...%5Cwp426_smoke` (URL-encoded).
- **Session metadata:** `GET /session/{id}` returns `"directory": "C:\\Users\\user\\AppData\\Local\\Temp\\opencode\\wp426_smoke"`.
- **Independent verification:** The session's `directory` field matches the intended disposable workspace exactly.
- **No unrelated repository:** No file created in controller repo, fno-ai-paper-trading, or any other directory.

---

## 6. Actual execution output

```
Done.
```

Non-empty output. 9+ output tokens consumed by the model (`beam-free`).

---

## 7. File verification

- **Expected file:** `C:\Users\user\AppData\Local\Temp\opencode\wp426_smoke\WP428_DIRECTORY_ISOLATION.txt`
- **Exists:** ✅
- **Content:** `WP428_DIRECTORY_ISOLATION=WP428-2AB5E8391909` (exact match, no trailing newline)
- **Other files in workspace:** `README.txt` (unchanged) + `WP428_DIRECTORY_ISOLATION.txt` only.
- **No files created elsewhere.**

---

## 8. Persistence and reconciliation evidence

- **Execution row:** `exec-3f9e7e7e67fe4d36`, status `completed`, completion_status `completed`.
- **Session ID:** `ses_e620da1c6ffe75NjYFKOgx3EAg` (persisted before submission).
- **Timestamps:** `submitted_at=1793649776.549`, `started_at=1793649776.748`, `completed_at=1793649788.182`.
- **Verification evidence:** `{"source": "task_controller", "git_status": "", "workspace": "C:\\Users\\user\\AppData\\Local\\Temp\\opencode\\wp426_smoke"}`.
- **Reconciliation:** `recover()` returned `{"ok": True, "state": "READY", "actions": []}`. Session ID and execution ID unchanged. No duplicate submission.
- **Task status:** `completed`.
- **Mission state:** `READY`.

---

## 9. Regression test results

| Suite | Tests | Result |
|---|---|---|
| `test_wp427_session_directory.py` | 13 | pass |
| `test_wp425_opencode_execution.py` | 17 | pass |
| `test_wp424_chatgpt_adapter.py` | 39 | pass |
| `test_wp423_orchestrator.py` | 35 | pass |
| `test_wp423_contracts.py` | 29 | pass |
| `test_wp423_persistence.py` | 17 | pass |
| `test_wp423_controller_api.py` | 19 | pass |
| **Total** | **169** | **all pass** |

No existing tests were weakened. No assertions were skipped.

---

## 10. Limitations

1. **`changed_files` empty:** The controller's `_git_changed_files()` runs `git status --porcelain` in the workspace, which is not a git repo, so it returns `[]`. The file creation is verified by independent file check. A future milestone could use the OpenCode session's `summary.files` field.
2. **Model is runtime override, not config default:** The smoke test used `opencode`/`beam-free` via runtime env vars. The permanent default remains `opencode-go`/`gpt-5.6-luna` (which doesn't produce output). WP-426C reconciled this.
3. **ChatGPT browser integration remains blocked** on WP-422 (CDP unavailable). The autonomous loop is not operational.
4. **No commit or push** was made. All files remain untracked.

---

## 11. Recommendation for WP-429

1. **WP-429:** Resolve the `gpt-5.6-luna` model issue (set `OPENCODE_API_KEY` in server env or switch to a working default model).
2. **WP-430:** ChatGPT browser integration (blocked on WP-422 operator opt-in).
3. Only after WP-429/430, consider enabling the controller's automatic execution loop for ChatGPT-originated tasks.

**Files affected (WP-428):** No code changes. Only the disposable workspace file (`WP428_DIRECTORY_ISOLATION.txt`) and the report/memory handoff. **No changes to** `.env`, credentials, providers/models, browser/profiles, Edge, production repository, or existing tests. No commits or pushes. No server restart. No credential changes. No permission changes. No live task beyond the single authorized one.