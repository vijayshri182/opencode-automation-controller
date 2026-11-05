# WP-422 — Controlled CDP Enablement for the Existing Normal Edge Profile

- **Date:** 2026-11-02
- **Repository:** `C:\Vijay_GitHub\opencode-automation-controller` (branch `master`, **no commits exist**; all files untracked — nothing committed or pushed)
- **Verdict:** **Phase 2 (code/config) PASS. Phase 3/4 (live migration) BLOCKED — not attempted.**
  No Edge process was closed, restarted, relaunched, killed or modified. No profile data was created, copied, moved or deleted. `attach_existing()` correctly refused to launch a replacement browser and reported the exact CDP error.
- **Scope honesty:** everything below marked *mock/unit* is proven by tests with fake browsers. Everything marked *live* is a read-only observation of the real machine. The ChatGPT↔OpenCode loop is **not** claimed operational.

---

## 1. Phase 1 — Identify and validate the existing browser

All observations are read-only (`Get-CimInstance`, `Get-Process`, registry reads, file existence checks, TCP connect attempts).

### 1.1 The real Edge process

| Property | Value |
|---|---|
| Top-level `msedge.exe` | **PID 2420** |
| Parent PID | 24088 |
| Creation time | 23-10-2026 12:56:20 (uptime ≈ 10 days) |
| Command line | `"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe" --no-startup-window /prefetch:5` |
| `--remote-debugging-port` present | **No** |
| `--user-data-dir` present | **No** (so the default directory is in use) |
| Main window title | `Chat GPT and Open Code Int and 9 more pages - Personal - Microsoft Edge` |
| Total `msedge.exe` processes | 24 (PID 2420 + renderer/GPU/utility children) |
| Other top-level Edge processes | **None** — exactly one browser instance |

Exactly one top-level browser process exists, so there is no ambiguity about which process is "the user's normal Edge".

### 1.2 User-data and profile directories

| Property | Value |
|---|---|
| User-data dir | `C:\Users\user\AppData\Local\Microsoft\Edge\User Data` |
| Created | 11-09-2026 00:32:14 |
| Profiles present | **`Default` only** |
| `Local State` → `profile.last_used` | `Default` |
| `Local State` → `profile.last_active_profiles` | `[Default]` |
| `DevToolsActivePort` in user-data dir | **absent** → remote debugging is not active |

`.edge-profile-automation` is **not** the profile in use and was **not** substituted. It has no owning process, no `SingletonLock` and no `DevToolsActivePort`.

### 1.3 Open windows/tabs and unsaved-work risk

The window title reports **10 open pages** ("… and 9 more pages"). The tab set **cannot be enumerated** without CDP or UI automation, and neither is available:

- CDP: no endpoint is listening.
- UI automation: enumerating tabs by driving the live UI would mean interacting with the borrowed browser before attachment is established — out of scope for Phase 1 and against the WP-419/WP-421 UI rules.

Therefore unsaved work **cannot be ruled out**. This is one of the two independent reasons Phase 3 was not executed (see §4).

### 1.4 Edge version

| Channel directory | Version |
|---|---|
| `Application\155.0.4283.62` (running, `ProductVersion` 155.0.4283.62) | **155.0.4283.62** |
| `Application\156.0.4314.58` | 156.0.4314.58 (staged, not running) |

Both are far above Chromium 136.

### 1.5 Enterprise / browser policies affecting remote debugging

| Key | State |
|---|---|
| `HKLM:\SOFTWARE\Policies\Microsoft\Edge` | **absent** |
| `HKCU:\Software\Policies\Microsoft\Edge` | **absent** |

Consequences:

- `RemoteDebuggingAllowed` is **not configured** → remote debugging is *allowed* by policy (Edge ≥ 93 semantics).
- `DeveloperToolsAvailability` is **not configured** → DevTools/CDP targets are not restricted by policy.
- No MDM/GPO override exists that could re-enable CDP on the default directory, and none was created (creating one would be a policy/security change, out of scope).

