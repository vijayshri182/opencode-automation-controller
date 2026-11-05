# Migration Risk Register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| DPAPI store not portable | Certain | High | Re-establish via interactive authorization on new laptop |
| Unresolved safety latch (open option leg) | Certain | High | Operator review before any session; do not auto-recover |
| Scheduler tasks not registered | Certain | Medium | Register from exported XML after operator approval |
| .env secrets not transferred | By design | Medium | Recreate from template, fill manually |
| Credential expiry during migration | Possible | Medium | Reauthorize before 08:45 preflight |
| PROD test failures (intrabar monitor) | Known | Low | Pre-existing env difference, not a regression |
| Controller not backed up | Known | Medium | Commit/copy controller before handover |
| gui/ app not committed | Known | Low | Separate reviewed commit needed |
| OpenCode config not portable | Possible | Low | Reinstall OpenCode, copy config templates |