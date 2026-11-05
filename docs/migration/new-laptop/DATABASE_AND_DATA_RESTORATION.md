# Database and Data Restoration

## F&O databases
| Database | Source (backup) | Size | Integrity |
|---|---|---|---|
| prod_paper_trading.db | databases/prod_paper_trading.db | 125 MB | ok |
| prod_gui_paper_trading.db | databases/prod_gui_paper_trading.db | 4 KB | ok |
| dev_sefre_job_audit.db | databases/dev_sefre_job_audit.db | 60 KB | ok |
| dev_sefre_events.db | databases/dev_sefre_events.db | 32 KB | ok |

## Restore command (SQLite online backup)
```powershell
python -c "import sqlite3; src='backup/databases/prod_paper_trading.db'; dst='data/paper_trading.db'; c=sqlite3.connect(dst); b=sqlite3.connect(src); b.backup(c); c.commit(); c.close(); b.close()"
```

## Integrity check
```powershell
python -c "import sqlite3; c=sqlite3.connect('data/paper_trading.db'); print(c.execute('PRAGMA integrity_check').fetchone()[0]); c.close()"
```

## Paper state
- Restore `paper_state/` directory from backup.
- Contains safety latch (do NOT clear without operator review).

## Historical data
- Reports, evidence, artifacts: restore from backup (optional but recommended).

## Essential vs optional
- Essential: paper_trading.db, paper_state/, .env (template), credential store.
- Optional: reports/, artifacts/, historical datasets, logs.