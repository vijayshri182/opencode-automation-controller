# WP-GUI01 — ChatGPT ↔ OpenCode Automated Work Loop Feasibility

**Date:** 2026-11-02
**Repo:** `C:\Vijay_GitHub\fno-ai-paper-trading-dev` (DEV only)
**Branch:** `dev/phase-13`
**HEAD:** `d8cf5feb5d9af27487633466992337ff1f763599`
**Task type:** READ-ONLY feasibility. No implementation, no installs, no config changes, no commit/push.
**Preservation:** Existing dirty/untracked work left untouched; only this new report file is added.

---

## 1. Feasibility decision

**Decision: FEASIBLE WITH SUPERVISION** via an officially supported path.

The supported path is:

1. A **local MCP server** (HTTP, Streamable HTTP) exposing a small set of task/report tools.
2. An **OpenAI Secure MCP Tunnel** (`tunnel-client`) providing an outbound-only path from that local MCP server to ChatGPT, so the server never needs a public inbound port.
3. ChatGPT (product) adds the tunnel-backed server as a **custom MCP server / plugin** ("Add custom MCP server" → Connection: Tunnel).
4. The local controller receives tasks as MCP tool calls, queues them, runs OpenCode through its **official HTTP API** (`opencode serve`), collects reports/tests, and returns results as MCP tool results into the **same ChatGPT conversation**.

Fully unattended operation is **not** recommended: permission prompts, sensitive actions (commit/push/deploy/session launch), and OpenCode safety boundaries require either supervised approval or carefully pre-approved, allowlisted actions. The architecture below keeps a human approval gate for anything sensitive while allowing automatic task transfer and automatic result return for read-only / report-generating work.

---

## 2. Verified environment (mandatory context reuse)

### 2.1 DEV repository

| Item | Value |
|---|---|
| Path | `C:\Vijay_GitHub\fno-ai-paper-trading-dev` |
| Branch | `dev/phase-13` |
| HEAD | `d8cf5feb5d9af27487633466992337ff1f763599` |
| HEAD subject | `feat(replay): finalize data integrity, provenance, and dashboard consistency improvements` |
| Working tree | Dirty: 8 tracked modified + many untracked files (pre-existing). **Preserved; not touched.** |
| Project instructions | No `AGENTS.md`/`CLAUDE.md` at repo root. Project guidance lives in `docs/`, `README.md`, `.env.example`. |
| Memory | `.opencode/memory.md` is **not present** in this worktree (memory file lives in Default Project). No scan performed. |

### 2.2 OpenCode

| Item | Value |
|---|---|
| CLI version | `1.18.30` (from `opencode --version`) |
| Binary | `C:\Users\user\AppData\Local\Programs\nodejs\node_modules\opencode-ai\node_modules\opencode-windows-x64\bin\opencode.exe` |
| Desktop app | `C:\Users\user\AppData\Local\Programs\...` version 1.3.14.0 (separate) |
| Invocation (non-interactive) | `opencode run [message..]` with `--dir`, `--format json`, `--attach`, `--model`, `--agent`, `--auto`, `--port` |
| Headless server | `opencode serve --port <n> --hostname 127.0.0.1` (default port 4096) |
| Web UI | `opencode web` (starts server + opens browser) |
| Auth | HTTP basic auth via `OPENCODE_SERVER_PASSWORD` (username `opencode` or `OPENCODE_SERVER_USERNAME`) |
| Local DB | `opencode db path` → `C:\Users\user\.local\share\opencode\opencode.db` |
| OpenAPI spec | `http://127.0.0.1:<port>/doc` |
| Config | `C:\Users\user\.config\opencode\opencode.jsonc` (permissions; only PROD path currently allowed for `external_directory`) |
| Service secret | `C:\Users\user\.config\opencode\service.json` (password present; not reproduced here) |
| ACP server | `opencode acp` (Agent Client Protocol, optional IDE integration) |

Verified OpenCode HTTP API surface (from official docs at `https://opencode.ai/docs/server/`): sessions, messages (sync + `prompt_async`), abort, diff, files, config, providers, agents, events (SSE), TUI control, permissions. This is sufficient to drive OpenCode programmatically with no GUI automation.

