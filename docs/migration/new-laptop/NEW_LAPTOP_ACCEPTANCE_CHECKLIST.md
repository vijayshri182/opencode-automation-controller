# New-Laptop Acceptance Checklist

## Git and repository integrity
- [ ] Both F&O repos cloned at correct commits (DEV 61f2edc, PROD 77ed747)
- [ ] `git fsck` passes
- [ ] `git status` shows only expected untracked files

## Python environment and dependencies
- [ ] .venv created with Python 3.13
- [ ] `pip check` passes
- [ ] `import fno_ai_paper_trading` succeeds

## Database integrity
- [ ] Restored DBs pass `PRAGMA integrity_check`
- [ ] Row counts match backup

## Configuration validation
- [ ] `.env` created from template
- [ ] `FNO_LIVE_EXECUTION_TEST_ENABLED=0`
- [ ] No secrets in committed files

## Credential-store validation
- [ ] Central store directory created
- [ ] `authorize_market_data_credential.py` completed (interactive)
- [ ] Preflight `--probe-only --market-data` → READY
- [ ] Identity bound, DPAPI encrypted

## Synthetic/offline DEV tests
- [ ] 49 startup tests pass
- [ ] Safety invariants verified

## PROD paper-only preflight
- [ ] 49 startup tests pass
- [ ] 68 credential/safety tests pass (2 pre-existing env differences documented)
- [ ] py_compile clean

## Dashboard health
- [ ] Dashboard starts and returns HTTP 200
- [ ] Dashboard is read-only (no launch capability)

## Controller health (if required)
- [ ] Controller starts, health endpoint returns 200
- [ ] MCP tool discovery works

## Safety
- [ ] No runner or scheduler started
- [ ] No live execution enabled
- [ ] Safety latch reviewed before any session