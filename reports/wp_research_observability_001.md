# WP-RESEARCH-OBSERVABILITY-001 — Existing OpenCode HTTP Response and Research Execution Evidence Audit

Date: 2026-11-04
Repository: `C:\Vijay_GitHub\opencode-automation-controller` (branch `master`, no commits; all files untracked)
Mode: **read-only audit**. No new research task submitted, no services started/stopped/restarted, no credentials
accessed or revealed, no source/config/db/log modified, no commit/push.

---

## 1. Current observability architecture

The controller is a stdlib `http.server` MCP (Streamable HTTP / JSON-RPC 2.0) wrapper around a
`MissionOrchestrator`. OpenCode communication goes through `src/opencode_bridge/opencode_adapter.py`
(`OpenCodeAdapter`, urllib-based). Research tasks are persisted in SQLite (`research_tasks` table in
`bridge.db`) but **no execution engine runs them** — they remain `pending`.

Data flow for a research task:
1. MCP client → `POST /mcp` → `submit_research_task` → row inserted into `research_tasks` (status
   `pending`, `session_id=NULL`, `result_json=NULL`).
2. `get_research_task_status` / `get_research_task_result` read the row back.
3. There is no code path that transitions a research task to `running`/`completed`/`failed`, creates an
   OpenCode session, or stores tool output. The `update_research_task` DB helper exists but is never
   called for research execution.

Controller → OpenCode HTTP (exact endpoints called by `OpenCodeAdapter`):
- `GET  /global/health`
- `POST /session` (body `{"title":..., "agent":...}`, query `directory=...`)
- `POST /session/{session_id}/prompt_async` (body `{"parts":[{"type":"text","text":...}], "model":{...},
  "agent":..., "tools":{...}}`, query `directory=...`)
- `GET  /session/{session_id}/message?limit=N&directory=...`
- `POST /session/{session_id}/abort` (query `directory=...`)

Auth: OpenCode uses HTTP Basic (`Authorization: Basic base64(username:password)`); controller MCP uses
`Authorization: Bearer <MCP_AUTH_TOKEN>`.

---

## 2. Actual request/response capture status

**Not captured.** The adapter (`_request`) parses the response in memory and returns parsed JSON; raw
request bodies and raw response bodies are never persisted. Only these are retained:

- `OpenCodeAdapter._request`: on `HTTPError`, reads the error body and truncates to **300 chars**
  (`body_text[:300]`) into `OpenCodeAuthError`/`OpenCodeAPIError` message text — and that message is
  only logged at debug level / surfaced as an exception, not stored unless a caller persists `str(exc)`.
- Successful responses: parsed JSON returned to caller; caller persists only extracted fields
  (e.g. `execution_output` text, `error` string, tokens are read but the adapter does not return them
  to the DB layer in the research path).

So: **no raw HTTP request/response is retrievable after the fact.** Only derived, truncated fields.

---

## 3. Existing log and artifact locations

| Artifact | Path | Contents |
|---|---|---|
| Controller DB (live) | `C:\Vijay_GitHub\fno-ai-paper-trading-dev\.opencode_bridge\bridge.db` | SQLite; tables incl. `research_tasks`, `missions`, `audit_events`, `executions`, `tasks`, etc. |
| Controller DB (repo-root copy) | `C:\Vijay_GitHub\opencode-automation-controller\orch.db` | Same schema; appears to be a snapshot/copy (research_tasks rows=0 here vs 1 in bridge.db). |
| Controller logs | **none persisted** | `logging.getLogger(...)` is used but no handler/FileHandler is configured → output goes to the process's stdout/stderr only (captured by the launching terminal, if any). |
| OpenCode instance logs | `reports/evidence/test_research_isolation_002*/serve.err.log`, `serve.out.log` | Only present when an instance was launched with `--print-logs` (research preflight runs). Complete stream-error lines including `AI_APICallError` text. |
| Raw HTTP traces | none | Not captured anywhere. |
| JSON artifacts (research) | none | `result_json` column exists but is NULL for the only research task. |

---

## 4. Exact commands for inspecting outputs

All commands below are read-only. Replace nothing; the token is read from `.env` at runtime and never
printed.

### A. Controller health
```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8799/health"
```
Returns `{"ok": true, "service": "mcp_server"}`.

