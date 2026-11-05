# WP-421A — Reuse Existing Edge/CDP Browser and Palmistry Project Tab

- **Date:** 2026-11-02
- **Repo:** `C:\Vijay_GitHub\opencode-automation-controller` (branch `master`, no commits made)
- **Status:** implementation + mock verification **COMPLETE**; live verification **BLOCKED** (no CDP endpoint exists). No browser was launched.

---

## 1. Verdict

| Item | Result |
|---|---|
| New browser launch path removed from the attach flow | **PASS** (`edge_attach.py` has no launch API call; guarded by tests) |
| Attaches to existing CDP browser instead of launching | **PASS (mock)** — `chromium.connect_over_cdp` only |
| Reuses existing Palmistry Project tab without navigation | **PASS (mock)** |
| Reuses existing ChatGPT tab, navigates only when needed | **PASS (mock)** |
| Deterministic multi-tab handling | **PASS (mock)** |
| Clear blocked result when CDP fails / no suitable tab | **PASS (mock + live)** |
| Live attach to the running managed Edge (`9224`) | **BLOCKED — `ECONNREFUSED 127.0.0.1:9224`** |

**Acceptance criterion** (“attaches to the existing Edge process and reuses the existing Palmistry Project tab”) is **not yet demonstrated live**, because there is currently **no Edge process with remote debugging enabled**. The code path required is in place and unit-verified; the environment is missing the endpoint.

---

## 2. CDP endpoint used

| Endpoint | Source | Live probe |
|---|---|---|
| `http://127.0.0.1:9224` | WP-419/WP-421 managed port (`.edge-profile-automation`) | `ECONNREFUSED` |
| `http://127.0.0.1:9222` | `managed_edge.DEFAULT_CDP_PORT` (config default) | `ECONNREFUSED` |

Exact attach error (from `reports/execution/wp421a_live_evidence.json`):

```
Error: BrowserType.connect_over_cdp: connect ECONNREFUSED 127.0.0.1:9224
Call log:
  - <ws preparing> retrieving websocket url from http://127.0.0.1:9224
```

```
Error: BrowserType.connect_over_cdp: connect ECONNREFUSED 127.0.0.1:9222
Call log:
  - <ws preparing> retrieving websocket url from http://127.0.0.1:9222
```

`http://127.0.0.1:9224/json/version` → `Unable to connect to the remote server`.
Listener scan (ports 9220–9235) → **no listener**. `Get-NetTCPConnection -State Listen` shows no debugging port at all.

---

## 3. Existing browser / context / page discovery evidence (live)

| Check | Result |
|---|---|
| `msedge.exe` processes | 24 total; only **one** top-level browser process: **PID 2420**, created **23-10-2026 12:56**, command line `msedge.exe --no-startup-window /prefetch:5` — **no `--remote-debugging-port`**, default user-data-dir |
| `--user-data-dir=C:\Vijay_GitHub\opencode-automation-controller\.edge-profile` | Orphaned renderer/utility/crashpad children remain (parent PID 6300 no longer exists) — an earlier non-CDP launch that has since lost its browser process |
| `.edge-profile-automation` | **No owning process**, **no `SingletonLock`**, **no `DevToolsActivePort`** → clean, not attached, not locked |
| Browser/context/page enumeration | **Not possible** — `connect_over_cdp` fails before any context or page can be listed |

**Conclusion:** the “already-running managed Edge” that WP-421A assumes does not currently exist. The only live Edge is the operator’s normal browser, which was started **without** a debugging port and therefore **cannot** be attached to (CDP cannot be enabled post-start).

---

## 4. Was the existing Palmistry Project tab reused? Did anything navigate?

- **Reused:** not verified live (endpoint unreachable, so there were no contexts or tabs to reuse).
- **Navigation performed:** **none**. The attach attempt failed before `page.goto` could run; no URL was changed in any browser.
- **New browser launched:** **no.** Probe used only `playwright.chromium.connect_over_cdp()`; no `launch()`, no `launch_persistent_context()`, no `subprocess`, no new profile, no new window. Confirmed afterwards: the only top-level `msedge.exe` is still PID 2420 with creation time **23-10-2026**, i.e. no new browser process appeared.
- **Edge/CDP restarted or terminated:** no. No process was killed.
- **Credentials / `.env` / profile settings changed:** no.

---

## 5. Files and functions changed

### New: `src/opencode_bridge/edge_attach.py`
The only place where CDP attachment lives. **Contains no launch path.**

