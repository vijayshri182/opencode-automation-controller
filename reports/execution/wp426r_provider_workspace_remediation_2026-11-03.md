# WP-426R — Provider and Workspace Remediation

**Date:** 2026-11-03
**Repository:** `C:\Vijay_GitHub\opencode-automation-controller` (`master`, no commits; all work untracked)
**Verdict:** **BLOCKED.** The disposable workspace permission was successfully added and the OpenCode server was restarted. However, the `OPENCODE_API_KEY` required by the configured `opencode-go` provider is not available in any approved secret store or operator-managed environment source. The model produces 0 tokens for every prompt. The live retry could not be performed.

---

## 1. Executive verdict

**BLOCKED.** Provider credential unavailable. The OpenCode API server is reachable, authenticated and healthy (v1.18.30). The `external_directory` permission for the disposable workspace was added and verified after a server restart. But the configured model (`opencode-go` / `gpt-5.6-luna`) cannot execute because `OPENCODE_API_KEY` is not set in the server's environment. No live task was submitted in this remediation. The original WP-426 execution was reconciled as failed.

---

## 2. Original WP-426 session reconciliation

- **Execution ID:** `exec-81b3ec34a3e64e33`
- **Session ID:** `ses_e62518dc0ffeEXENtXkF7SeJ3H`
- **Original status:** `running` (0 tokens, 0 output, 0 files)
- **Reconciliation:** Marked execution as `failed` (completion_status `failed`, error recorded). Task marked `failed`. Mission state left as `READY` (transition to `RECONCILIATION_REQUIRED` not permitted from `READY`; evidence preserved).
- **Reconcile result:** `found: True` (session exists) but `0 tokens` → not interpreted as success.
- Original evidence preserved in DB (`C:\Users\user\AppData\Local\Temp\opencode\wp426_orch.db`) and report (`wp426_live_opencode_api_smoke_test_2026-11-03.md`).

---

## 3. Provider remediation method

**Not performed — credential unavailable.**

- Inspected the OpenCode server's provider configuration: `opencode-go` source `api`, env `['OPENCODE_API_KEY']`, models include `gpt-5.6-luna`.
- Checked controller environment: `OPENCODE_API_KEY` is **not set**.
- Checked Windows user environment variables: **not set**.
- Checked `~/.config/opencode/opencode.jsonc`: no provider credential (only permissions).
- Checked controller `.env`: only `OPENCODE_SERVER_PASSWORD` (for server auth, not model provider).
- No approved secret store or operator-managed environment source contains `OPENCODE_API_KEY`.
- **The credential was not invented, generated, substituted or retrieved from unrelated sources.**
- **No credential value was printed, logged or exposed.**

