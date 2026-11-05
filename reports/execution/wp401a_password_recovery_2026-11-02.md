# WP-401A — OpenCode Server Password Recovery

**Date:** 2026-11-02
**Repository:** `C:\Vijay_GitHub\opencode-automation-controller`

## Sources checked

- Process/User/Machine environment: absent (length 0).
- PowerShell profiles: no password references found.
- Repository files: only documentation/source references (no credential values).
- service.json: not used by controller.

## Candidate result

No legitimate password candidate found. No guessing attempted. Server (PID 7132) untouched.

## Controller configuration

Controller correctly reads `OPENCODE_SERVER_PASSWORD` from environment. No code change needed.

## Remaining operator action

Provide the original password or start a new OpenCode server on a different port with a known password. Do not expose the password.