### B. MCP JSON-RPC (authenticated) — list tools
```powershell
$token = ((Get-Content C:\Vijay_GitHub\opencode-automation-controller\.env |
           Where-Object { $_ -match '^MCP_AUTH_TOKEN=' }) -replace '^MCP_AUTH_TOKEN=','').Trim()
$h = @{ Authorization = "Bearer $token"; "Content-Type" = "application/json" }
$init = '{"jsonrpc":"2.0","id":0,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"audit","version":"1"}}}'
Invoke-RestMethod -Method POST -Uri "http://127.0.0.1:8799/mcp" -Headers $h -Body $init | Out-Null
$notif = '{"jsonrpc":"2.0","method":"notifications/initialized","params":{}}'
try { Invoke-RestMethod -Method POST -Uri "http://127.0.0.1:8799/mcp" -Headers $h -Body $notif | Out-Null } catch {}
$b = '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'
(Invoke-RestMethod -Method POST -Uri "http://127.0.0.1:8799/mcp" -Headers $h -Body $b).result.tools.name
```
Returns the 19 tool names currently exposed by the live controller. Note: the live controller (started
before WP-RESEARCH-002 code changes) does **not** expose `submit_research_task` /
`get_research_task_status` / `get_research_task_result` even though they exist on disk — a restart
(operator-gated) is required to use them.

### C. Query the persisted research task directly (SQLite, read-only)
```powershell
cd C:\Vijay_GitHub\opencode-automation-controller
.venv\Scripts\python -c "import sqlite3,json; c=sqlite3.connect(r'C:\Vijay_GitHub\fno-ai-paper-trading-dev\.opencode_bridge\bridge.db'); c.row_factory=sqlite3.Row; print(json.dumps([dict(r) for r in c.execute('SELECT * FROM research_tasks')], indent=2, default=str))"
```
Returns the row(s) with all columns including `session_id`, `result_json`, `error`.

### D. OpenCode session messages (dev server 4097, Basic auth) — example with a real session
```powershell
$pw = ((Get-Content C:\Vijay_GitHub\opencode-automation-controller\.env | Where-Object { $_ -match '^OPENCODE_SERVER_PASSWORD=' }) -replace '^OPENCODE_SERVER_PASSWORD=','').Trim(); $cred = New-Object System.Management.Automation.PSCredential("opencode", (ConvertTo-SecureString $pw -AsPlainText -Force))
Invoke-RestMethod -Uri "http://127.0.0.1:4097/session/ses_e5d80a12fffeF60OQcjjZCYEQR/message?limit=50" -Credential $cred
```
Returns the full message list (user + assistant) with parts: `text`, `step-start`, `tool` (with
`state.status`, `state.input`, `state.output`, `state.error`), token counts, cost, finish reason, model
provider/id. This is the canonical place to see actual `websearch`/`webfetch` tool invocations and
their results.

List all sessions on the dev server:
```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:4097/session" -Credential $cred
```

### E. OpenCode health
```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:4097/global/health" -Credential $cred
```

### F. Inspect OpenCode instance logs (research preflight runs)
```powershell
Get-Content C:\Vijay_GitHub\opencode-automation-controller\reports\evidence\test_research_isolation_002_flint\serve.err.log -Tail 20
```
Contains `stream error` lines with full `AI_APICallError` text and session IDs.

---

## 5. Available API endpoints

Controller (loopback, port 8799):
- `GET  /health` — health.
- `POST /mcp` — JSON-RPC 2.0: `initialize`, `notifications/initialized`, `tools/list`, `tools/call`.
  Tool names (live instance, 19): `controller_health`, `list_chatgpt_projects`, `get_chatgpt_project`,
  `set_active_chatgpt_project`, `discover_chatgpt_conversation`, `read_chatgpt_messages`,
  `get_chatgpt_observations`, `get_chatgpt_reader_state`, `get_chatgpt_observer_status`,
  `start_chatgpt_observer`, `stop_chatgpt_observer`, `acknowledge_chatgpt_message`,
  `get_unread_chatgpt_messages`, `get_chatgpt_message_history`, `get_controller_capabilities`,
  `get_task_status`, `get_execution_result`, `submit_chatgpt_task`, `approve_chatgpt_task`.
  On-disk (not live): `submit_research_task`, `get_research_task_status`, `get_research_task_result`.

