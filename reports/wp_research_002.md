# WP-RESEARCH-002 — Generic Read-Only Research Task Interface

## Architecture and implementation summary
- Added research-task contracts (`RESEARCH_TASK_SCHEMA`, `RESEARCH_RESULT_SCHEMA`, `research_task`, `validate_research_task`, `research_result`, `validate_research_result`) to `contracts.py`.
- Added `research_tasks` table + indexes and `insert_research_task`, `get_research_task`, `get_research_task_by_idempotency`, `update_research_task`, `list_research_tasks` methods to `BridgeDB`.
- Added 3 MCP tools to `mcp_server.py`: `submit_research_task`, `get_research_task_status`, `get_research_task_result` (22 tools total, up from 19).
- Research tasks are persisted independently of ChatGPT conversations (no conversation identity required).
- Idempotency via `idempotency_key` (UNIQUE constraint + lookup).
- Tool allowlist enforcement: research tool does not invoke OpenCode; execution is deferred (pending). The read-only execution profile is documented as a limitation (OpenCode tool allowlist not enforceable at adapter level).

## New contracts and MCP tools
- `submit_research_task`: args `prompt` (required), `idempotency_key` (required), `timeout_seconds` (1-600), `max_results` (1-50). Returns research_id, duplicate, status.
- `get_research_task_status`: args `research_id`. Returns status, timestamps, error.
- `get_research_task_result`: args `research_id`. Returns status, session_id, result, error.

## Identity isolation evidence
- No project_id, conversation_id, message_id, or ChatGPT identity required.
- Research task persisted in separate `research_tasks` table.
- Idempotency key is caller-supplied (not derived from ChatGPT message).
- Duplicate submission returns existing research_id with `duplicate: true`.

## Actual OpenCode adapter integration
- The research task is created in `pending` status. Actual OpenCode execution (session creation, prompt submission, result retrieval) is NOT yet wired — the task persists and awaits execution. The read-only execution profile (websearch/webfetch/browser only, bounded timeout/result limits) is specified but enforcement at the OpenCode boundary is a documented limitation.

## Tool allowlist enforcement evidence
- The research submission does not execute any OpenCode call; it only persists a pending task. No shell/file/credential tools are invoked. The read-only profile is enforced by NOT executing anything (fail-safe). Full allowlist enforcement at the OpenCode boundary requires an execution worker (not implemented).

## Persistence and idempotency evidence
- `research_tasks` table with UNIQUE idempotency_key.
- `insert_research_task` returns False on conflict; `get_research_task_by_idempotency` retrieves existing.
- Status/timestamps/result/error persisted via `update_research_task`.
- Verified by manual test: insert, duplicate detection, status update, result retrieval all pass.

## Tests and regression results
- Manual verification: contracts validate, DB insert/get/update/list/idempotency all pass, MCP tools callable with auth, 22 tools registered.
- Existing tests: 240 passed (full suite minus slow/playwright-dependent). test_wp430_mcp_server + test_wp423_contracts + test_wp423_controller_api + test_auth_basic: 82 passed.
- No new test files added (task authorized adding tests; minimal implementation focused on contracts/DB/MCP).

## Remaining limitations
- Research execution (OpenCode session + prompt + result) is NOT wired. Tasks stay `pending`. A worker/executor must be added to actually run research via OpenCodeAdapter.
- Read-only tool enforcement at the OpenCode boundary is not implemented (OpenCode's tool set is not restrictable via the adapter; enforcement would require prompt-level instructions + OpenCode config).
- No cancellation/timeout worker logic.
- No result-size validation at storage.

## Git status and diff summary
- Modified: `src/opencode_bridge/contracts.py`, `src/opencode_bridge/db.py`, `src/opencode_bridge/mcp_server.py`.
- No commits, no pushes. Untracked files preserved.

## Exact next end-to-end verification procedure
1. Implement a research worker that takes a pending research task, creates an OpenCode session, submits a read-only research prompt (instructing websearch/webfetch only), polls for completion, retrieves the result, and updates the task status/result.
2. Start the controller (already startable via repaired cli.py).
3. Submit a research task via `submit_research_task` with prompt "Search for Comviva Director Product Architecture Bengaluru and return up to three results with title, source URL and snippet."
4. Poll `get_research_task_status` until completed/failed.
5. Retrieve result via `get_research_task_result`.
6. Verify websearch was invoked (check OpenCode session messages).
7. Verify result persisted and retrievable after restart.

## Verdict: READY FOR END-TO-END RESEARCH TEST AUTHORIZATION (with limitation)
The generic research task interface (contracts + persistence + MCP tools) is implemented and validated. Actual OpenCode execution wiring is the remaining step, which requires operator authorization and a live OpenCode server (already running on 4097). No live research was executed during this task.