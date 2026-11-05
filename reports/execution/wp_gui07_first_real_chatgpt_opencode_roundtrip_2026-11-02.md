# WP-GUI07 — First Supervised End-to-End ChatGPT ↔ OpenCode Round Trip

**Date:** 2026-11-02
**Repository:** `C:\Vijay_GitHub\opencode-automation-controller`

## 1. Repository baseline

- Branch: `master` (no commits)
- HEAD: none
- Working tree: untracked project files and `.venv`.

## 2. Existing components reused

- Playwright Edge adapter, conversation identity verification, task extraction, result submission.
- TaskController, approval binding, duplicate protection, persistence/recovery.
- OpenCodeAdapter with optional model selection.

## 3. Marker protocol

Supported markers:
- `[OPENCODE_TASK_START]` ... `[OPENCODE_TASK_END]` (preferred)
- `<!-- OPENCODE_TASK -->` ... `<!-- /OPENCODE_TASK -->` (legacy)
- Fenced `OPENCODE_TASK` block (fallback)

Rules: exactly one start and one end marker; complete content preserved; duplicate/incomplete markers rejected.

## 4. Browser setup instructions

1. Ensure Playwright installed in `.venv`.
2. Start controller: `PYTHONPATH=src python -m opencode_bridge.operator_cli --conversation-url <URL> --profile-dir <PROFILE_DIR> --model-provider opencode --model-id beam-free`
3. Launch visible Edge with persistent profile; sign in to ChatGPT manually if needed.
4. Verify conversation identity via controller output.

## 5. Exact manual actions required

- Sign in to ChatGPT.
- Set conversation URL.
- Create a marked task in ChatGPT using the agreed marker.
- Approve the extracted task when prompted.
- Verify result appears in the same conversation.

## 6. OpenCode model used for test

- `opencode/beam-free` (optional model param), default unchanged.

## 7. Genuine execution evidence

- WP-GUI06 demonstrated genuine assistant response from `opencode/beam-free` summarizing `config.py`.
- No files modified.

## 8. Conversation identity verification

- `verify_conversation()` compares current URL to expected; mismatch pauses.
- run_one_cycle navigates and verifies before extraction.

## 9. Visible result-submission evidence

- Not yet demonstrated. `return_result_to_chatgpt()` verifies submit and persists status; manual verification pending.

## 10. Test counts and commands

- `PYTHONPATH=src python -m pytest -q` -> 32 passed, 1 skipped, 1 warning
- Real Edge test in venv -> 1 passed

## 11. Remaining blockers

- Manual ChatGPT sign-in and marked task creation.
- Visible result submission verification.
- Full round trip not yet demonstrated.

## 12. Final Git status

- No commits or pushes.
- Working tree: untracked project files and `.venv`.