---
description: "Guide and execute the F&O new-laptop migration package step by step."
---

You are assisting with the F&O new-laptop migration. Follow these rules strictly.

1. Read `docs/migration/new-laptop/INDEX.md` first.
2. Read `docs/migration/new-laptop/MASTER_MIGRATION_GUIDE.md`.
3. Read `docs/migration/new-laptop/PHASED_MIGRATION_RUNBOOK.md`.
4. Read `docs/migration/new-laptop/PROJECT_RESTORATION_MATRIX.csv`.
5. Identify the current migration phase and completed steps from the user.
6. Inspect the new laptop's current state before changing anything.
7. Execute only the next authorized migration phase.
8. Maintain a persistent migration progress report in the target directory.
9. Verify each restored project independently.
10. Stop at credential authentication, F&O safety-latch, scheduler activation, or any operator-approval boundary.

Mandatory safety:
- Never access or print secret values.
- Never copy the old DPAPI credential store.
- Never enable live trading or live orders.
- Never clear the F&O safety latch automatically.
- Never start an F&O runner or scheduler.
- Never register or enable scheduled tasks without separate approval.
- Never push or commit unrelated project changes.
- Never delete or overwrite user data without explicit authorization.

If the OpenCode command format is not supported by the installed version, this file serves as a documented reusable prompt.