### 2.3 Local automation & communication capabilities

| Capability | Status |
|---|---|
| Python | 3.13.15 |
| Node | 24.19.0 (system) + vendored `vendor/node-v24.21.0-win-x64/` in repo |
| FastAPI / uvicorn / aiosqlite / requests | Installed (FastAPI 0.143.2, uvicorn 0.54.0, aiosqlite 0.22.1, requests 2.34.2) |
| SQLite | Available (stdlib + `opencode db`) |
| MCP Python SDK (`mcp`, `fastmcp`) | **Not installed** — must be added or replaced by a minimal JSON-RPC/HTTP MCP implementation |
| GUI automation libs (pyautogui, pywinauto, selenium, playwright, pywin32) | **Not installed** |
| Existing repo GUI | Node 24 + Fastify (127.0.0.1:8787) + React 19/Vite (localhost:5173), read-only over SQLite |
| OpenCode permissions config | `permission.external_directory` currently allows only PROD path; **DEV path must be added before any unattended DEV work** (config change, out of scope for this read-only task) |

### 2.4 Safety-relevant F&O constraints (binding)

- DEV only: `C:\Vijay_GitHub\fno-ai-paper-trading-dev`.
- PROD must remain untouched and inaccessible where feasible.
- No commit/push unless separately authorized.
- No Upstox APIs, tokens, OAuth, or credentials.
- No session launch, live orders, or deployment.
- No risk-control changes.
- Preserve paper-only invariants (`ExecutionMode.PAPER`, `PaperBroker.is_live=False`, `can_write_orders=False`).
- No generated strategy-candidate execution; RF16 NO-GO remains binding.
- No automatic approval of sensitive actions.
- Preserve dirty and untracked files.

---

## 3. Supported ChatGPT → local handoff options

### Option A — ChatGPT Custom GPT with Actions (OpenAPI) to a public HTTPS endpoint
- Mechanism: A Custom GPT calls a REST endpoint you expose; results come back as tool output in the same conversation.
- Pros: Native to ChatGPT; no tunnel client; simple HTTP.
- Cons: Requires a **publicly reachable HTTPS** endpoint with valid TLS; exposes the controller to the internet; conflicts with "do not expose unauthenticated service to network" unless fronted by auth + TLS + allowlisting. Not the preferred path for a private dev machine.

### Option B — ChatGPT custom MCP server over Secure MCP Tunnel (RECOMMENDED)
- Mechanism (officially supported): Run a local MCP server; run OpenAI's `tunnel-client` outbound to OpenAI; in ChatGPT Plugins choose "Add custom MCP server" → Connection: **Tunnel** and select/paste the `tunnel_id`.
- Pros: **Outbound-only** (no inbound firewall ports, no public listener); local MCP server stays private; result returns automatically as MCP tool result in the same conversation; supports stdio or HTTP MCP servers; supports approvals; ChatGPT product native.
- Cons: Requires OpenAI Platform account + tunnel creation + RBAC permissions (Tunnels Read/Manage/Use); tunnel must be associated with the target ChatGPT workspace; `tunnel-client` must stay running; 600 req/min, 10 MiB serialized envelope, 120 s request deadline; personal-account vs enterprise workspace association caveats.

### Option C — Responses API with `tunnel_id` (programmatic, not ChatGPT UI)
- Mechanism: Call OpenAI Responses API with an MCP tool whose `tunnel_id` points at the tunnel. Useful for building your own orchestrator, but it is **not** "the same ChatGPT conversation" unless you also drive ChatGPT through the API (which is a different surface). Keep as a secondary/automation option, not the primary UX.

### Option D — Manual copy/paste loop (fallback)
- Human copies the task from ChatGPT, drops it into the controller/GUI, runs, pastes the report back. Always available, zero infra, but not automated. Useful as the degraded mode when tunnel/permissions are unavailable.

### Option E — ChatGPT desktop local file access / "computer use" (not recommended)
- Fragile, UI-dependent, and not a supported programmatic handoff. Rejected per the "no fragile screen-coordinate assumptions" requirement.

