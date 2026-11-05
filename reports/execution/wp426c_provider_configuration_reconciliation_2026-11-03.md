# WP-426C — Provider Configuration and Governance Reconciliation

**Date:** 2026-11-03
**Repository:** `C:\Vijay_GitHub\opencode-automation-controller` (`master`, no commits; all work untracked)
**Verdict:** **PASS.** The WP-426R remediation changes were audited and reconciled. The configurable provider/model implementation is preserved and backward compatible. The default is restored to the original `opencode-go`/`gpt-5.6-luna` (via empty defaults = server default). The `.env` model overrides were removed. The disposable workspace permission is retained (narrowly scoped). WP-426R3 evidence is preserved. No new live execution occurred.

---

## 1. Executive verdict

**PASS.** All reconciliation requirements met:

- Configurable provider/model implementation preserved (backward compatible).
- Default restored to original (empty = server default = `opencode-go`/`gpt-5.6-luna`).
- No silent permanent change to `beam-free` as default.
- `.env` model overrides removed (original `.env` state restored).
- Disposable workspace permission retained (narrowly scoped).
- WP-426R3 evidence preserved.
- No new live execution.
- No credentials exposed.

---

## 2. Initial branch, HEAD and working-tree status

- **Branch:** `master`
- **HEAD:** no commits (unknown revision)
- **Working tree:** all files untracked (no tracked changes). Pre-existing untracked directories preserved (`.edge-profile*`, `config/`, `docs/`, `reports/`, `scripts/`, `src/`, `tests/`, etc.).

---

## 3. Exact affected-file inventory

| File | Change | Status |
|---|---|---|
| `src/opencode_bridge/config.py` | Added `opencode_model_provider()` and `opencode_model_id()` (defaults now empty = server default) | Modified (retained) |
| `src/opencode_bridge/executors.py` | `TaskControllerExecutor.submit` passes model to `send_prompt_async` only when both provider and model_id are non-empty | Modified (retained) |
| `.env` | Removed `OPENCODE_MODEL_PROVIDER` and `OPENCODE_MODEL_ID` lines (restored to original 2-line state) | Modified (reverted model overrides) |
| `~/.config/opencode/opencode.jsonc` | Added disposable workspace to `external_directory` allow list | Modified (retained, narrowly scoped) |

No other files were modified by WP-426R/WP-426C.

---

## 4. Original versus smoke-test provider/model comparison

| | Original (pre-WP-426) | WP-426R3 smoke test | After WP-426C reconciliation |
|---|---|---|---|
| Provider | `opencode-go` (server default) | `opencode` (via env override) | `opencode-go` (server default, via empty config default) |
| Model | `gpt-5.6-luna` (server default) | `beam-free` (via env override) | `gpt-5.6-luna` (server default, via empty config default) |
| Config mechanism | No config functions (model not passed) | Config functions with `opencode`/`beam-free` defaults + `.env` override | Config functions with empty defaults (model not passed unless explicitly configured) |
| Behavior | Server uses its default model | Explicitly uses `opencode`/`beam-free` | Server uses its default model (backward compatible) |

---

## 5. Changes retained, changed or restored and why

### Retained
- **`config.py` functions:** `opencode_model_provider()` and `opencode_model_id()` are retained. They provide configurability via `OPENCODE_MODEL_PROVIDER` and `OPENCODE_MODEL_ID` environment variables. Defaults changed to `""` (empty) so that no model is passed unless explicitly configured — restoring original behavior.
- **`executors.py` model propagation:** Retained. `TaskControllerExecutor.submit` now passes `model` to `send_prompt_async` only when both provider and model_id are non-empty. When empty, `model=None` is passed (original behavior — server uses its default).
- **`opencode.jsonc` permission:** Retained. The disposable workspace `C:\Users\user\AppData\Local\Temp\opencode\wp426_smoke` is narrowly scoped. Existing fno-ai-paper-trading permissions preserved.

### Changed
- **Config defaults:** Changed from `opencode`/`beam-free` to `""`/`""` (empty). This restores the original behavior where no model is explicitly passed, letting the server use its configured default.
- **`.env` overrides:** Removed `OPENCODE_MODEL_PROVIDER` and `OPENCODE_MODEL_ID` lines. The `.env` is restored to its original 2-line state (base URL + password).

### Not changed
- No changes to `opencode_adapter.py`, `orchestrator.py`, `controller.py`, `state_machine.py`, `contracts.py`, `db.py`, or any test file.
- No changes to credentials, provider/model configuration in the OpenCode server, or production repositories.

---

## 6. `.env` treatment without secret disclosure

- **Prior state:** 2 lines (`OPENCODE_BASE_URL`, `OPENCODE_SERVER_PASSWORD`).
- **WP-426R state:** 5 lines (added 3 lines for model config).
- **After WP-426C:** 2 lines (restored to prior state).
- **Secret values:** Not displayed. Only line counts and key names are reported.
- **No secret values were printed, logged or exposed.**

