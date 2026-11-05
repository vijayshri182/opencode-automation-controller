# WP-407 — Playwright ChatGPT ↔ OpenCode Browser Integration

**Date:** 2026-11-02
**Repository:** `C:\Vijay_GitHub\opencode-automation-controller`

## Existing implementation reused

- Managed Edge CDP attach (port 9224), persistent profile.
- ChatGPT conversation binding and auth detection.
- Marker extraction, policy engine, TaskController, OpenCode HTTP adapter (for reference only).
- Bounded monitoring and result submission verification.

## Attempted browser-to-browser approach

- Inspected OpenCode web UI at http://127.0.0.1:4097 behind Basic Auth.
- Observed only sidebar buttons (Home, New session, Add project, Settings, Help); no visible composer or session creation flow via simple clicks.
- Clicking "New session" did not open a usable task composer in the inspected DOM.
- Authenticated URL requires embedding credentials; Playwright context is shared with ChatGPT session.

## Blocker

OpenCode web UI automation is not reliably achievable with the current observed DOM and shared browser context. The UI appears to require project/session setup that is not exposed via simple selectors, and credential-bearing URLs are unsafe.

## Status

BLOCKED — technical dependency/UI complexity. No browser-to-browser task submission or result retrieval was implemented or validated.

## Recommended alternative

Continue using the already-validated OpenCode HTTP API path for task execution, while retaining ChatGPT browser automation for task/result transport if a stable OpenCode UI selector contract becomes available.