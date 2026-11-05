# WP-416A — Project-Scoped Chat Creation

**Date:** 2026-11-02
**Repository:** `C:\Vijay_GitHub\opencode-automation-controller`

## Implementation

- `create_project_chat(project_name)` in adapters uses `button[aria-label='New chat in {project}']` (fallback to first "New chat").
- Fail-closed: returns empty string if button missing or click fails.
- No global New chat fallback when project-specific button exists.

## Live validation

BLOCKED — the Palmistry Project page repeatedly navigates/destroys execution context during inspection, preventing stable DOM verification of the Project-specific New chat control.

## Tests

- Mock tests pass (create_project_chat mock).
- No live validation performed.

## Verdict

BLOCKED (environment instability prevents live verification). No commits or pushes.