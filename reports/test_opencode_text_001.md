# TEST-OPENCODE-TEXT-001 — Controller-to-OpenCode Basic Text Round Trip

Date: 2026-11-03
Repository: `C:\Vijay_GitHub\opencode-automation-controller` (DEV only)
Method: existing `OpenCodeAdapter` against the existing development OpenCode server.
No service was started, stopped, or restarted. No configuration or source file was modified.

## 1. Health verification (no restart)

| Component | Endpoint | Result |
|---|---|---|
| Controller MCP server | `http://127.0.0.1:8799/health` | `{"ok": true, "service": "mcp_server"}` |
| OpenCode development server | `http://127.0.0.1:4097` | `{"healthy":true,"version":"1.18.30"}` |
| Research server (4098) | — | Not used (reserved for later isolated validation) |

## 2. Session creation

- Adapter: `OpenCodeAdapter(base_url="http://127.0.0.1:4097")`
- Adapter state: `research_mode=False`, `agent=None`, `tools=None` (development defaults)
- Working directory: `C:\Vijay_GitHub\fno-ai-paper-trading-dev`
- Session ID: `ses_e5d80a12fffeF60OQcjjZCYEQR`
- HTTP status: session created successfully (adapter returned a session object with `id`)
- Agent on session: `build` (the development agent — **not** `research`)

## 3. Prompt submission

Exact prompt sent:

```
Hello world. Reply with exactly: Hello from OpenCode.
```

Submission endpoint: `POST /session/{id}/prompt_async` (existing adapter method `send_prompt_async`).
Prompt accepted; user message persisted as `msg_1a27f6264001xFgAmzI8T5ScXx`.

## 4. Response retrieval

Polled with the existing `get_messages` + `OpenCodeAdapter.extract_final_assistant` path.

Assistant message: `msg_1a27f6b47001QrHewrA1sFd8KJ`

| Field | Value |
|---|---|
| role | `assistant` |
| agent | `build` |
| providerID | `opencode` |
| modelID | `big-pickle` |
| tokens | input 7538, output 6, total 9336, cache read 1792 |
| cost | 0 |
| text part | `Hello from OpenCode.` |

## 5. Exact-match verification

```text
extract_final_assistant(msgs) -> 'Hello from OpenCode.'
response.strip() == "Hello from OpenCode."  ->  True
```

## 6. Recorded execution details

| Item | Value |
|---|---|
| OpenCode endpoint | `http://127.0.0.1:4097` |
| Session ID | `ses_e5d80a12fffeF60OQcjjZCYEQR` |
| Request status | accepted (`prompt_async` returned 2xx) |
| Response status | retrieved (assistant text part present) |
| Response text | `Hello from OpenCode.` |
| Execution duration | 13.1 s (session create → response retrieved) |
| Errors | none on the successful attempt (see finding below) |

## 7. Confirmation of endpoint / agent / queue isolation

- `OPENCODE_RESEARCH_BASE_URL` is empty (`''`), so nothing targeted `http://127.0.0.1:4098`.
- `adapter.research_mode` is `False`; `adapter.agent` is `None`, `adapter.tools` is `None`.
- Session was created on the development server and recorded agent `build` for both messages — no `research` agent selection occurred.
- No research task was created or submitted: `research_tasks` table row count = **0** after the test.
- No web search was performed by the controller; the prompt did not request research.

## 8. Finding — default free model quota exhausted

The **first** attempt used the adapter's previous default model `opencode/beam-free`.
That attempt produced an assistant message with **0 tokens and no text parts**.
The OpenCode server log records the actual cause:

```text
level=ERROR message="stream error" providerID=opencode modelID=beam-free
  error.error="AI_APICallError: Free usage limit reached. Free models work in OpenCode
  (https://opencode.ai); subscribe to OpenCode Go to keep going: https://opencode.ai/go"
```

The same log also shows repeated `AI.Error.QuotaExceeded: Go usage limit exceeded`
for other sessions on this machine during the same period.

The retry with an available model (`opencode/big-pickle`) succeeded on the first poll
interval. This is a **provider quota condition, not a controller or adapter defect**.
It does, however, mean any future automated run that relies on a free model can
silently produce an empty assistant message unless the failure is detected:

- The adapter's `get_messages`/`extract_final_assistant` path returns `''` for a
  quota-failed turn, which is indistinguishable from "model still working" unless a
  timeout is applied.
- The quota error appears only in the OpenCode server log, not in the message payload
  returned by the adapter.

Recommended (not implemented in this test): treat an assistant message with
`tokens.output == 0` and an empty `parts` list, older than the poll deadline, as an
execution failure rather than a timeout.

## 9. Regression / preservation checks

| Check | Result |
|---|---|
| Controller still healthy after test | PASS (`{"ok": true, "service": "mcp_server"}`) |
| Development OpenCode server still reachable | PASS (1.18.30, unchanged) |
| Any service started/stopped/restarted | NO |
| Configuration or source modified | NO |
| Research tasks created | NO (0 rows) |
| Credentials accessed or changed | NO |
| Emails / external messages sent | NO |
| Commits / pushes | NO |

## Verdict: PASS

The controller's existing OpenCode adapter successfully created a session on the
development OpenCode server, submitted the exact prompt, retrieved the assistant
response, and the returned text matched exactly:

```
Hello from OpenCode.
```

Caveat carried forward: the default free model `opencode/beam-free` currently returns
an empty assistant turn because its usage limit is exhausted. The round trip was
verified with `opencode/big-pickle`. Empty-output detection should be added before any
unattended automation depends on this path.
