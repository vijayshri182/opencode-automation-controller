# WP-420A — Chromium No-Sandbox Investigation

**Date:** 2026-11-02
**Repository:** `C:\Vijay_GitHub\opencode-automation-controller`

## Source of `--no-sandbox`

- No application code in `src/` or `scripts/` explicitly adds `--no-sandbox`.
- The flag originates in Playwright's launcher: `playwright/driver/.../coreBundle.js` pushes `--no-sandbox` into Chrome arguments **unless** `options.chromiumSandbox === true`.
- Concretely, `PlaywrightEdgeAdapter.start()` in `src/opencode_bridge/browser_automation.py` called `launch_persistent_context(..., executable_path=edge_path, headless=self.headless)` without setting `chromium_sandbox`, so Playwright defaulted to `--no-sandbox`.
- `ManagedEdgeLauncher` (subprocess-based) does not add `--no-sandbox`.

## Is it required?

No. The sandbox can be enabled by passing `chromium_sandbox=True` to `launch_persistent_context`. Verified live: a sandboxed Edge launch succeeded and loaded a page (`Example Domain`).

## Correction applied

- `PlaywrightEdgeAdapter.start()`: added `chromium_sandbox=True` to `launch_persistent_context`.
- No changes to `.env`, credentials, or other browser settings.
- `ManagedEdgeLauncher` unchanged (already sandboxed by default).

## Active session

- The correction is in code only; the active browser session was not restarted and no session migration was performed. The next Playwright launch will use the sandbox.

## Tests

- `tests/test_browser_sandbox.py`: 2 passed
  - `test_playwright_launch_uses_chromium_sandbox`: verifies `chromium_sandbox=True` is passed and `--no-sandbox` is not in args.
  - `test_managed_edge_launcher_does_not_add_no_sandbox`: verifies subprocess args contain no `--no-sandbox`.

## Verdict

PASS (configuration corrected; sandbox enabled for future launches; no restart performed).