OpenCode (dev, port 4097; research, port 4098 when running):
- `GET  /global/health`
- `GET  /provider` (model list incl. `opencode-go/beam-free`, `opencode/big-pickle`, etc.)
- `GET  /agent`
- `GET  /config`
- `POST /session` (create)
- `POST /session/{id}/prompt_async` (submit prompt)
- `GET  /session/{id}/message?limit=N&directory=...` (retrieve messages + parts)
- `POST /session/{id}/abort`

---

## 6. Example evidence from existing sessions/tasks

### A. Existing persisted research task (bridge.db, read-only)
```
research_id:        res-2eb40bb981db
idempotency_key:    k1
prompt:             "Search Comviva Director Product Architecture Bengaluru"
read_only:          1
timeout_seconds:    120.0
max_results:        10
status:             pending
created_at:         2026-11-03T15:08:26.165Z (epoch 1793718506.165)
started_at:         null
completed_at:       null
session_id:         null
result_json:        null
error:              null
```
**No completed or failed research task exists.** The only research task is `pending` and was never executed
(no session_id, no result, no error). This is the honest state — there is no successful research session
in the controller DB to demonstrate.

### B. Existing OpenCode session with assistant output (dev server 4097)
Session `ses_e5d80a12fffeF60OQcjjZCYEQR` (title "integration-test", model `opencode/big-pickle`) — retrieved
via `GET /session/{id}/message`:
- User part: `{"type":"text","text":"Hello world. Reply with exactly: Hello from OpenCode."}`
- Assistant part: `{"type":"text","text":"Hello from OpenCode."}` with `tokens.input=7538`,
  `tokens.output=6`, `finish="stop"`, `cost=0`.
- Additional parts: `step-start` with snapshot hash. No tool calls in this session.

This demonstrates that OpenCode session messages (including assistant text and token counts) are
retrievable **only while the OpenCode server is running** and the session exists in its store. The
controller does not persist them.

### C. Audit events (bridge.db)
```
(1, 'mcp-server', 'mission_created', 'C:\\Vijay_GitHub\\fno-ai-paper-trading-dev', 1793717300.817)
(2, 'msg-research-0c5ff62e-...', 'inbound_persisted', 'corr-research-90b20f60-...', 1793718129.986)
```

---

## 7. Missing observability capabilities

1. **No raw HTTP request/response persistence** — adapter parses in memory; only 300-char truncated
   error snippets survive, and only if a caller stores `str(exc)`.
2. **No controller log file** — `logging.getLogger` with no handler → stdout/stderr of the process only;
   not captured to disk unless the launcher redirects.
3. **Research tasks are never executed** — `update_research_task` exists but is never called for
   execution; no executor transitions `pending` → `running` → `completed/failed`; `session_id` and
   `result_json` stay NULL. Tool output is never stored.
4. **No tool-call / tool-result persistence** — websearch/webfetch inputs and outputs are not captured
   in the controller DB; only retrievable live from the OpenCode server.
5. **No OpenCode session-message persistence** — assistant messages, parts, tokens, cost are not
   stored by the controller.
6. **Running controller is stale** — the live instance (PID 33028/6492) predates WP-RESEARCH-002 and
   does not expose `submit_research_task` / `get_research_task_status` / `get_research_task_result`
   (19 tools, no research tools). On-disk code has them; a restart is required (operator-gated).