So policy is *not* the blocker. The blocker is the browser-level rule below.

### 1.6 Does this Edge support CDP on the existing normal user-data dir?

**No.**

Authoritative statement (Chrome for Developers, "Changes to remote debugging switches to improve security", Will Harris, 2025-03-17 — inherited by Edge as a Chromium downstream):

> "Therefore, from Chrome 136 we're making changes to the behavior of `--remote-debugging-port` and `--remote-debugging-pipe`. These switches will no longer be respected if attempting to debug the default Chrome data directory. These switches must now be accompanied by the `--user-data-dir` switch to point to a non-standard directory."
> — https://developer.chrome.com/blog/remote-debugging-port

Corroborating sources:

- Chrome Enterprise release notes, Chrome 136: "Custom data directory required for remote debugging … Remote debugging via a TCP port or a pipe is no longer possible in Google Chrome with the default data directory on Windows, Linux, and macOS."
- Chromium issue 415018774 — closed **Won't Fix (Intended Behavior)**: "to use `--remote-debugging-port` in Chrome 136 and above, you must specify a non-default user data dir using the `--user-data-dir` switch".
- Microsoft Q&A 5976829 (Edge-specific, 2026-08-16): Edge built from the same Chromium shows identical behaviour; the accepted answer notes the only working command-line approach is an absolute path to a **dedicated** directory, and "there isn't a supported switch that restores CDP on the default profile".

Note the distinction that trips people up: `--user-data-dir="default"` is a *relative path*, so it creates `.\default` rather than pointing at the real profile. Pointing `--user-data-dir` **at** `C:\Users\user\AppData\Local\Microsoft\Edge\User Data` is exactly the case that is blocked.

**Live confirmation on this machine (read-only):**

| Probe | Result |
|---|---|
| Raw TCP connect `127.0.0.1:9222–9226` | all `TimeoutError` (no listener; no RST) |
| `Get-NetTCPConnection -State Listen` filtered 9220–9235 | **(none)** |
| `Test-NetConnection 127.0.0.1 -Port 9224` | `False` |
| `DevToolsActivePort` in the real user-data dir | absent |
| `attach_existing(cdp_url="http://127.0.0.1:9224")` | `cdp_connect_failed` — `Error: BrowserType.connect_over_cdp: connect ECONNREFUSED 127.0.0.1:9224` |

Full JSON: `reports/execution/wp422_live_evidence.json`.

### 1.7 Does enabling remote debugging require profile migration or a different user-data dir?

**Yes — a different directory is required on the command-line path.** There is no profile *migration* option: the Chromium rule keys on the directory *path*, so the only command-line route is a non-standard directory (which means a different encryption key and therefore no inherited ChatGPT sign-in). A symlink/junction back to the real directory is explicitly rejected by design (Chromium issue 497897156).

The **only** route that keeps the real profile is the Edge `edge://inspect` opt-in (§5.1).

---

## 2. Phase 2 — Configuration resolution (completed)

### 2.1 Port standardisation on 9224

| File | Change |
|---|---|
| `src/opencode_bridge/managed_edge.py` | `DEFAULT_CDP_PORT` **9222 → 9224** |
| `src/opencode_bridge/edge_attach.py` | `CDP_URL` now **derives** from `DEFAULT_CDP_PORT` (`http://127.0.0.1:{DEFAULT_CDP_PORT}`) instead of hard-coding a literal; `EDGE_CDP_URL` still overrides for diagnostics only |
| `src/opencode_bridge/operator_cli.py` | `--cdp-port` default **9222 → 9224** |

The literal `9222` no longer appears anywhere in `src/opencode_bridge/*.py` — enforced by `test_no_hidden_9222_fallback_in_source`. There is no hidden fallback to 9222 in any code path.

### 2.2 Attach-only is preserved and enforced

