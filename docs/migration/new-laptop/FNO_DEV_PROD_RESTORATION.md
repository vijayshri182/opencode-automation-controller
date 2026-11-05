# F&O DEV and PROD Restoration

## Python
- PROD: Python 3.13.x
- DEV: Python 3.13.x

## Setup
```
cd C:\Vijay_GitHub\fno-ai-paper-trading
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
```
Repeat for DEV.

## Database restoration
- Restore `paper_trading.db` from backup using SQLite backup API (not file copy).
- Restore `paper_state/` directory.
- Verify: `PRAGMA integrity_check` → ok.

## Configuration
- Copy `.env.example` to `.env`. Fill non-secret config.
- Set `FNO_LIVE_EXECUTION_TEST_ENABLED=0`.
- Set `FNO_CREDENTIAL_STORE_BOOTSTRAP=1` (PROD) if using central store.

## Credential store
- Create `C:\ProgramData\FNO-App\secrets\` directory.
- Run `.\.venv\Scripts\python.exe scripts\authorize_market_data_credential.py` (interactive).
- Verify: `.\.venv\Scripts\python.exe scripts\upstox_token_preflight.py --probe-only --market-data` → READY.

## Tests
```
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe -m pytest tests/test_wp_prod_28_startup_readiness.py tests/test_wp_prod_29_startup_phase.py -q
# Expected: 49 passed (PROD), 49 passed (DEV)
```

## Safety invariants (verify)
- `ExecutionMode.PAPER.can_write_orders == False`
- `PaperBroker(is_live=False)`
- `FNO_LIVE_EXECUTION_TEST_ENABLED=0`

## Safety latch
- Do NOT clear the unresolved open option leg without operator review.
- Documented in WP-PROD-39. Requires `--recover --recover-reason --recover-by`.

## Do NOT
- Start runner or scheduler.
- Enable live execution.
- Clear safety latch without review.