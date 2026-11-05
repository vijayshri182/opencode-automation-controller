# WP-RESEARCH-008 — Read-only Research Provider Readiness Diagnosis

Date: 2026-11-04
Repository: `C:\Vijay_GitHub\opencode-automation-controller` (branch `master`, no commits; all untracked)
Mode: **read-only diagnosis only**. No services started/stopped/restarted, no credentials accessed/copied/modified,
no `.env` or provider config changes, no purchases/subscriptions, no external communication, no commit/push.

---

## 1. Evidence-backed comparison of the two instances

### 1.1 Process / launch context

| Attribute | Development instance (4097) | Research instance (4098, when last run) |
|---|---|---|
| Binary | `opencode` CLI v1.18.30 | `opencode` CLI v1.18.30 |
| Command | `opencode serve --port 4097` (PID 29924, parent 32552) | `opencode serve --port 4098 --print-logs` (PID 4724 / 34100 / 28784 across runs) |
| Working directory | `C:\Vijay_GitHub\opencode-automation-controller` (and temp smoke dirs) | `C:\Vijay_GitHub\opencode-research-workspace` |
| `OPENCODE_CONFIG` | unset (loads `~/.config/opencode/opencode.jsonc`) | set to `C:\Users\user\.config\opencode-research\opencode.jsonc` |
| `OPENCODE_SERVER_PASSWORD` | set (auth enabled) | unset (unauthenticated loopback) |
| `OPENCODE_CLIENT` | `desktop` (inherited from launching shell) | `desktop` (inherited from launching shell) |
| `OPENCODE_PRINT_LOGS` | unset | set |
| Project ID | `global` (and `05f91c...` for research workspace) | `05f91c77d30f70863888e7851450a34afd82879c` |

Both instances share the same `~/.local/share/opencode/auth.json` (only provider `opencode-go`,
fields `key`/`type`) and the same global config `~/.config/opencode/opencode.jsonc`.

### 1.2 Configuration comparison

- **Dev config** (`~/.config/opencode/opencode.jsonc`): only `external_directory` allow entries;
  no model/provider configuration. Uses defaults.
- **Research config** (`~/.config/opencode-research/opencode.jsonc`): deny-all permission baseline +
  `websearch`/`webfetch` allow + `research` agent with tools allowlist. No model/provider configuration.
- **Global config** (`~/.config/opencode/opencode.jsonc`): identical for both (both load it; research
  values win on overlay). Neither config sets a default model or provider API key.

### 1.3 Provider resolution

- `opencode` (free) provider: `apiKey: "public"` (hardcoded in the provider definition, not from auth).
  Models: `big-pickle`, `flint-40b-free`, `deepseek-v4.1-flash-free`, `mimo-v2.6-flash-free`, etc.
- `opencode-go` (subscription) provider: `apiKey` from `auth.json` (fields `key`, `type`); connected on
  both instances. Models include `beam-free`, `gpt-5.6-luna`, `claude-haiku-5-5`, etc.
- Both instances report `CONNECTED = ['opencode', 'opencode-go']`.

### 1.4 Model availability (from provider list, captured during the Flint run)

- `opencode/big-pickle`, `opencode/flint-40b-free`, `opencode/deepseek-v4.1-flash-free`,
  `opencode/mimo-v2.6-flash-free` all resolve as available models on the research instance.
- `opencode-go/beam-free` resolves as available on the research instance (capabilities include
  `toolcall: true`).

### 1.5 Observed errors (from `reports/evidence/test_research_isolation_002*/serve.err.log`)

Every free-model attempt on the research instance (big-pickle ×5, deepseek, mimo, flint) failed with:
```
stream error ... providerID=opencode modelID=<model> ...
error.error="AI_APICallError: Free usage limit reached. Free models work in OpenCode
(https://opencode.ai); subscribe to OpenCode Go to keep going: https://opencode.ai/go"
```
The dev instance (4097) succeeded with `big-pickle` in the same time window
(`DEV_OK`, tokens input 108 / output 3; `CROSSDIR_OK` in the research workspace dir).

---

## 2. Exact provider error classification

- **Error type:** `AI_APICallError` (AI SDK call error) returned by the upstream `opencode.ai`
  inference endpoint (`https://opencode.ai/inference/openai/v1`).