- `edge_attach.py` contains no launch, close, terminate, kill, subprocess, shutil or filesystem-mutation primitive (AST-checked by `test_attach_module_has_no_launch_or_termination_primitives`; string-checked by `test_existing_profile_paths_are_never_mutated_by_attach`).
- `CdpEdgeAdapter.start()` in attach-only mode calls `attach_existing()` and **raises** `ManagedEdgeError("CDP attach failed (<reason>): <exact error>")` if it fails — `launcher.start()` is never reached.
- `CdpEdgeAdapter.terminate_managed()` now returns early in attach-only mode, so the borrowed browser is never terminated.
- `CdpEdgeAdapter.stop()` in attach-only mode only calls `playwright.stop()` — it never calls `browser.close()`, so CDP-created contexts in the user's browser are left intact.
- `ManagedEdgeLauncher.stop()` only ever touches `self._process` — i.e. a browser that this launcher itself spawned. After attach-only usage that attribute is `None`, so it is a no-op. No `psutil`, `taskkill`, `Stop-Process`, `killall`, `os.kill` or `/F /PID` anywhere in either module.

### 2.3 New `DevToolsActivePort` / WebSocket attach route

Added because the *sanctioned* route for a real profile (§5.1) may expose only the browser WebSocket, not the HTTP `/json/*` endpoints:

- `discover_ws_endpoint(user_data_dir)` — reads `DevToolsActivePort` (line 1 = port, line 2 = browser WS path), builds `ws://127.0.0.1:<port><path>`, and returns stable blocked reasons (`devtools_active_port_absent` / `_malformed` / `_unreadable`).
- `attach_existing_edge(..., user_data_dir=...)` — tries the configured HTTP endpoint first, and only if that fails and a `DevToolsActivePort` exists, retries once against the WebSocket. Evidence is recorded in `discovery` (`http` / `websocket` / `devtools_active_port`) and `attempted_endpoints`.
- `CdpEdgeAdapter(attach_only=..., user_data_dir=...)` — threads the directory through.
- `operator_cli.py` gained `--attach-only` and `--user-data-dir` flags.

This adds a *retry against the same browser process*. It does not add a launch path, and it cannot substitute a different profile.

### 2.4 `--no-sandbox`

Unchanged and still absent from all application launch arguments (WP-420A already stopped Playwright injecting it, via `chromium_sandbox=True`). No security weakening was introduced by this task.

---

## 3. Phase 3 — Controlled migration: **NOT PERFORMED**

### 3.1 Decision

Two independent reasons, either of which is sufficient to stop:

1. **Restarting would not achieve the goal.** Relaunching Edge with the same user-data directory plus `--remote-debugging-port=9224` is *ignored* by Edge 155 (Chromium ≥136 rule, §1.6). Closing the user's working browser to gain nothing would be a net loss.
2. **Unsaved work cannot be excluded.** 10 pages are open (§1.3) and cannot be enumerated without the CDP access we do not have. Closing gracefully still discards volatile page state and any unsaved form input.

Per the task's own gate — *"If the existing profile cannot safely support CDP, or if unsaved work, policy restrictions, or profile migration risks are detected, STOP before closing or modifying Edge"* — **Phase 3 stopped before any action**.

### 3.2 What was therefore NOT done

- No graceful close of Edge; no `Stop-Process`; no `terminate()`; no `/F`.
- No relaunch; no new Edge instance; **no new PID** (there is no "new Edge process" to report).
- No profile directory created, copied, renamed, reset or deleted; `.edge-profile-automation` remains empty of processes and untouched as a profile.
- No dedicated automation browser launched as a fallback.
- No credentials, `.env`, tokens, auth state or browser settings read or modified.
- No OpenCode API server, desktop app or worker restarted.

### 3.3 Profile-preservation statement

The original user-data directory `C:\Users\user\AppData\Local\Microsoft\Edge\User Data` and its single `Default` profile are **exactly as found** (same creation time, same `last_used`, no `DevToolsActivePort` added). Edge PID 2420 is still alive with the same creation timestamp and command line, so the authenticated ChatGPT session is by definition untouched — nothing was restarted, so nothing could have been lost. No credential material was inspected to prove this; the proof is the absence of any restart.

