# Handover Checklist

## Pre-migration (completed)
- [x] Git audit of DEV and PROD
- [x] Backup of databases (4 SQLite, integrity verified)
- [x] Backup of paper_state, reports, data, artifacts, scripts, scheduled tasks, OpenCode config
- [x] Backup of .env.example templates (not .env)
- [x] Credential store metadata recorded (no secrets)
- [x] Git commits in DEV (3) and PROD (2)
- [x] Secret scan clean
- [x] Installation/restoration document created
- [x] Handover inventory created

## Remaining manual actions on new laptop
- [ ] Clone DEV and PROD repos; checkout correct branches/commits
- [ ] Create .venv; install requirements
- [ ] Restore databases from backup (verify integrity)
- [ ] Restore paper_state, reports, artifacts
- [ ] Create .env from .env.example (fill non-secret config)
- [ ] Establish central credential store (fresh MARKET_DATA authorization)
- [ ] Verify FNO_LIVE_EXECUTION_TEST_ENABLED=0
- [ ] Run synthetic tests (49 passed expected)
- [ ] Run preflight (probe-only --market-data) → READY
- [ ] Resolve outstanding safety latch (unresolved open option leg) before any session
- [ ] Do NOT start runner/scheduler without operator authorization

## Outstanding issues
- Unresolved open option leg from prior session (safety latch). Requires operator review.
- gui/ app not committed (separate reviewed commit needed).
- OpenCode automation controller not committed (separate project).