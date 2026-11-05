# WP-2 — Complete End-to-End ChatGPT ↔ OpenCode Workflow

**Date:** 2026-11-02
**Repository:** `C:\Vijay_GitHub\opencode-automation-controller`

## 1. Authentication status

- Edge uses a persistent local profile; sign-in is manual.
- No passwords/cookies/tokens are extracted or logged.
- Authentication failures pause the workflow.

## 2. Marked-task lifecycle

- Marker protocol: `[OPENCODE_TASK_START]` ... `[OPENCODE_TASK_END]` (preferred), legacy HTML markers, fenced fallback.
- Extract only between markers; duplicate/incomplete markers rejected.
- Task bound to content hash and workspace; approval required.
- Submission to OpenCode uses existing adapter; duplicate protection via idempotency key.
- Status tracked through TaskController; timeout/cancellation handled.

## 3. Result submission and verification

- Result message includes task ID, status, final output, report, tests, git status, blockers.
- `submit_message` clicks send; `verify_submitted` checks message presence in page.
- If not verified, status becomes `submission_uncertain` and no success claimed.
- No automatic resend.

## 4. Tests

- Full suite: 34 passed, 1 skipped, 1 warning.
- Real Edge launch: 1 passed (venv).
- Live OpenCode integration: 2 passed.

## 5. Remaining operator actions

- Sign in to ChatGPT in persistent Edge profile.
- Set conversation URL.
- Create marked task.
- Run supervised cycle; approve; verify result submission.

## 6. Security

- Loopback only, no secret logging, no autonomous chaining, path allowlist documented as non-sandbox.