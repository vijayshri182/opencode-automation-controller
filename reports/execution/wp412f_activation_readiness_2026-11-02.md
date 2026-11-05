# WP-412F — Project Chat Activation Readiness

**Date:** 2026-11-02
**Repository:** `C:\Vijay_GitHub\opencode-automation-controller`

## Implementation verification

- `create_project_chat(project_name)` targets `button[aria-label='New chat in {project}']` with fallback to first "New chat".
- Returns resulting conversation URL.
- Controller persists binding via `set_conversation_url`.
- Polling uses that conversation URL.
- Dedup via idempotency key/content hash.
- User-authored marker required; assistant messages not eligible.
- Fails closed (returns empty URL on failure).

## Worker status

- PID 31528: running.
- Binding: previous conversation (https://chatgpt.com/c/6ae8462d-8234-83ee-add5-6d72dabaac15) from startup.
- Worker code predates latest marker support; may not detect new markers without restart.

## State preservation and duplicate risks

- Restarting worker could lose in-memory state but DB persists tasks.
- Duplicate execution risk low (idempotency key).
- Restart requires operator approval.

## Exact activation sequence (operator-approved)

1. Verify ChatGPT signed in on managed Edge (port 9224).
2. Call `create_project_chat("Palmistry Project")` (operator-triggered).
3. Capture and validate resulting conversation URL.
4. Persist binding via `set_conversation_url`.
5. Restart worker with new `--conversation-url` (requires authorization).
6. Verify worker monitors only new conversation.

## Explicit operator approval points

- Step 2: create new project chat.
- Step 5: worker restart.

## Evidence required for acceptance

- Conversation URL and ID.
- Worker polling only that conversation.
- Marked user task detected.
- Policy authorization.
- OpenCode execution ID and model.
- Result submission and receiving-side verification.

## Verdict

PARTIAL (implementation ready; live activation pending operator approval).