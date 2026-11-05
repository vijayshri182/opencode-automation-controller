# GitHub Repository Restoration

## Clone commands
```
cd C:\Vijay_GitHub
git clone https://github.com/vijayshri182/fno-ai-paper-trading.git
cd fno-ai-paper-trading; git checkout master
# verify HEAD = 77ed747

git clone https://github.com/vijayshri182/fno-ai-paper-trading.git fno-ai-paper-trading-dev
cd fno-ai-paper-trading-dev; git checkout dev/phase-13
# verify HEAD = 61f2edc

git clone https://github.com/vijayshri182/opencode-automation-controller.git
cd opencode-automation-controller; git checkout master
# verify HEAD = 9a6ac13
```

## Restore untracked files from backup
- Copy `paper_state/`, `reports/`, `data/`, `artifacts/` from the verified backup.
- Do NOT copy `.env` or credential store.
- Restore databases using SQLite backup API (see DATABASE_AND_DATA_RESTORATION.md).

## Branch/HEAD verification
- DEV: dev/phase-13 @ 61f2edc
- PROD: master @ 77ed747
- Controller: master @ 9a6ac13

## Notes
- eng-inova-ai remote: github.com/vijayshri182/eng-inova-ai.git, HEAD 69da25e.
- Other projects: clone from their respective remotes.
- No push/commit during restoration.