---

## 4. Phase 4 — Live verification: **BLOCKED**

| Step | Required | Result |
|---|---|---|
| 1. Verify browser process + user-data dir | — | **PASS (live, read-only)** — PID 2420, dir as above |
| 2. Verify CDP on 9224 | listening | **FAIL** — `ECONNREFUSED 127.0.0.1:9224`; nothing listening 9220–9235 |
| 3. Playwright attaches without launching | attach | **BLOCKED** — no endpoint exists; adapter reported `cdp_connect_failed` and `launched_new_browser: false` |
| 4. Reuse existing tabs/contexts | — | **NOT REACHED** (mock-tested only: `test_attaches_instead_of_launching`, `test_reuses_existing_project_tab_without_navigation`) |
| 5. Navigate a ChatGPT tab to the Palmistry Project *if necessary* | — | **NOT EXECUTED** — `navigated: false` |
| 6. Palmistry Project rendered, conversation list visible | — | **NOT REACHED** |
| 7-9. No messages / no conversation created / no task executed | — | **HONOURED** |

Live evidence (`reports/execution/wp422_live_evidence.json`):

```json
"attach_result": {
  "ok": false,
  "reason": "cdp_connect_failed",
  "error": "http://127.0.0.1:9224 -> Error: BrowserType.connect_over_cdp: connect ECONNREFUSED 127.0.0.1:9224",
  "discovery": "http",
  "attempted_endpoints": ["http://127.0.0.1:9224"],
  "attached_to_existing_browser": false,
  "launched_new_browser": false,
  "navigated": false,
  "devtools_active_port": { "ok": false, "reason": "devtools_active_port_absent" }
}
```

This is the **correct** behaviour for WP-421A/WP-422: blocked deterministically, no fallback launch.

---

## 5. Remaining blockers and the operator-only routes

### 5.1 Option A — sanctioned, keeps the real profile (recommended)

Microsoft documents an in-browser opt-in that works on the *real* profile (Microsoft Learn, "Let agents inspect your site and WebView2 app with Chrome DevTools MCP" → Step 1, *Option B*):

1. In the **running** Edge (PID 2420), open `edge://inspect`.
2. Left sidebar → **Remote debugging**.
3. Tick **"Allow remote debugging for this browser instance"**.
4. Approve the per-connection "Allow remote debugging?" prompt if shown.

Microsoft's own troubleshooting text confirms the resulting artefact: *"Make sure the `DevToolsActivePort` file exists in the user data directory. The `DevToolsActivePort` file is created when remote debugging is active."* — which is exactly the path WP-422 now supports via `discover_ws_endpoint`.

Constraints:

- **This must be done by the operator.** It is a browser-security consent action; automating a consent dialog is out of scope and would defeat its purpose.
- The port is chosen by Edge (not necessarily 9224), which is why the WebSocket/`DevToolsActivePort` route was added rather than assuming 9224.
- It is a per-session grant; it may need re-ticking after an Edge restart.
- The assistant has not opened `edge://inspect`, clicked anything, or created the `DevToolsActivePort` file.

No restart is required, so no unsaved work is lost and the authenticated session is preserved by construction.

### 5.2 Option B — dedicated, non-default profile (needs separate authorisation)

A non-default `--user-data-dir` (§5.4 command) is the only command-line route that works. It contradicts WP-422's "no dedicated automation browser" boundary, so it is listed for the operator's decision, **not** performed. It also requires a fresh ChatGPT sign-in in that profile.

### 5.3 Option C — Chromium / Chrome for Testing

The Chromium blog states the restriction "does not affect Chrome for Testing and Chromium." Using a Chromium-for-Testing binary would sidestep the rule but is a different browser than the user's Edge; recorded for completeness only.

### 5.4 Reference command for Option B (NOT executed)

