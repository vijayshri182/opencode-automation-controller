# WP-3 — Operational Acceptance Readiness

**Date:** 2026-11-02
**Repository:** `C:\Vijay_GitHub\opencode-automation-controller`

## 1. Existing implementation verification

Verified components:
- OpenCodeAdapter health/session/task/result.
- TaskController lifecycle, approval binding, duplicate protection.
- PlaywrightEdgeAdapter, conversation identity verification, task extraction, result submission verification.
- Operator CLI supervised cycle.
- State persistence and recovery.

## 2. Exact operator instructions

1. Start OpenCode securely:
   ```powershell
   $env:OPENCODE_SERVER_PASSWORD = "<strong-local-password>"
   opencode serve --hostname 127.0.0.1 --port 4096
   ```
2. Start controller:
   ```powershell
   cd C:\Vijay_GitHub\opencode-automation-controller
   $env:PYTHONPATH = "src"
   $env:OPENCODE_BASE_URL = "http://127.0.0.1:4096"
   $env:OPENCODE_SERVER_PASSWORD = "<strong-local-password>"
   $env:OPENCODE_MOCK = "0"
   python -m opencode_bridge.operator_cli --conversation-url "<CHATGPT_URL>" --profile-dir "C:\Vijay_GitHub\opencode-automation-controller\.edge-profile" --model-provider opencode --model-id beam-free
   ```
3. Launch Edge (handled by controller) and sign in to ChatGPT manually if prompted.
4. Verify conversation identity in controller output.
5. Ensure ChatGPT response contains:
   ```
   [OPENCODE_TASK_START]
   Ask OpenCode to inspect the repository README and return a three-point summary without modifying any files.
   [OPENCODE_TASK_END]
   ```
6. Approve task when prompted.
7. Wait for OpenCode execution and result submission.
8. Verify the submitted result appears in the same ChatGPT conversation.

## 3. Test task and expected result

Task: "Ask OpenCode to inspect the repository README and return a three-point summary without modifying any files."
Expected: concise three-point summary of README; no file modifications.

## 4. Observable checkpoints

- OpenCode health PASS.
- Browser start and conversation URL match.
- Task extraction preview printed.
- Approval prompt.
- Task status completed.
- Result submission verified (controller prints submitted=True, verified=True).
- State file updated.

## 5. Failure and recovery instructions

- Auth expiry: pause, sign in, rerun.
- Conversation mismatch: stop, verify URL.
- OpenCode unavailable: check server, retry.
- Uncertain submission: do not resend; inspect conversation manually.
- Timeout: task marked failed; retry with approval.

## 6. Evidence required for acceptance

- Controller logs/output showing health, extraction, approval, execution status, submission verified.
- Screenshot or observation of result in ChatGPT conversation.
- Git status unchanged (except .venv/state).

## 7. Outstanding operator actions

- Perform manual sign-in and marked-task round trip.
- Capture evidence.

## 8. Final readiness classification

READY FOR OPERATOR ACCEPTANCE (implementation complete; live round trip pending manual execution).