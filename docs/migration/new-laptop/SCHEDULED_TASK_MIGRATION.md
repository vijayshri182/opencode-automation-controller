# Scheduled Task Migration

## Exported task XMLs
Location: `D:\Workspace\Windows_Automation_Migration\task_scheduler_xml\`

## F&O tasks

| Task | Purpose | Trigger | Action | Enabled |
|---|---|---|---|---|
| FNO_Upstox_ExecutionToken_Preflight | 08:45 credential/preflight | Daily 08:45 | powershell execution-token-preflight.ps1 | Yes |
| FNO_V2_LivePaperTrial | 09:05 paper trial | One-shot 09:05 | v2_live_paper_trial.py --end 15:30 | Yes |
| FNO_V2_Live_Dashboard_0900 | Dashboard | Daily 09:00 | dashboard launcher | Yes |
| FNO_Today5mReadinessMonitor | Readiness monitor | Daily 10:15 | readiness monitor | Yes |
| FNO_DailyPaperTrading_0905 | Legacy V1 | Disabled | n/a | No |
| FNO_V2_SessionDayPreflight | Session preflight | Disabled | n/a | No |

## Registration procedure (operator-authorized only)
```powershell
schtasks /Create /TN "FNO_V2_LivePaperTrial" /XML "path\to\FNO_V2_LivePaperTrial.xml"
```
Do NOT register without operator authorization. Do NOT activate scheduler during migration.

## Dependencies
- Python .venv, .env, central credential store must be configured first.
- Single-instance lock (IgnoreNew) preserved.