```
"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe" ^
  --remote-debugging-port=9224 ^
  --user-data-dir="C:\Vijay_GitHub\opencode-automation-controller\.edge-profile-automation" ^
  --no-first-run --no-default-browser-check
```

No `--no-sandbox`. Never point this at `C:\Users\user\AppData\Local\Microsoft\Edge\User Data` — it will silently not listen.

---

## 6. Files changed

All changes are uncommitted; the repository has no commits at all.

| File | Change | SHA-256 (first 16) |
|---|---|---|
| `src/opencode_bridge/managed_edge.py` | `DEFAULT_CDP_PORT` 9222→9224; `CdpEdgeAdapter(user_data_dir=...)`; `terminate_managed()` no-op for borrowed browser | `A8302B68E366D0DE` |
| `src/opencode_bridge/edge_attach.py` | `CDP_URL` derived from `DEFAULT_CDP_PORT`; `DEFAULT_EDGE_USER_DATA_DIR`; new `discover_ws_endpoint()`; WebSocket fallback + `discovery`/`attempted_endpoints` evidence in `attach_existing_edge()` | `FCF7AADC939E3300` |
| `src/opencode_bridge/browser_automation.py` | `PlaywrightEdgeAdapter.attach_existing(user_data_dir=...)` passthrough | `8E2B7BCF3FC6F4FA` |
| `src/opencode_bridge/operator_cli.py` | `--cdp-port` default 9224; new `--attach-only`, `--user-data-dir`; adapter wiring | `BA80859E3E38CAAE` |
| `tests/test_wp422_edge_cdp_config.py` | **new** — 16 tests | `86EC5B0F04BB9F4A` |
| `reports/execution/wp422_live_evidence.json` | **new** — live probe evidence | — |
| `reports/execution/wp422_existing_edge_cdp_migration_2026-11-02.md` | **new** — this report | — |

No `.env`, credential, token, authentication or profile file was read, created or modified.

---

## 7. Tests executed

Environment: repo `.venv` Python, `pytest` 9.x, run from `C:\Vijay_GitHub\opencode-automation-controller`.

### 7.1 WP-422 suite — `tests/test_wp422_edge_cdp_config.py`

**16 passed** (8.33 s). Coverage mapped to the required test list:

| Requirement | Test |
|---|---|
| Port 9224 as the single configured CDP port | `test_single_configured_cdp_port_is_9224` (asserts `DEFAULT_CDP_PORT == 9224`, `CDP_URL == http://127.0.0.1:9224`, `launcher.cdp_url()`) |
| No hidden 9222 fallback | `test_no_hidden_9222_fallback_in_source` (grep of every `src/opencode_bridge/*.py`) |
| CDP-only attachment | `test_attach_module_has_no_launch_or_termination_primitives` (AST: no `.launch`/`.launch_persistent_context`/`.close`/`.terminate`/`.kill`, no `subprocess`/`shutil`) |
| No browser launch fallback | `test_attach_only_adapter_has_no_launcher_start`, `test_attach_without_devtools_active_port_is_blocked_not_launched`, `test_attach_only_start_reports_blocked_and_creates_no_profile_dir` |
| Existing profile preservation | `test_existing_profile_paths_are_never_mutated_by_attach` (no `mkdir`/`rmdir`/`unlink`/`copyfile`/`copytree`/`rename`), `test_attach_only_start_reports_blocked_and_creates_no_profile_dir` |
| No forced termination | `test_attach_only_terminate_managed_never_stops_the_borrowed_browser`, `test_launcher_stop_is_noop_when_it_spawned_nothing`, `test_no_forced_termination_primitives_in_attach_or_launch_paths` |
| Graceful stop without closing borrowed contexts | `test_cdp_adapter_stop_disconnects_without_closing_borrowed_context` |
| `DevToolsActivePort` / WS route | `test_discover_ws_endpoint_reads_devtools_active_port`, `..._missing_file_is_blocked`, `..._malformed_is_blocked`, `test_attach_falls_back_to_devtools_active_port_websocket`, `test_ws_endpoint_skips_http_discovery` |
| Blocked behaviour when CDP unavailable | `test_attach_without_devtools_active_port_is_blocked_not_launched` (asserts exact `ECONNREFUSED 127.0.0.1:9224` and `launched_new_browser` absent-false) |