**Recommendation: Option B** as the primary path, with Option D as the always-available fallback. Option A only if a public HTTPS endpoint is later justified and secured.

---

## 4. Supported local → same-conversation return options

- **MCP tool results** are returned into the same ChatGPT conversation automatically (the tool's JSON/text output becomes part of the model context). This satisfies "return into the SAME conversation" without copy/paste.
- **Asynchronous polling is required**: tunnel request deadline is 120 s and the serialized envelope limit is 10 MiB. Long OpenCode runs (minutes) cannot be a single synchronous tool call. Design:
  - `submit_task` returns immediately with `{ task_id, status: "queued" }`.
  - `get_task_status(task_id)` returns `{ status, phase, elapsed_s, last_log_line }`.
  - `get_task_result(task_id)` returns the final report summary + artifact paths + test counts + git diff stat when `status == "completed"`; otherwise `not_ready`.
- **Large artifacts**: return a compact digest (report path, key metrics, test pass/fail counts, diff stat, sha256 of report) rather than full file contents. Full files stay on disk; the user opens them locally or the controller exposes them via a separate read-only local endpoint. If MCP resources are implemented, expose report files as MCP resources for on-demand fetch (still subject to 10 MiB per request).
- **Progress**: optional SSE/`global/event` from OpenCode can be summarized into status; or poll OpenCode session messages.

---

## 5. Recommended architecture

### 5.1 Components

1. **Local MCP Server (HTTP, Streamable HTTP)** — the handoff surface.
   - Tools (minimal): `submit_task`, `get_task_status`, `get_task_result`, `list_tasks`, `cancel_task`, `approve_action`.
   - Runs on `127.0.0.1:<port>` (e.g. 8799), no public bind.
   - Auth: shared local secret in header (defense in depth; tunnel also provides OpenAI-side auth).

2. **Controller service (FastAPI + uvicorn)** — queue + execution + audit.
   - SQLite audit DB (task id, created/started/finished timestamps, request text, status, report path, test counts, git HEAD before/after, hashes).
   - Single worker (concurrency = 1) to avoid concurrent repo mutations.
   - Task states: `queued → running → (completed | failed | cancelled | blocked)`.

3. **OpenCode adapter** — drives OpenCode via its official HTTP API.
   - Preferred: start/reuse `opencode serve --port <p> --hostname 127.0.0.1` with `OPENCODE_SERVER_PASSWORD`; use `/session` (create), `/session/:id/prompt_async` (submit task), `/session/:id/message` (poll), `/session/:id/abort` (cancel), `/event` (SSE for progress).
   - Alternative: spawn `opencode run --dir <DEV> --format json` per task and capture stdout; simpler but less observable. Use as fallback.
   - Always pass `--dir C:\Vijay_GitHub\fno-ai-paper-trading-dev`.

4. **Evidence collector** — after a task finishes, read the report file named in the task, capture pytest summary (from a known log path), `git status --porcelain` + `git diff --stat`, and sha256 of changed/new report files. Never mutates repo.

5. **Secure MCP Tunnel client** (`tunnel-client`) — outbound-only bridge to ChatGPT. Keep running while in use; health via `/healthz`, `/readyz`, `/ui`.

6. **Optional monitoring GUI** — extend the existing Fastify/React GUI or add a small page that reads controller + OpenCode status. Uses HTTP APIs only. No screen coordinates, no desktop automation.

### 5.2 Data flow

```
ChatGPT (user) ──MCP tool call (submit_task)──► Secure MCP Tunnel (outbound) ──► tunnel-client ──► Local MCP Server (127.0.0.1) ──► Controller (queue)
                                                                                                                                           │
                                                                                                                                           ▼
                                                                                                                                    OpenCode serve (127.0.0.1) ──► DEV repo (read/write reports, tests)
                                                                                                                                           │
                                                                                                                                           ▼
Controller ◄── report/tests/diff ── OpenCode session done
   │
   └── MCP tool result (status/result digest) ──► tunnel-client ──► ChatGPT conversation (same thread)
```

### 5.3 DEV-only enforcement (controller-side)

- Hard-code allowed working directory to `C:\Vijay_GitHub\fno-ai-paper-trading-dev`; reject any task whose resolved path is outside it.
- Refuse tasks mentioning PROD paths or credentials.
- OpenCode `external_directory` permission must include DEV path (config change required before unattended use).
- Block tasks that request commit/push/deploy/session-launch/live-orders unless an explicit approval token is supplied and verified; default deny.
- Preserve dirty tree: controller records `git status --porcelain` before/after and warns if unexpected changes occur; never runs `git clean/reset/stash`.

---

## 6. GUI automation strategy

**Do not use screen coordinates or desktop automation.** Instead:

- Use **OpenCode's official HTTP API** (`opencode serve`) for all control: create sessions, send prompts, poll messages, abort, read diffs/files, stream events (SSE).
- Use **`opencode web`** when a human wants the official browser UI; it binds to localhost and uses the same API.
- Use the **controller's own HTTP API** for task queue/audit status.
- Extend the existing repo GUI (Fastify + React, 127.0.0.1:8787) with read-only panels for controller/OpenCode status if desired; it already follows loopback-only, read-only, no-live-broker principles.
- If a native window must be driven (rare), use OpenCode's **TUI control endpoints** (`/tui/*`) or **ACP** (`opencode acp`), not pixel coordinates.
- For monitoring OpenCode progress, prefer SSE (`/event`, `/global/event`) or polling `/session/:id/message` over log scraping.

---

## 7. Security model

- **Loopback only**: MCP server, controller, OpenCode serve, tunnel client admin all bind `127.0.0.1`. No `0.0.0.0` except via explicit, reviewed decision.
- **OpenCode auth**: `OPENCODE_SERVER_PASSWORD` set; username `opencode` (or override). Never log or commit it.
- **Controller auth**: local shared secret in request header; rotate per session if desired.
- **Tunnel**: outbound HTTPS only to `api.openai.com:443`; no inbound ports. Requires OpenAI Platform org + tunnel RBAC (Read/Manage/Use). Tunnel associated with the target ChatGPT workspace, not just a personal org.
- **Approvals**: ChatGPT MCP approvals (`require_approval`) can be set to `always` for sensitive tools and `never` only for read-only reporting tools. Controller also enforces its own allowlist.
- **Data limits**: 10 MiB serialized envelope, 600 req/min, 120 s request deadline, 1000 pending queue. Design all tools to be fast and small; long work is async.
- **Secrets handling**: never put tokens in task text or reports; controller redacts; audit DB stores hashes/paths, not secret values.
- **Audit**: SQLite with task id, timestamps, request (sanitized), status, report path, test counts, git HEAD before/after, artifact sha256. Retain for traceability.
- **No auto-approval of sensitive actions**: commit/push/deploy/session-launch/live-order requests are denied unless an out-of-band human approval is recorded.

---

## 8. Supervised vs continuous operating modes

### Supervised (recommended initial mode)
- ChatGPT generates a task → controller queues it but marks `awaiting_approval`.
- Human reviews the queued task (via GUI or CLI) and approves → worker runs.
- Result returned to ChatGPT automatically.
- Sensitive actions always require approval.

### Continuous (opt-in later)
- Approved task types (e.g. "run tests", "generate report", "run a named read-only analysis") execute automatically.
- Hard allowlist of task kinds; anything outside the allowlist is queued for approval.
- Rate limits (e.g. max N tasks/hour), timeout per task, cancel support.
- Stop conditions: 3 consecutive failures, dirty-tree drift, OpenCode auth failure, or any safety-latch trip → pause and notify.

---

## 9. Exact limitations and manual steps

1. **OpenAI account/tunnel prerequisites (manual, one-time)**: create tunnel in Platform tunnel settings, associate with the target ChatGPT workspace, grant Tunnels Read/Manage/Use, install/run `tunnel-client`, verify `/readyz`. Personal accounts vs enterprise workspaces may need manual association override.
2. **ChatGPT workspace permission**: admin must allow adding custom MCP servers; plugin creation requires "I understand and want to continue" risk acknowledgement.
3. **MCP SDK not installed**: either install an MCP SDK (out of scope for this read-only task) or implement a minimal Streamable HTTP JSON-RPC server. Recommend installing `mcp`/`fastmcp` for Python or using the Node MCP SDK with the vendored Node.
4. **OpenCode permission config**: `external_directory` currently allows only the PROD path. Add DEV path before unattended DEV execution (config change, separate authorization).
5. **Permission prompts**: OpenCode may prompt for file writes/commands during a run. For unattended runs, configure permissions or use `--auto` (dangerous; not recommended). Supervised mode avoids this.
6. **120 s tunnel deadline**: long tasks must be async with polling; a single synchronous tool call will time out.
7. **10 MiB envelope**: return digests, not full artifacts.
8. **No live Upstox/credentials**: controller must never read or transmit tokens; tasks touching credentials are denied.
9. **PROD isolation**: controller hard-codes DEV path; PROD path is not in the allowlist. (Config-level exclusion of PROD from OpenCode permissions is already in place.)
10. **Same-conversation guarantee** depends on tunnel health and ChatGPT product support; manual fallback (Option D) remains available.

---

## 10. Implementation plan and acceptance criteria

### Phase 1 — Local-only MVP (no tunnel)
- Implement controller + SQLite + single worker.
- Implement local MCP HTTP server with `submit_task`, `get_task_status`, `get_task_result`, `list_tasks`.
- OpenCode adapter via `opencode serve` HTTP API.
- Evidence collector + before/after `git status` capture.
- Acceptance: submit a task via `curl` to local MCP server; OpenCode runs in DEV; report file appears; result returned via MCP tool response; dirty tree preserved; PROD untouched.

### Phase 2 — Tunnel + ChatGPT
- Run `tunnel-client`; create custom MCP server in ChatGPT (Tunnel).
- End-to-end: ChatGPT task → local controller → OpenCode → result in same conversation.
- Acceptance: one full loop completed with a real report; status polling works; cancellation works.

### Phase 3 — Monitoring & hardening
- Extend existing GUI with controller/OpenCode status (read-only).
- Add timeouts, duplicate-task prevention (idempotency key), recovery after interruption (reconcile queued/running tasks on startup), cancellation.
- Acceptance: kill controller mid-task → restart → task reconciled to `failed`/`cancelled` with evidence; no duplicate execution; timeout enforced.

### Acceptance criteria (overall)
- [ ] No unauthenticated service exposed to the network.
- [ ] All services bind 127.0.0.1 by default.
- [ ] DEV path enforced; PROD inaccessible.
- [ ] Dirty/untracked files preserved across runs.
- [ ] No commit/push/live-order/session-launch without explicit approval.
- [ ] Paper-only invariants unchanged.
- [ ] Automatic task transfer and automatic result return demonstrated in same ChatGPT conversation (via tunnel) OR manual fallback documented.
- [ ] No GUI screen-coordinate automation used.

---

## Appendix A — Verified command reference

- `opencode --version` → `1.18.30`
- `opencode serve --port 4096 --hostname 127.0.0.1`
- `opencode web`
- `opencode run --dir "C:\Vijay_GitHub\fno-ai-paper-trading-dev" --format json "…"`
- `opencode db path` → `C:\Users\user\.local\share\opencode\opencode.db`
- `opencode session list`
- OpenAPI spec: `http://127.0.0.1:<port>/doc`
- Health: `GET /global/health` → `{ healthy, version }`
- Python: 3.13.15; Node: 24.19.0; FastAPI 0.143.2; aiosqlite 0.22.1

## Appendix B — Source references

- OpenCode server docs: `https://opencode.ai/docs/server/`
- OpenCode CLI: `opencode --help`
- OpenAI MCP servers guide: `https://developers.openai.com/api/docs/guides/tools-connectors-mcp`
- OpenAI Secure MCP Tunnel: `https://developers.openai.com/api/docs/guides/secure-mcp-tunnels`
- F&O GUI architecture: `docs/gui_architecture.md`, `docs/local_gui_setup.md`
- F&O project scope/safety: `README.md`, `PROJECT_PLAN.md`, `PRODUCTION_DEVELOPMENT_SEPARATION.md`