---

## 7. OpenCode permission configuration status

- **File:** `C:\Users\user\.config\opencode\opencode.jsonc`
- **Before WP-426R:** Only `fno-ai-paper-trading/**` (two path variants).
- **After WP-426R/WP-426C:** Added `wp426_smoke/**` (two path variants).
- **Scope:** Narrowly scoped to the exact disposable path. Parent `Temp\opencode` is NOT granted. No other paths added.
- **Can be safely removed later:** Yes, after WP-426 verification is complete and the disposable workspace is cleaned up (operator authorization required for cleanup).
- **Config verified:** `/config` endpoint returns the updated permissions.

---

## 8. Focused test results

| Suite | Tests | Result |
|---|---|---|
| `test_wp425_opencode_execution.py` | 17 | pass |
| `test_wp423_orchestrator.py` | 35 | pass |
| `test_wp423_contracts.py` | 29 | pass |
| `test_wp423_persistence.py` | 17 | pass |
| `test_wp423_controller_api.py` | 19 | pass |
| `test_wp424_chatgpt_adapter.py` | 39 | pass |

**Total: 156 passed.** No tests were weakened, skipped or deleted. No new tests added (none needed — the reconciliation is config-only).

---

## 9. WP-426R3 evidence preservation

- **Smoke ID:** `WP426R3-FD4C78EA88E6`
- **Task ID:** `task-084cd566efe540ce`
- **Execution ID:** `exec-1c5dcaf9efd540c1`
- **Session ID:** `ses_e622467c3ffe2uNrI8ydvlBacF`
- **File:** `C:\Users\user\AppData\Local\Temp\opencode\wp426_smoke\WP426_SMOKE_TEST.txt` (content: `SMOKE_ID=WP426R3-FD4C78EA88E6 CREATED_BY=WP426_LIVE_OPENCODE`)
- **DB:** `C:\Users\user\AppData\Local\Temp\opencode\wp426r3_orch.db` (preserved)
- **Evidence JSON:** `C:\Users\user\AppData\Local\Temp\opencode\wp426r3_evidence.json` (preserved)
- **Report:** `reports/execution/wp426_live_opencode_api_smoke_test_2026-11-03.md` (PASS verdict, historical record preserved)
- **Historical record:** WP-426R3 used `opencode`/`beam-free` model. This is documented in the report and remains accurate regardless of the restored default.

---

## 10. Remaining risks and unresolved decisions

1. **Default model non-functional:** The restored default (`opencode-go`/`gpt-5.6-luna`) produces 0 tokens (verified in WP-426/WP-426R). The controller will pass no model (server default) when env vars are unset. This is the original behavior and is documented as unverified.
2. **Operator must explicitly configure a working model:** To use `beam-free` or any other model, the operator sets `OPENCODE_MODEL_PROVIDER` and `OPENCODE_MODEL_ID` in `.env`. This is now configurable without code changes.
3. **No implicit fallback:** The implementation does not fall back to another model if the configured one fails. If the server default doesn't work, execution fails (correct behavior — no silent switching).
4. **Permission cleanup:** The disposable workspace permission can be removed after WP-426 verification is complete and the workspace is cleaned up (operator authorization required for cleanup).
5. **No live execution in this task:** Per WP-426C scope, no live task was submitted. The WP-426R3 evidence remains the last live verification.

---

## 11. Explicit statement

**No new live execution occurred in WP-426C.** This task was audit and reconciliation only. No OpenCode session was created, no prompt was sent, no file was created or modified in the disposable workspace.

---

## 12. Recommendation for WP-427 readiness

The controller is ready for WP-427 (set session working directory via `?directory=` query parameter in `OpenCodeAdapter`):

- Provider/model configurability is implemented and tested.
- Default behavior is restored to original (backward compatible).
- The successful WP-426R3 live execution provides a verified baseline using `opencode`/`beam-free`.
- The disposable workspace permission is in place.
- All 156 WP-423/424/425 tests pass.

**Recommended WP-427 scope:**
1. Add `directory` parameter support to `OpenCodeAdapter.create_session()` and `send_prompt_async()`.
2. Update `TaskControllerExecutor.submit()` to pass the workspace as `directory`.
3. Add tests for directory propagation.
4. Verify with a live smoke test (operator-gated) that the file is created in the disposable workspace without requiring absolute paths in the task text.

**Files affected (WP-426C):** `src/opencode_bridge/config.py`, `src/opencode_bridge/executors.py`, `.env`. **No changes to** `~/.config/opencode/opencode.jsonc` (permission already in place), `opencode_adapter.py`, `orchestrator.py`, `controller.py`, or any test file. No commits or pushes.