**Operator action required:** Provide `OPENCODE_API_KEY` through the approved secret-management mechanism (e.g., set it in the OpenCode server's environment or in `~/.config/opencode/` configuration). Do not paste the secret into this conversation.

---

## 4. Workspace permission before/after

**Before:**
```json
"external_directory": {
  "C:/Vijay_GitHub/fno-ai-paper-trading/**": "allow",
  "C:\\Vijay_GitHub\\fno-ai-paper-trading\\**": "allow"
}
```

**After:**
```json
"external_directory": {
  "C:/Vijay_GitHub/fno-ai-paper-trading/**": "allow",
  "C:\\Vijay_GitHub\\fno-ai-paper-trading\\**": "allow",
  "C:/Users/user/AppData/Local/Temp/opencode/wp426_smoke/**": "allow",
  "C:\\Users\\user\\AppData\\Local\\Temp\\opencode\\wp426_smoke\\**": "allow"
}
```

- Existing permission rules preserved.
- Only the exact disposable path `C:\Users\user\AppData\Local\Temp\opencode\wp426_smoke` was added.
- Parent `C:\Users\user\AppData\Local\Temp\opencode` was **not** granted.
- No other repositories or paths were granted.
- Permission verified via `/config` endpoint after restart.

---

## 5. Restart details

- **Reason:** Apply the `external_directory` permission change (config file edit).
- **Process:** PID 25232 (`opencode serve --port 4097 --hostname 127.0.0.1`), parent process 29448 (orphaned).
- **Action:** Stopped PID 25232, started new instance (PID 29924) with same command and working directory `C:\Vijay_GitHub\opencode-automation-controller`.
- **Environment:** `OPENCODE_SERVER_PASSWORD` set from `.env` value (for server auth).
- **Post-restart health:** `{"healthy": True, "version": "1.18.30"}` — authentication verified.
- **Post-restart config:** permissions include the new disposable workspace path (verified via `/config`).
- **No software installed or updated. No version changed.**

---

## 6. Provider diagnostic evidence

- **Health:** `{"healthy": True, "version": "1.18.30"}` ✅
- **Authentication:** verified (health call succeeded with configured credentials) ✅
- **Model execution test:** Sent "Reply with exactly the word HELLO" to a new session in the disposable workspace. Result: **0 tokens, 0 parts, 0 cost**. ❌
- **Root cause:** `OPENCODE_API_KEY` not available to the OpenCode server. The `opencode-go` provider requires this env var; without it, the model call fails silently (no error in message, just empty output).
- **No non-empty diagnostic output was produced.** The retry was not attempted.

---

## 7. Controller timeout/reconciliation correction

No code changes were made in this remediation. The controller's existing timeout/reconciliation logic (WP-423/425) is sound:

- `poll()` returns `running` when the deadline passes without assistant text.
- `recover()` reconciles via persisted session ID without resubmitting.
- Empty output is not classified as success (only `finished=True` with text triggers `_persist_result`).
- The original WP-426 execution was correctly left in `running` until manually reconciled.

No genuine gap was found. No new tests were added (none needed).

---

## 8. New task, execution and session IDs

**Not applicable.** No retry task was submitted because the provider credential is unavailable. The original WP-426 execution (`exec-81b3ec34a3e64e33`, session `ses_e62518dc0ffeEXENtXkF7SeJ3H`) remains as separate evidence (reconciled as failed).

---

## 9. Actual execution output

**None.** No execution was attempted in this remediation (credential blocker). The model produces 0 tokens for all prompts.

---

## 10. File verification

No file was created (no retry attempted). The disposable workspace contains only `README.txt` (unchanged). No production repository was modified.

---

## 11. Durable persistence and final state

- Original WP-426 execution: `failed` (reconciled).
- New execution: none (blocked).
- Controller DB: `C:\Users\user\AppData\Local\Temp\opencode\wp426_orch.db` (unchanged since reconciliation).
- Mission state: `READY`.
- Permission config: updated and verified.
- OpenCode server: running (PID 29924), healthy, authenticated.

---

## 12. Regression results

No new tests were run (no code changes). Existing WP-423/424/425 test suites (156 tests) remain passing from prior runs. No tests were weakened or skipped.

---

## 13. Remaining limitations and next recommended milestone

1. **BLOCKER:** `OPENCODE_API_KEY` is not available in any approved secret store. The operator must provide it through the approved secret-management mechanism (e.g., set it in the OpenCode server's environment, or in `~/.config/opencode/` configuration, or via a secure credential store). Do not paste the secret into this conversation.
2. **Permission verified:** The disposable workspace is now in the `external_directory` allow list. Once the credential is available, the agent should be able to write to it.
3. **Controller ready:** WP-423/424/425 implementations are sound and tested. The only blockers are the missing model credential and (previously) the workspace permission (now resolved).
4. **Next milestone (WP-426R2 or WP-427):** Once `OPENCODE_API_KEY` is available, re-run WP-426: submit one uniquely identified harmless task, verify actual execution output, file creation, durable persistence, and reconciliation without duplicate. Then consider enabling automatic execution for ChatGPT-originated tasks.

**Files affected:** `C:\Users\user\.config\opencode\opencode.jsonc` (permission added), this report, and the memory handoff. **No changes to** `.env`, credentials, providers/models, browser/profiles, Edge, production repository, or existing tests. No commits or pushes. The OpenCode server was restarted (authorized) to apply the permission change.