# TEST-RESEARCH-ISOLATION-002 — Model and Research Tool-Calling Preflight

Date/time: 2026-11-03 (IST: Tue Nov 03 ~23:14), DEV only.

## Objective
Validate whether the dedicated OpenCode research instance can run a usable model and actually
invoke the permitted research tools (`websearch` / `webfetch`) required by the research isolation
boundary, before attempting full negative/positive permission testing.

## Scope and safety constraints honoured
- DEV only; PROD untouched; controller 8799 and development OpenCode 127.0.0.1:4097 NOT configured,
  restarted, or mutated (no `/config` write to dev; no restart).
- Research instance launched fresh on `127.0.0.1:4098` (PID 34100, `opencode serve --port 4098
  --print-logs`, working directory `C:\Vijay_GitHub\opencode-research-workspace`,
  `OPENCODE_CONFIG=C:\Users\user\.config\opencode-research\opencode.jsonc`, unauthenticated
  loopback only, no browser, no shell tools used).
- No credentials accessed, stored, printed, or modified. No .env change. No provider/model change.
- No live strategy execution, no broker write, no session launch from the controller.

## Setup / preflight (PASS)
- Controller health: `http://127.0.0.1:8799/health` -> `{"ok": true, "service": "mcp_server"}`.
- Development OpenCode health: `http://127.0.0.1:4097/global/health` -> `{"healthy":true,"version":"1.18.30"}`.
- Port 4098 was free before launch; research instance healthy on 4098, version 1.18.30.

## Effective configuration verification (PASS, read-only via `/config`, `/agent`, `/api/provider`)
- Server-level `permission`: `read/edit/glob/grep/list/bash/task/external_directory/todowrite/webfetch/websearch/write: deny`,
  `* : deny`; only `websearch` and `webfetch` allowed; `external_directory: deny`.
- Agent `research` present via `/agent` with `mode: all`; agent tools map: `websearch: true`,
  `webfetch: true`, all other tools `false`; agent-level `permission` mirrors deny-all with the two
  allows.
- Model default resolved to `null`; available `opencode` provider models include `big-pickle` plus
  other free models (`deepseek-v4.1-flash-free`, `mimo-v2.6-flash-free`, `flint-40b-free`, ...).

## Model execution attempts — BLOCKED
All free-tier `opencode` provider models were attempted on the research instance; every stream failed
with the same provider error, before any assistant output/tool part was produced:

1. `big-pickle` (requested via adapter with `agent=research`, allowed tools = websearch/webfetch,
   `research_mode=True`), prompt requiring websearch:
   - Session `ses_e5d7df388ffe5tSXoqBldc9FLA`, agent `research`, submitted via
     `POST /session/{id}/prompt_async` -> bounded poll (deadline 120 s, poll 4 s, 30 polls) ended at
     elapsed 121.33 s, final assistant text `""`, `empty_output: true`, `timed_out: true`.
   - Server log: `message="stream error" providerID=opencode modelID=big-pickle session.id=... error.error="AI_APICallError: Free usage limit reached. Free models work in OpenCode (https://opencode.ai); subscribe to OpenCode Go to keep going: https://opencode.ai/go"`.
2. `big-pickle`, minimal prompt (`Reply with exactly: RESEARCH_OK`), agent `research`:
   - Session `ses_e5d7bdf0dfferTza2FYkl3LkFX`, elapsed 60.54 s, final text `""`, timed out.
   - Same `Free usage limit reached` stream error.
3. `big-pickle`, agent `build` (default agent) with default tool set, in research workspace:
   - Session `ses_e5d7964e3ffes6Jivhv3X0YkZW`, elapsed 92.7 s, final text `""`, timed out.
   - Same `Free usage limit reached` stream error -> failure is not specific to the `research` agent.
4. `deepseek-v4.1-flash-free` -> same error (session `ses_e5d76b643ffeE64O9QsVsbqmNP`).
5. `mimo-v2.6-flash-free` -> same error (session `ses_e5d75f94fffeV3PJ3M1MgZHe1R`).