| Function | Purpose |
|---|---|
| `CDP_URL`, `PALMISTRY_PROJECT_URL`, `PALMISTRY_PROJECT_ID` | Fixed endpoint (`http://127.0.0.1:9224`, overridable by `EDGE_CDP_URL`) and the fixed Project entry point |
| `classify_tab(url, title, project_url)` | Pure ranker: `0` = project root or project conversation, `1` = any `chatgpt.com` tab, `9` = not eligible |
| `attach_existing_edge(cdp_url, project_url, playwright=None, wait_seconds, verify, navigate_if_needed)` | Connects over CDP, enumerates contexts/pages, picks the best tab deterministically (`rank`, `context_index`, `page_index`), navigates **only** a plain ChatGPT tab, verifies Project + auth + conversation list, returns a structured result. Never launches. |
| `_await_project_ready(page, navigated, wait_seconds, project_url)` | Bounded readiness wait (max `wait_seconds` after navigation, max 5 s for a reused tab) for `a[href*='/c/']` links + body text |
| `detach(result)` | `playwright.stop()` only — never `browser.close()` |

Blocked reasons (stable codes): `cdp_connect_failed`, `no_suitable_tab`, `navigation_failed`, `project_not_verified`, `not_authenticated`, `chatgpt_tab_not_on_project`, `playwright_unavailable`, `playwright_start_failed`.

### `src/opencode_bridge/browser_automation.py`
- `PlaywrightEdgeAdapter.__init__`: added `_attached` flag and `last_attach_info`.
- `PlaywrightEdgeAdapter.attach_existing(cdp_url, project_url, wait_seconds)`: reuses the running browser, binds `self._page` to the borrowed tab, stores non-serialisable objects out of `last_attach_info`.
- `PlaywrightEdgeAdapter.stop()`: when attached, **only** `playwright.stop()`; it does not close the borrowed context or page.

### `src/opencode_bridge/managed_edge.py`
- `CdpEdgeAdapter.__init__(..., attach_only: bool = False)`: attach-only mode.
- `CdpEdgeAdapter.attach_existing(...)`: attaches through the launcher’s CDP URL; records the borrowed page/context.
- `CdpEdgeAdapter.start()`: in attach-only mode it **never** calls `launcher.start()`; it raises `ManagedEdgeError` with the exact blocked reason instead.
- `CdpEdgeAdapter.stop()`: in attach mode disconnects Playwright only (no `browser.close()`, which can clear CDP-created contexts), and leaves Edge running.

---

## 6. Tests executed and results

New file: `tests/test_wp421a_cdp_attach.py` — **16 passed** (20.3 s).

The fakes raise `LaunchForbidden` on `launch()`, `launch_persistent_context()`, `new_page()` and `browser.close()`, so any regression into a launch path fails loudly.

| Test | Proves |
|---|---|
| `test_classify_tab_ranks` | Project / project-conversation / ChatGPT / other ranking |
| `test_attaches_instead_of_launching` | `connect_over_cdp("http://127.0.0.1:9224")` called; zero launch calls; `launched_new_browser=False` |
| `test_reuses_existing_project_tab_without_navigation` | Project tab selected, `navigated=False`, `page.navigations == []` |
| `test_chatgpt_tab_is_reused_and_navigated_when_needed` | Exactly one `goto(PROJECT_URL)` on the existing tab, no launch |
| `test_project_tab_preferred_over_plain_chatgpt_tab` | Cross-context preference for the project tab |
| `test_multiple_tabs_handled_deterministically` | Lowest `(rank, context_index, page_index)` wins, repeatably; other tabs untouched |
| `test_no_suitable_tab_is_blocked_not_replaced` | `no_suitable_tab`; no navigation, no new page, no launch |
| `test_cdp_failure_reports_exact_error_without_fallback_launch` | `cdp_connect_failed` + exact `ECONNREFUSED ...` string; zero launch calls |
| `test_unverified_project_blocks` | `project_not_verified` when navigation does not land on the project |
| `test_signed_out_tab_is_blocked` | `not_authenticated` on a sign-in page |
| `test_navigation_failure_is_blocked` | `navigation_failed` with the exact `net::ERR_ABORTED` message |
| `test_playwright_adapter_attach_existing_sets_page_and_disconnects_only` | Adapter binds the borrowed page; `stop()` stops Playwright, **does not close the tab** |
| `test_playwright_adapter_attach_failure_reports_blocked` | Blocked reason surfaced via `last_attach_info`, `_page is None` |
| `test_cdp_adapter_attach_only_never_calls_launcher_start` | `launcher.start()` monkeypatched to raise; attach-only `start()` still succeeds |
| `test_cdp_adapter_attach_only_raises_when_cdp_missing` | `ManagedEdgeError` containing `cdp_connect_failed` |
| `test_wp419_ui_navigation_preserved_and_no_direct_conversation_url` | WP-419 UI path still clicks the visible Project + conversation entries and performs **zero** `goto`/route navigation |

