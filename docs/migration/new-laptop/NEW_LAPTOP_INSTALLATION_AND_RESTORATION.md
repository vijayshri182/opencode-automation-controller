# New-Laptop Installation and Restoration — F&O Paper-Trading Application

## A. System prerequisites

- Windows 10/11 (64-bit), IST timezone (`India Standard Time`).
- Python 3.13.x (the PROD .venv uses 3.13.15).
- Git for Windows.
- PowerShell 5.1+.
- OpenCode (optional, for agent workflows): install per OpenCode docs; config at `%USERPROFILE%\.config\opencode\`.
- Disk: >= 5 GB free (repos + venv + data + reports).
- Network: access to Upstox API (api.upstox.com) and PyPI.

## B. Repository installation

```powershell
cd C:\Vijay_GitHub
git clone <DEV_REMOTE> fno-ai-paper-trading-dev
cd fno-ai-paper-trading-dev; git checkout dev/phase-13
git clone <PROD_REMOTE> fno-ai-paper-trading
cd fno-ai-paper-trading; git checkout master
```

Restore to the handover commits:
- DEV: `b55f011` (or later)
- PROD: `c8294b7` (or later)

Create venvs:
```powershell
cd C:\Vijay_GitHub\fno-ai-paper-trading
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
```
Repeat for DEV.

Copy `.env.example` to `.env` in each repo and fill in non-secret config. **Do not copy the old `.env`** (it contains stale tokens). Set `FNO_LIVE_EXECUTION_TEST_ENABLED=0`.

## C. Database and data restoration

Mandatory:
- `data/paper_trading.db` (PROD) — restore from backup using SQLite backup (verified integrity=ok). Restore command:
  ```
  python -c "import sqlite3; src='backup/databases/prod_paper_trading.db'; dst='data/paper_trading.db'; c=sqlite3.connect(dst); b=sqlite3.connect(src); b.backup(c); c.commit(); c.close(); b.close()"
  ```
- Paper state: `paper_state/` directory (restore from backup).
- Reports/evidence: `reports/` (optional but recommended for audit).

Optional: historical datasets, research artifacts.

## D. Credential setup

The central store (`C:\ProgramData\FNO-App\secrets\prod.env`) uses DPAPI and is NOT portable across machines/users.

On the new laptop:
1. Create the directory: `New-Item -ItemType Directory -Path "C:\ProgramData\FNO-App\secrets" -Force`.
2. Set env vars in `.env`: `UPSTOX_API_KEY`, `UPSTOX_API_SECRET` (client id/secret from Upstox app).
3. Run interactive authorization: `.\.venv\Scripts\python.exe scripts\authorize_market_data_credential.py`.
4. Verify: `.\.venv\Scripts\python.exe scripts\upstox_token_preflight.py --probe-only --market-data`.
5. Ensure `FNO_LIVE_EXECUTION_TEST_ENABLED=0`.

Do NOT copy the old prod.env. Do NOT enable live execution.

## E. Application services

- Paper trading: `scripts\v2_live_paper_trial.py --end 15:30` (operator-authorized only).
- Dashboard: `scripts\serve_v2_live_dashboard.py`.
- Historical intelligence dashboard: see docs.
- OpenCode automation controller: separate repo, not required for F&O restoration.
- Scheduled tasks: register from `scripts/install_v2_live_paper_trial_task.ps1` only if authorized.

## F. First-run validation

1. Git integrity: `git fsck`, `git status`.
2. Python env: `pip check`, import `fno_ai_paper_trading`.
3. Database integrity: `PRAGMA integrity_check` on restored DB.
4. Config validation: load settings, verify `FNO_LIVE_EXECUTION_TEST_ENABLED=0`.
5. Credential store: `upstox_token_preflight.py --probe-only --market-data` → READY.
6. Synthetic tests: `pytest tests/test_wp_prod_28_startup_readiness.py tests/test_wp_prod_29_startup_phase.py` → 49 passed.
7. Paper-only preflight: `upstox_token_preflight.py --probe-only --market-data` → READY.
8. Dashboard health: HTTP 200 on dashboard port.
9. Controller health (if used): separate.

Validation ≠ permission to launch a trading session.

## G. Troubleshooting

- **Stale .env token vs central store:** The runner prefers the central store when valid. If .env has a stale token, it is overridden. If both are stale, reauthorize via `authorize_market_data_credential.py`.
- **Startup gate / first-candle readiness:** The runner refuses to start before 09:20 or without a valid completed 5m candle. Check `reports/runtime/v2_startup_status.json`.
- **Startup status artifact:** Stale artifact from a previous run is not current readiness. Re-run the preflight.
- **Scheduler:** `FNO_V2_LivePaperTrial` is a one-shot task; it does not auto-restart. Check `schtasks /Query`.
- **Database restoration:** Use SQLite backup API, not file copy, to avoid WAL/SHM corruption.
- **Safety latch:** An unresolved open option leg freezes entries. Use `--recover` only after operator review. Do not clear it blindly.
- **DPAPI portability:** The encrypted store is NOT portable. Re-establish on the new laptop via fresh authorization.
