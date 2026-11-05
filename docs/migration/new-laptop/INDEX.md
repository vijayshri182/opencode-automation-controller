# New-Laptop Migration Package — Index

## Purpose
Complete migration package for moving the F&O development environment from the current Windows laptop to a new Windows laptop. Covers all projects, GitHub repos, OpenCode, automation controller, F&O restoration, databases, configuration and scheduled tasks.

## Origin
Derived from WP-HANDOVER-01 through WP-HANDOVER-04 and WP-NEW-LAPTOP-MIGRATION-01. Source backup: `D:\Workspace\_FNO_LAPTOP_HANDOVER_20261105_104453`.

## Reading order
1. `MASTER_MIGRATION_GUIDE.md`
2. `WINDOWS_ENVIRONMENT_SETUP.md`
3. `GITHUB_REPOSITORY_RESTORATION.md`
4. `DATABASE_AND_DATA_RESTORATION.md`
5. `CREDENTIAL_REESTABLISHMENT_CHECKLIST.md`
6. `OPENCODE_CONTROLLER_RESTORATION.md`
7. `FNO_DEV_PROD_RESTORATION.md`
8. `SCHEDULED_TASK_MIGRATION.md`
9. `PHASED_MIGRATION_RUNBOOK.md`
10. `NEW_LAPTOP_ACCEPTANCE_CHECKLIST.md`
11. `MIGRATION_RISK_REGISTER.md`

## Authoritative documents
- `MASTER_MIGRATION_GUIDE.md` — overall guide.
- `PHASED_MIGRATION_RUNBOOK.md` — step-by-step execution.
- `NEW_LAPTOP_ACCEPTANCE_CHECKLIST.md` — validation.

## Operator-authorization boundaries
The following require explicit operator authorization and must NOT be performed automatically:
- Credential establishment (`authorize_market_data_credential.py`).
- Scheduler registration.
- Runner launch.
- Safety-latch recovery.
- Any live trading or order execution.

## Classification
`MIGRATION_PACKAGE_READY_WITH_MANUAL_PREREQUISITES`