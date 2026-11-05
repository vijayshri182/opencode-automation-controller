# Backup Manifest — F&O Laptop Handover

- Backup directory: `C:\Vijay_GitHub\_FNO_LAPTOP_HANDOVER_20261105_104453`
- Created: 2026-11-05
- Source: `C:\Vijay_GitHub\fno-ai-paper-trading` (PROD) + `C:\Vijay_GitHub\fno-ai-paper-trading-dev` (DEV)

## Databases backed up (SQLite online backup, integrity verified)

| File | Size (bytes) | SHA-256 (prefix) | Integrity |
|---|---|---|---|
| databases/prod_paper_trading.db | 125444096 | 3f3959d8a65f1bb1 | ok |
| databases/prod_gui_paper_trading.db | 4096 | 867839bc25b30558 | ok |
| databases/dev_sefre_job_audit.db | 61440 | 6f13422cc6ce90f9 | ok |
| databases/dev_sefre_events.db | 32768 | 90a4751188da7144 | ok |

## Directories backed up

- `fno-ai-paper-trading/paper_state/` — paper broker state, safety latch, positions
- `fno-ai-paper-trading/reports/` — all reports, evidence, runtime logs
- `fno-ai-paper-trading/data/` — datasets (excluding .db already above)
- `fno-ai-paper-trading/artifacts/` — capture artifacts
- `fno-ai-paper-trading-dev/paper_state/`, `reports/`, `data/`, `artifacts/`
- `fno-ai-paper-trading/scripts/` — all scripts
- `scheduled_tasks/` — exported scheduler XML definitions
- `opencode_config/` — OpenCode config (no secrets)
- `docs/` — installation doc

## Credentials

- Central credential store (`C:\ProgramData\FNO-App\secrets\prod.env`) was NOT copied (DPAPI-encrypted, not portable).
- Metadata recorded in `CREDENTIAL_STORE_METADATA.txt`.
- New laptop must establish its own store via `scripts/authorize_market_data_credential.py`.
- `.env` files were NOT backed up (contain secrets). `.env.example` templates were backed up.

## Excluded

- `.venv/` (reinstall on new laptop)
- `.git/` (clone from remote)
- `node_modules/`, `.mypy_cache/`, `__pycache__/`
- `gui/data/paper_trading.db` (backed up separately as prod_gui_paper_trading.db)
- `opencode-automation-controller` (separate project, not required for F&O restoration)
- AI career agent databases (separate project)

## Backup size

- Total: ~819 MB, 3778 files.
- Database backups: ~120 MB.