Regression run (`tests/` excluding the two `fastapi`-dependent modules):

```
1 failed, 64 passed in 172.56s
```

- Only failure: `tests/test_integration_opencode.py::test_integration_real_task` — a **live OpenCode API** integration test (empty assistant reply from the running server). It does not import `edge_attach`/browser code and is unrelated to this change.
- `tests/test_opencode_bridge_gui03.py` and `tests/test_opencode_bridge_mcp.py` remain uncollectable (`ModuleNotFoundError: No module named 'fastapi'`) — pre-existing environment gap, unchanged.

Earlier focused run (before the last regression run): `test_wp421a_cdp_attach.py` + `test_wp421_project_discovery.py` + `test_playwright_bridge_mock.py` + `test_browser_sandbox.py` + `test_chat_persistence.py` + `test_managed_edge_cdp.py` → **41 passed** (20.3 s + 20.9 s across the six files).

---

## 7. `--no-sandbox` investigation (carried from WP-420A, re-verified)

- The flag is **not** added by application code: `ManagedEdgeLauncher.start()` builds only `--remote-debugging-port`, `--user-data-dir`, `--no-first-run`, `--no-default-browser-check`.
- It comes from Playwright’s driver (`driver/package/lib/coreBundle.js`), which pushes `--no-sandbox` unless the launch option `chromiumSandbox` is `true`.
- Fix already applied in WP-420A: `PlaywrightEdgeAdapter.start()` passes `chromium_sandbox=True` (snake_case; `chromiumSandbox` raises `TypeError` in the Python API). `PlaywrightEdgeAdapter.start()` therefore no longer produces the warning.
- **WP-421A adds no launch path at all**, so it cannot introduce or re-introduce `--no-sandbox`. Attaching to an existing browser inherits whatever flags that browser was started with.
- The orphaned `.edge-profile` process tree still shows `--no-sandbox` in its command line because it was started by the pre-fix launch path. **It was not restarted or terminated** (prohibited), so the warning disappears only when that browser is next started by the fixed code.

---

## 8. Remaining blockers

1. **No CDP endpoint is running.** Nothing is listening on 9224 (or 9222). CDP cannot be enabled on an already-started browser, so the live acceptance criterion cannot be satisfied until a managed Edge exists.
   **Required operator action (one-time, outside this task):** start the managed browser with the automation profile and debugging port, e.g.

   ```
   "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe" ^
     --remote-debugging-port=9224 ^
     --user-data-dir="C:\Vijay_GitHub\opencode-automation-controller\.edge-profile-automation" ^
     --no-first-run --no-default-browser-check
   ```

   Then sign in to `chatgpt.com` and open the Palmistry Project once. No profile lock is present, so this start should be clean. After that, `attach_existing()` needs no further change and no launch.
2. **Port drift:** `managed_edge.DEFAULT_CDP_PORT = 9222` while WP-419/421A use **9224**. `edge_attach.CDP_URL` hardcodes 9224 (env-overridable). This inconsistency should be resolved deliberately rather than silently.
3. **Live Project reuse, tab enumeration, Project verification and conversation-list readiness remain unverified** — mock-verified only.
4. `fastapi` is not installed, so two test modules cannot be collected (pre-existing).

---

## 9. Scope compliance

- No `chromium.launch()`, no `launch_persistent_context()`, no equivalent launch call in the attach flow (enforced by tests).
- No new Edge process, profile, window or page created during this task.
- No Edge/CDP restart or termination; no OpenCode server, desktop app or worker restart.
- No credentials, `.env`, provider/model configuration or browser-profile settings changed.
- No messages sent to ChatGPT, no conversation created, no repository task executed from any captured content.
- No commits, no pushes. All work is uncommitted in the working tree.

**This task does not claim the end-to-end ChatGPT ↔ OpenCode loop is operational.**
