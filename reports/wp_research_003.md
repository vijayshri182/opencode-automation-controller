# WP-RESEARCH-003 — Bounded Read-Only Research Execution Worker

## Verdict: BLOCKED

## Technical limitation (root cause)
The OpenCode adapter (`src/opencode_bridge/opencode_adapter.py`) is an HTTP client that:
- creates sessions (`POST /session` with title/directory),
- submits prompts (`POST /session/{id}/prompt_async` with parts/model),
- reads messages (`GET /session/{id}/message`).

It has **no parameter or mechanism to restrict which tools OpenCode may invoke**. OpenCode's tool set (websearch, webfetch, browser, bash, file writes, etc.) is determined by the OpenCode server's own configuration/agent, not by the client adapter. The adapter only submits text prompts and reads results; it cannot enforce an allowlist or denylist at the execution boundary.

Consequently, a "read-only research execution profile" cannot be enforced by the controller with the current adapter. Any restriction would be prompt-level instruction only, which the task explicitly forbids claiming as secure ("Do not implement a prompt-only substitute and call it secure").

## What was inspected
- `opencode_adapter.py`: OpenCodeAdapter (create_session, send_prompt_async, get_messages, abort, health). No tool-policy parameter.
- `executors.py`: TaskControllerExecutor submits prompts via the adapter; no tool restriction.
- `orchestrator.py` / `contracts.py`: WP-RESEARCH-002 contracts and persistence (research_tasks table, MCP tools) are in place.
- OpenCode server API (port 4097): session creation accepts only title/directory; prompt submission accepts parts/model. No tool-allowlist field observed.

## What exists (from WP-RESEARCH-002)
- Research task contracts (`research_task`, `validate_research_task`, `research_result`, `validate_research_result`).
- `research_tasks` table + CRUD methods.
- MCP tools: `submit_research_task`, `get_research_task_status`, `get_research_task_result` (22 tools total).
- Tasks persist in `pending` status. Execution wiring is the missing piece.

## Why execution worker was NOT implemented
Implementing a worker that creates an OpenCode session, submits a research prompt, and stores the result would inherently rely on OpenCode's own tool selection, which includes potentially side-effecting tools (bash, file writes). Without boundary enforcement, the worker cannot guarantee read-only behavior. Per the task's safety instruction ("If OpenCode cannot provide enforceable restrictions using the current adapter, stop at that boundary"), I stopped rather than implement an unverifiable worker.

## Known limitations
- No read-only tool allowlist enforceable at the OpenCode boundary via the current adapter.
- No execution worker, timeout enforcement, cancellation, or result collection wired.
- Prompt-level restrictions are insufficient and are not claimed as secure.

## Required to unblock
Operator must determine whether OpenCode supports per-session or per-request tool restrictions (e.g., a `tools` field in session creation or prompt submission, or a separate sandboxed OpenCode instance with only websearch/webfetch/browser enabled). If supported, the adapter must be extended to pass the allowlist and the worker can be implemented. If not, a sandboxed OpenCode deployment (restricted tool set at server level) is required.

## Files changed
- None. No code changes, no tests, no commits. Only this report added.

---
*No execution worker implemented. No services started. No live research performed. No commits.*