# Offsite Backup Verification Report

- Source: `C:\Vijay_GitHub\_FNO_LAPTOP_HANDOVER_20261105_104453`
- Destination: `D:\Workspace\_FNO_LAPTOP_HANDOVER_20261105_104453`
- Date: 2026-11-05
- Method: robocopy /E (recursive, including empty dirs), then SHA-256 per-file comparison.

## Results

- Source file count: 3784
- Destination file count: 3784
- Source total size: 858,518,822 bytes
- Destination total size: 858,518,822 bytes
- Files checked (SHA-256): 3784
- Mismatches: 0
- Missing files: 0

## Database verification (destination)

| Database | Integrity |
|---|---|
| databases/prod_paper_trading.db | ok |
| databases/prod_gui_paper_trading.db | ok |
| databases/dev_sefre_job_audit.db | ok |
| databases/dev_sefre_events.db | ok |

## Credentials

- The central DPAPI credential store was NOT copied (not portable, DPAPI CurrentUser-scoped).
- Metadata recorded in `CREDENTIAL_STORE_METADATA.txt`.
- No plaintext secrets, tokens, or private keys were copied.

## Exceptions

- None. The destination copy is complete and byte-identical to the source.

## Conclusion

The independent destination copy has been verified complete and byte-identical. The source backup remains unchanged.