No websearch/webfetch tool invocation was ever actually executed (no successful model output /
tool part was generated before the provider stream error).

## Empty-response / deadline handling — VERIFIED
- With every model failing, the adapter correctly returned an empty final assistant text and the
  bounded poll/deadline logic flagged `empty_output` and `timed_out` rather than treating the turn as
  successful. No infinite polling occurred (30 polls / 121 s and 15 polls / 60 s, both within deadline).
- Provider error text was observable only through the server log (`serve.err.log`), not through the
  assistant message `error` field / token counters (assistant tokens input/output 0, output 0).

## Contrasting evidence (dev instance, same model)
- Development OpenCode 127.0.0.1:4097 (v1.18.30, same auth/provider state, same version) succeeded moments
  earlier/later with `big-pickle`:
  - `Reply with exactly: DEV_OK` -> assistant text `DEV_OK`, tokens input 108 / output 3.
  - `Reply with exactly: OK4097` in the same window -> ok; plus cross-directory test with the working
    prompt directory `C:\Vijay_GitHub\opencode-research-workspace` -> ok.
- Conclusion (not a defect in the research config): the free-tier model entitlement appears bound to the
  already-running development/managed server instance context, not to a freshly launched
  `opencode serve` process started from this shell, nor to the effective research config alone.

## Verdict
- **BLOCKED — no usable model execution on the dedicated research instance in this test.**

The research isolation boundary (deny-all + allowlist) could not be exercised end-to-end with a working
model. The preflight therefore could not validate that permitted research tools are actually invoked and
that denied tools are actually refused at execution time.

### Rerun verdicts (2026-11-03)
- **big-pickle rerun evidence**: BLOCKED — all attempts (`big-pickle` ×5, incl. agent `research` and
  default `build`) failed with `AI_APICallError: Free usage limit reached`; no tool invocation executed.
- **Flint 40B Free rerun evidence**: **BLOCKED** — all three runs (text-only, websearch, webfetch) failed
  with the same `AI_APICallError: Free usage limit reached` (provider `opencode`, model `flint-40b-free`);
  no text output, no tool calls, bounded polling/deadline handling confirmed.

### Final verdict (as of this rerun)
- **BLOCKED — no usable model execution** on the dedicated research instance, with both `opencode/big-pickle`
  and `opencode/flint-40b-free`. No permitted-tool invocation or denial behaviour has yet been observed.

## Limitations / non-claims
- The free-usage error classification is from the explicit server-side `AI_APICallError` text; it was not
  derived from empty output alone.
- Actual per-agent tool denial and permitted-tool invocation remain unverified at the model layer; they
  should be re-run once a working model is available on the research instance.
- No browser, shell, filesystem-write tool, credential access, or external-message action was performed.

## Flint rerun — `opencode/flint-40b-free` (controlled rerun, 2026-11-03)

Triggered by operator instruction to rerun TEST-RESEARCH-ISOLATION-002 with **Flint 40B Free**
(model `opencode/flint-40b-free`) instead of the earlier `opencode/big-pickle`. Reused the existing
report structure and probe where possible; no scope expansion beyond the test.

### 2.1 Preflight (re-run) — PASS
- Controller `http://127.0.0.1:8799/health` -> `{"ok": true, "service": "mcp_server"}`.
- Dev OpenCode `http://127.0.0.1:4097/global/health` -> `{"healthy":true,"version":"1.18.30"}`.
- Port 4098 free at start of run; dedicated research instance started on 4098 (PID 4724,
  `opencode serve --port 4098 --print-logs`, cwd `C:\Vijay_GitHub\opencode-research-workspace`,
  `OPENCODE_CONFIG=C:\Users\user\.config\opencode-research\opencode.jsonc`, unauth loopback).
- Effective config re-verified on the fresh instance: server-level permission deny-all with
  `websearch: allow` / `webfetch: allow` / `* : deny` / `external_directory: deny`; agent `research`
  (`mode: all`) with tools allowlist (websearch/webfetch true, all other tools false) and agent-level
  permission mirroring the deny map.

