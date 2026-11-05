# Phased Migration Runbook

## Phase 1: Hardware and Windows readiness
- Install Windows updates, set IST timezone.
- Admin required: yes (timezone, Windows features).

## Phase 2: Development tools
- Install Python 3.13, Git, Node.js, VS Code, PowerShell 5.1+.
- Set execution policy: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`.
- Admin required: yes (installers).

## Phase 3: GitHub project cloning
- Clone repos, checkout branches/commits.
- Commands: see GITHUB_REPOSITORY_RESTORATION.md.
- Admin required: no. User interaction: GitHub auth.

## Phase 4: Local workspace restoration
- Create venvs, install deps.
- Restore databases, paper_state, reports.
- Admin required: no.

## Phase 5: Runtime and dependency setup
- Verify imports, run synthetic tests.
- Admin required: no.

## Phase 6: Database and persistent-data restoration
- Restore DBs via SQLite backup API.
- Verify integrity.
- Admin required: no.

## Phase 7: OpenCode setup
- Install OpenCode, configure, verify health.
- Admin required: no.

## Phase 8: Controller setup
- Clone controller, create venv, install deps.
- Configure .env, verify health.
- Admin required: no.

## Phase 9: Individual project validation
- Run tests per project.
- Admin required: no.

## Phase 10: F&O DEV validation
- Run 49 synthetic tests.
- Verify config, credential store (probe-only).

## Phase 11: F&O PROD read-only validation
- Run 49 startup tests + 68 credential/safety tests.
- Verify preflight (probe-only).

## Phase 12: Credential-store re-establishment
- Create directory, run authorize_market_data_credential.py (interactive).
- Verify preflight → READY.
- Admin required: no (but user interaction required).

## Phase 13: Scheduled-task registration (after operator approval)
- Register tasks from XML definitions.
- Admin required: yes (schtasks).

## Phase 14: Final migration acceptance
- Run all validation steps.
- Verify safety invariants.
- Confirm no runner/scheduler started.
- Admin required: no.