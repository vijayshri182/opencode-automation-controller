# Security Boundaries and Limitations

- All listeners bind 127.0.0.1 only.
- Authorized workspace: C:\Vijay_GitHub\fno-ai-paper-trading-dev only.
- PROD repository is never authorized.
- No commit, push, deploy, release.
- No credentials, tokens or .env reading.
- No Upstox API or live orders.
- No trading-session control.
- No generated strategy-candidate execution (RF16 NO-GO).
- Supervised mode only; continuous chaining disabled.
- A path allowlist is not an OS sandbox; it does not isolate arbitrary code execution. OpenCode runs with the user's OS permissions. Treat as a convenience boundary, not a security boundary.