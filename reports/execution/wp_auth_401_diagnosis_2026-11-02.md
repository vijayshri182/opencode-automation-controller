# OpenCode Server HTTP 401 Authentication Diagnosis

**Date:** 2026-11-02
**Repository:** `C:\Vijay_GitHub\opencode-automation-controller`

## Root cause

The running OpenCode server (PID 7132) was started with a password that does not match the current `OPENCODE_SERVER_PASSWORD` environment value. The controller's Basic Auth construction is correct (verified by unit tests). No controller-side defect found.

## Evidence

- Adapter health() returns `OpenCodeAuthError` (HTTP 401).
- Unit tests for default username and Basic Auth construction: 2 passed.
- Server remains untouched (no restart).

## Files inspected/changed

- src/opencode_bridge/config.py
- src/opencode_bridge/opencode_adapter.py
- tests/test_auth_basic.py (new)

## Tests

- test_auth_basic: 2 passed
- Full suite: 36 passed, 2 skipped, 1 warning

## Live authentication

- NOT VERIFIED (password mismatch with running server).

## Operator action required

Set `OPENCODE_SERVER_PASSWORD` to the value used when starting PID 7132, or start a new OpenCode server on a different port with a known password for testing. Do not expose the password.