### 7.2 Focused regression (incl. WP-419 / WP-421A)

```
tests/test_wp422_edge_cdp_config.py  tests/test_wp421a_cdp_attach.py
tests/test_wp421_project_discovery.py  tests/test_managed_edge_cdp.py
tests/test_playwright_bridge_mock.py  tests/test_browser_sandbox.py
tests/test_chat_persistence.py  tests/test_auth_basic.py
tests/test_autonomous_policy.py  tests/test_playwright_real_edge.py
```

→ **67 passed** (42.77 s). Includes the WP-419 UI-navigation regression (`test_wp419_ui_navigation_preserved_and_no_direct_conversation_url`) and the whole WP-421A attach suite (16 tests).

### 7.3 Full suite

```
pytest tests --ignore=tests/test_opencode_bridge_gui03.py --ignore=tests/test_opencode_bridge_mcp.py
```

→ **80 passed, 1 failed** (165.96 s).

The single failure is pre-existing and unrelated: `tests/test_integration_opencode.py::test_integration_real_task` — a **live OpenCode API** integration test (`send_prompt_async` + 120 s poll) that returns no assistant text in this environment. It exercises no browser code and failed identically before WP-422.

The two ignored modules are uncollectable due to a missing `fastapi` package (`ModuleNotFoundError: No module named 'fastapi'`) — pre-existing, unrelated to this task.

### 7.4 Mock vs live — explicit separation

- **Proven by mock/unit tests:** port 9224 standardisation, no 9222 fallback, attach-only (no launch/no terminate/no profile mutation), tab ranking/reuse, graceful disconnect, `DevToolsActivePort` parsing and WS fallback, blocked-reason codes.
- **Proven live (read-only):** process identity (PID 2420), profile directory and single `Default` profile, absence of `DevToolsActivePort`, absence of any listener on 9220–9235, absence of Edge policies, Edge version 155.
- **NOT proven live:** CDP attachment, tab/context reuse against the real browser, Palmistry Project rendering, conversation-list visibility, message round trip. These remain **BLOCKED** on §5.1.

---

## 8. Summary

| Phase | Outcome |
|---|---|
| 1 — Identify/validate existing browser | **PASS** — PID 2420, single `Default` profile at the standard user-data dir, Edge 155.0.4283.62, no Edge policies, no CDP, 10 un-enumerable tabs |
| 2 — Resolve configuration | **PASS** — single CDP port 9224, no 9222 fallback, attach-only enforced, no launch fallback, no `--no-sandbox`, profile never mutated, `DevToolsActivePort` route added |
| 3 — Controlled migration | **NOT PERFORMED (by design)** — relaunch cannot enable CDP on the default dir; unsaved work cannot be excluded |
| 4 — Live verification | **BLOCKED** — `ECONNREFUSED 127.0.0.1:9224`; adapter attached-to-nothing and refused to launch a substitute |

**Bottom line:** the code and configuration are now exactly right for reusing one operator-owned Edge over CDP on port 9224, and the failure mode when CDP is absent is a loud, structured block with the real error string and no fallback browser. The one thing that cannot be produced from this side is the browser-side grant: on Edge 155 the default profile only exposes CDP after the operator ticks **"Allow remote debugging for this browser instance"** at `edge://inspect` → *Remote debugging*, which writes `DevToolsActivePort` — the file `attach_existing()` is now able to consume.

No browser was closed, restarted, relaunched or terminated; no profile was created or modified; no credentials, `.env` or tokens were touched; no messages were sent; no conversation was created; no repository task was executed; nothing was committed or pushed.