- **Classification:** **Provider-side free-tier quota exhaustion** — not a client-side auth failure,
  not a model-not-found, not a permission denial, not a timeout, not an empty-output classification.
- **Scope:** affects **all** free `opencode` provider models uniformly on the research instance; not
  model-specific.
- **Surface:** the error appears only in the OpenCode server log (`serve.err.log` when `--print-logs`);
  the assistant message's `error` field is `null` and tokens are 0, so the API alone cannot classify it.

---

## 3. Root cause — ranked hypotheses

The exact server-side check cannot be determined from a read-only audit (no source access to the
upstream). Ranked hypotheses:

1. **(Most likely) Free-tier entitlement is bound to the desktop-managed instance identity.**
   The dev instance (4097) was launched under the OpenCode desktop app context (it carries the
   desktop app's session/license handshake), while the research instance is a CLI-launched process.
   Even though both inherit `OPENCODE_CLIENT=desktop` from the shell, the desktop app holds a
   cached free-usage entitlement/session token that a separately launched `opencode serve` does not
   receive. The upstream then treats the new instance as over-quota / unentitled.

2. **Per-project / per-installation quota bucketing.** The free tier may key quota on the OpenCode
   project ID (the research workspace maps to project `05f91c77...`, distinct from the dev project).
   A fresh project may start with zero free quota or a stricter bucket.

3. **Authentication-gated free tier.** The dev instance runs with `OPENCODE_SERVER_PASSWORD` set
   (authenticated server); the research instance is unauthenticated. The upstream may grant free
   usage only to authenticated/registered instances. (Less likely, but consistent with the data.)

4. **Cached warm state / prompt cache.** Dev responses show `cache.read` of 1792–9216 tokens,
   suggesting the dev instance has a warm prompt cache / entitlement cache that fresh instances lack.
   (Unlikely to fully explain 0 tokens on every attempt.)

The evidence that points to instance-identity rather than config: identical provider config, identical
auth.json, identical env (except password/config/print-logs), identical version, same machine and
account, same time window — yet one instance succeeds and the other fails on every free model.

---

## 4. Model availability findings

- Free `opencode` models resolve and are listed as available on the research instance; the failure
  happens at execution time (stream error), not at model resolution.
- `opencode-go/beam-free` (subscription-backed, `toolcall: true`) also resolves as available on the
  research instance and is the model the assistant itself runs on. It has not been executed on the
  research instance (no live test attempted, per boundaries). It is the most promising candidate to
  bypass the free-tier quota wall, subject to operator authorization (consumes Go subscription quota).
- Model availability does **not** differ by model within the free tier (all free models fail identically).

---

## 5. Safe remediation options and prerequisites

| Option | Description | Assessment |
|---|---|---|
| **A (recommended, operator-gated)** | Use a subscription-backed model (`opencode-go/beam-free`) on the research instance, which is not subject to the free-tier quota. Requires operator authorization (consumes Go quota) and a controlled, bounded test. | Bypasses the quota wall without changing config/auth. |
| B | Launch the research instance under the desktop app's management (so it inherits the free-usage entitlement/session). | May work but couples research isolation to the desktop app; changes launch procedure; needs operator approval. |
| C | Authenticate the research instance (`OPENCODE_SERVER_PASSWORD`) and re-test free models. | Tests hypothesis 3; low risk but requires a restart (operator-gated). |
| D | Inspect the upstream opencode.ai free-tier policy / account quota dashboard. | No code change; clarifies whether the account has any free quota left. |
| E | Subscribe to OpenCode Go (paid) for the research instance. | Costs money; operator decision only. |

Prerequisites for any live test: operator authorization, no service restart without approval, no
credential copying, no config changes, no subscription purchase.

---

## 6. Recommended next action

**CONDITIONALLY READY** — the research instance, configuration and isolation are sound; the only blocker
is the free-tier provider quota, which is environmental/account-level and not a defect in the
research config or executor. Recommended: operator authorizes a bounded live test using
`opencode-go/beam-free` (Option A) on the already-isolated research instance, without restarting or
reconfiguring any service, and reports the outcome. If the operator declines, keep all validation
mock-based and report the blocker.

---

## Final verdict

**CONDITIONALLY READY** — configuration and isolation verified; live execution blocked solely by the
OpenCode free-tier provider quota on the dedicated research instance. No code, config, credential or
service changes made in this audit.