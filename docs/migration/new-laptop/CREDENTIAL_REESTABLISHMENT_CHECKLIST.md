# Credential Reestablishment Checklist

## Central credential store
- Path: `C:\ProgramData\FNO-App\secrets\prod.env`
- DPAPI-encrypted (CurrentUser scope — NOT portable across machines/users).
- Application identity bound via `UPSTOX_API_KEY`.

## Steps (operator-interactive)
1. Create directory: `New-Item -ItemType Directory -Path "C:\ProgramData\FNO-App\secrets" -Force`.
2. Set in `.env`: `UPSTOX_API_KEY=<client_id>`, `UPSTOX_API_SECRET=<client_secret>`.
3. Run: `.\.venv\Scripts\python.exe scripts\authorize_market_data_credential.py`.
   - Opens browser for Upstox OAuth (MARKET_DATA only, no execution permissions).
   - Persists encrypted token to central store.
   - Regenerates preflight artifact.
4. Verify: `.\.venv\Scripts\python.exe scripts\upstox_token_preflight.py --probe-only --market-data` → READY.
5. Confirm `FNO_LIVE_EXECUTION_TEST_ENABLED=0`.

## Boundaries
- Do NOT copy the old DPAPI store (not portable).
- Do NOT use execution credentials (UPSTOX_ACCESS_TOKEN).
- Do NOT enable live execution.
- Market-data authorization is separate from execution authorization.
- Token expires at 03:30 IST next day; reauthorize before 08:45 preflight if expired.