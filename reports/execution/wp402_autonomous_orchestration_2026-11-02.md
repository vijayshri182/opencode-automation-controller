# WP-402 — Autonomous ChatGPT ↔ OpenCode Task Orchestration

**Date:** 2026-11-02
**Repository:** `C:\Vijay_GitHub\opencode-automation-controller`

## Architecture

- `policy.py`: TaskPolicy (AUTO_APPROVE/REQUIRES_APPROVAL/BLOCKED) with keyword classification; default uncertain -> requires approval.
- `autonomous.py`: AutonomousOrchestrator.process_one_cycle() reuses existing controller/browser; applies policy; auto-executes only read-only tasks; requires approval for modifications; blocks dangerous tasks; delivers results with verification.
- status_summary() aggregates task states.

## Files changed

- src/opencode_bridge/policy.py (new)
- src/opencode_bridge/autonomous.py (new)
- tests/test_autonomous_policy.py (new)

## Tests

- 44 passed, 1 warning (full suite with venv site-packages)

## Policy matrix

- Auto: inspect/read/analyse/report/diagnose/test/docs
- Requires approval: modify/change/edit/write/install/upgrade/terminate/restart/submit/send/deploy/release (unless read-only)
- Blocked: password/secret/token/credential/live trade/deploy/production/commit/push/delete/rm -rf/format disk/bypass auth/disable auth

## Automation coverage

- Simulated/mock: duplicate detection, policy classification, auto execution, approval gating, result delivery verified in tests.
- Live: not performed (requires marked task + approval).

## Remaining manual steps

- Operator creates marked task, approves, verifies result submission.

## Safety

- No auto-chaining beyond one cycle.
- No secrets exposed.
- No commits/pushes.