### 2.2 Exact model identifier
- Exact model requested and used: `opencode/flint-40b-free` (providerID `opencode`, modelID
  `flint-40b-free`; Flint 40B Free). Confirmed present in the installed OpenCode version's provider
  model list (v1.18.30). No silent substitution; no other model attempted in this rerun.

### 2.3 Execution results (all three runs — no usable model output)

1. **flint-text-only**: session `ses_e5d63ed27ffeZg5LMEJC2OX453`; prompt `Reply with exactly: FLINT_TEXT_OK`;
   elapsed 93.28 s, polls 23; final text `""`, `empty_output: true`, `timed_out: true`; `tool_calls: []`.
2. **flint-websearch**: session `ses_e5d6280d9ffeCWp9j8d6oRjj0s`; elapsed 181.74 s, polls 45;
   final text `""`, empty, timed out; no tool calls.
3. **flint-webfetch**: session `ses_e5d5fbb0cffehjRVVHecERCwEh`; elapsed 92.91 s, polls 23;
   final text `""`, empty, timed out; no tool calls.

All runs: assistant tokens input/output `0`, output `0`, `parts: []` (no text, no tool parts produced).
Probe artifacts: `reports/evidence/test_research_isolation_002_flint/flint_probe_results.json`.

### 2.4 Error classification and deadline behavior (Flint rerun)
- For all three runs, server logs (`reports/evidence/test_research_isolation_002_flint/serve.err.log`):
  `message="stream error" providerID=opencode modelID=flint-40b-free ... error.error="AI_APICallError:
  Free usage limit reached. Free models work in OpenCode (https://opencode.ai); subscribe to OpenCode
  Go to keep going: https://opencode.ai/go"`.
- Error classified as **provider/quota-level** (`AI_APICallError: Free usage limit reached`), not a
  model-name or tool-denial error; the error was not inferred from empty output alone.
- Bounded polling / deadline handling re-confirmed: adapter returned empty final text and flagged
  `empty_output` + `timed_out`; polls bounded by deadline (23/45/23 polls). No infinite polling.
- Actual websearch/webfetch tool invocation could **not** be verified (no model output/tool part).

### 2.5 Flint rerun conclusion and verdict
- Flint 40B Free also could **not** execute on the dedicated research instance in this environment
  (`Free usage limit reached` — same provider/quota class as the earlier `big-pickle` attempts).
- The blocker is therefore **not model-specific**; it is the same free-tier execution entitlement
  problem observed with the research instance.

## Cleanup performed
- Research instance stopped (`taskkill -Force`): PID 34100 (big-pickle run) terminated; port 4098 released.
- Research instance stopped (`taskkill -Force`): PID 4724 (Flint rerun) terminated; port 4098 released.
- Development OpenCode (4097 / 4096) and controller (8799) left running, unmutated, unconfigured.

## Artifacts
- Evidence logs (big-pickle run): `reports/evidence/test_research_isolation_002/serve.out.log`, `serve.err.log`
- Evidence logs (Flint rerun): `reports/evidence/test_research_isolation_002_flint/serve.out.log`, `serve.err.log`, `flint_probe_results.json`
- Probe: `scripts/tmp_iso002_probe.py`
- Flint rerun probe: `scripts/tmp_iso002_flint_probe.py`, `scripts/tmp_iso002_flint_summary.py`
- Prior related reports: `reports/wp_research_001.md`, `reports/wp_research_005.md`, `reports/wp_research_006.md`,
  `reports/test_opencode_text_001.md`

## Next concrete action (operator-gated)
- Decide how the research instance obtains usable model quota (OpenCode Go subscription / credential
  provisioning; or a research server attached to a source with free-tier entitlement).
- After provisioning, re-run this preflight (research instance restart may be required by entitlement
  semantics) and then proceed to permitted-tool invocation + negative-permission tests.