7. **No redacted request/response trace** for debugging provider errors (e.g. `AI_APICallError` text is
   only in OpenCode's `serve.err.log` when `--print-logs` is used).

---

## 8. Recommended next step

1. **Operator-gated restart** of the controller so the on-disk research tools (submit/get_status/
   get_result) become live, then submit one read-only research task and verify it transitions to
   `completed` with a populated `session_id` and `result_json`.
2. Add an **optional redacted HTTP trace** (request method/path/status, truncated body) behind a flag,
   and persist `session_id` + full message dump + tool calls into `research_tasks.result_json` (or a
   new `research_evidence` table) during execution.
3. Wire a research task **executor** (reuse `OpenCodeAdapter`) that creates a session, submits the
   prompt, polls with deadline, extracts assistant text + tool parts, and updates the row.
4. Add a controller log file (rotating FileHandler) so errors survive process restarts.
5. Keep all of the above behind the existing read-only / no-external-message safety boundaries.

---

## Final response — exact commands to see existing OpenCode HTTP response and session output immediately

1. **Controller health (no auth):**
   ```powershell
   Invoke-RestMethod -Uri "http://127.0.0.1:8799/health"
   ```

2. **OpenCode dev server health (Basic auth):**
   ```powershell
   $pw = ((Get-Content C:\Vijay_GitHub\opencode-automation-controller\.env | Where-Object { $_ -match '^OPENCODE_SERVER_PASSWORD=' }) -replace '^OPENCODE_SERVER_PASSWORD=','').Trim(); $cred = New-Object System.Management.Automation.PSCredential("opencode", (ConvertTo-SecureString $pw -AsPlainText -Force))
   Invoke-RestMethod -Uri "http://127.0.0.1:4097/global/health" -Credential $cred
   ```

3. **OpenCode session messages (actual HTTP response body with assistant text + parts + tokens):**
   ```powershell
   $pw = ((Get-Content C:\Vijay_GitHub\opencode-automation-controller\.env | Where-Object { $_ -match '^OPENCODE_SERVER_PASSWORD=' }) -replace '^OPENCODE_SERVER_PASSWORD=','').Trim(); $cred = New-Object System.Management.Automation.PSCredential("opencode", (ConvertTo-SecureString $pw -AsPlainText -Force))
   Invoke-RestMethod -Uri "http://127.0.0.1:4097/session/ses_e5d80a12fffeF60OQcjjZCYEQR/message?limit=50" -Credential $cred
   ```
   Returns the full message list including user/assistant parts, `text`, `step-start`, `tool` (with
   `state.status/input/output/error`), token counts, cost, finish reason, model provider/id.

4. **List all OpenCode sessions on dev server:**
   ```powershell
   $pw = ((Get-Content C:\Vijay_GitHub\opencode-automation-controller\.env | Where-Object { $_ -match '^OPENCODE_SERVER_PASSWORD=' }) -replace '^OPENCODE_SERVER_PASSWORD=','').Trim(); $cred = New-Object System.Management.Automation.PSCredential("opencode", (ConvertTo-SecureString $pw -AsPlainText -Force))
   Invoke-RestMethod -Uri "http://127.0.0.1:4097/session" -Credential $cred
   ```

5. **Persisted research task (SQLite, read-only):**
   ```powershell
   cd C:\Vijay_GitHub\opencode-automation-controller
   .venv\Scripts\python -c "import sqlite3,json; c=sqlite3.connect(r'C:\Vijay_GitHub\fno-ai-paper-trading-dev\.opencode_bridge\bridge.db'); c.row_factory=sqlite3.Row; print(json.dumps([dict(r) for r in c.execute('SELECT * FROM research_tasks')], indent=2, default=str))"
   ```

6. **Controller MCP tools list (authenticated, requires initialize handshake):**
   ```powershell
   $token = ((Get-Content C:\Vijay_GitHub\opencode-automation-controller\.env | Where-Object { $_ -match '^MCP_AUTH_TOKEN=' }) -replace '^MCP_AUTH_TOKEN=','').Trim()
   $h = @{ Authorization = "Bearer $token"; "Content-Type" = "application/json" }
   $init = '{"jsonrpc":"2.0","id":0,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"audit","version":"1"}}}'
   Invoke-RestMethod -Method POST -Uri "http://127.0.0.1:8799/mcp" -Headers $h -Body $init | Out-Null
   $notif = '{"jsonrpc":"2.0","method":"notifications/initialized","params":{}}'
   try { Invoke-RestMethod -Method POST -Uri "http://127.0.0.1:8799/mcp" -Headers $h -Body $notif | Out-Null } catch {}
   $b = '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'
   (Invoke-RestMethod -Method POST -Uri "http://127.0.0.1:8799/mcp" -Headers $h -Body $b).result.tools.name
   ```

7. **OpenCode instance logs (research preflight runs):**
   ```powershell
   Get-Content C:\Vijay_GitHub\opencode-automation-controller\reports\evidence\test_research_isolation_002_flint\serve.err.log -Tail 20
   ```

No raw HTTP request/response is persisted by the controller today; the commands above are the only way to
see actual OpenCode HTTP response bodies (live server) and persisted research-task rows (SQLite).