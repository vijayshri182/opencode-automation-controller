# Master Migration Guide — F&O Development Workspace

## Overview
Complete migration package for moving the F&O development environment from the current Windows laptop to a new Windows laptop. Covers all projects under C:\Vijay_GitHub, GitHub repositories, OpenCode, automation controller, F&O restoration, databases, configuration and scheduled tasks.

## Authoritative sources
- Primary workspace backup: D:\Workspace\Vijay_GitHub
- Dedicated F&O backup: D:\Workspace\_FNO_LAPTOP_HANDOVER_20261105_104453
- GitHub: https://github.com/vijayshri182
- Installation guide: docs/HANDOVER/NEW_LAPTOP_INSTALLATION_AND_RESTORATION.md (in both F&O repos)

## Total projects covered
16 Git repositories + ~23 non-Git projects. See PROJECT_RESTORATION_MATRIX.csv.

## Classification
MIGRATION_PACKAGE_READY_WITH_MANUAL_PREREQUISITES

## Key constraints
- No live trading or order execution.
- No credential transfer (DPAPI not portable).
- No scheduler activation without operator authorization.
- No runner launch during migration.

## Reading order
1. WINDOWS_ENVIRONMENT_SETUP.md
2. GITHUB_REPOSITORY_RESTORATION.md
3. DATABASE_AND_DATA_RESTORATION.md
4. CREDENTIAL_REESTABLISHMENT_CHECKLIST.md
5. OPENCODE_CONTROLLER_RESTORATION.md
6. FNO_DEV_PROD_RESTORATION.md
7. SCHEDULED_TASK_MIGRATION.md
8. PHASED_MIGRATION_RUNBOOK.md
9. NEW_LAPTOP_ACCEPTANCE_CHECKLIST.md
10. MIGRATION_RISK_REGISTER.md