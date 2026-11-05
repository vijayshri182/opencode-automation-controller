# WP-RESEARCH-005 — Dedicated Research Agent Integration and Isolation Configuration

## Files changed
- `src/opencode_bridge/opencode_adapter.py` — extended `OpenCodeAdapter.__init__` with `agent`, `tools`, `research_mode` params; `create_session` and `send_prompt_async` now accept and pass `agent`/`tools` to the OpenCode API body. Backward-compatible (defaults preserve existing behavior). `MockOpenCodeAdapter` updated.
- `src/opencode_bridge/config.py` — added `opencode_research_base_url()`, `opencode_research_agent()`, `opencode_research_tools()` (default allowlist: websearch+webfetch only, all else denied).
- `config/research_agent.md` — new dedicated research agent definition with deny-all baseline + allow websearch/webfetch, browser disabled.
- `tests/test_wp_research_005.py` — 12 new tests.

## Adapter changes
- `OpenCodeAdapter` now supports `base_url`, `agent`, `tools`, `research_mode` constructor params.
- `create_session(title, directory, agent=None)` passes agent to body.
- `send_prompt_async(session_id, text, model, directory, agent, tools)` passes agent/tools to body, falling back to instance defaults.
- Research mode flag does not change defaults; caller must explicitly set research endpoint/agent/tools.
- Fail-closed: if research endpoint unavailable, adapter still resolves to dev URL (caller must validate research_mode + separate URL). Documented.

## Research configuration
- `OPENCODE_RESEARCH_BASE_URL` env var (separate endpoint, no fallback to dev when set by caller).
- `OPENCODE_RESEARCH_AGENT` env var (default "research").
- `opencode_research_tools()` returns default allowlist: websearch+webfetch True, bash/write/edit/read/glob/grep/list/task/todowrite False.
- `config/research_agent.md`: markdown agent with permission `*: deny`, websearch/webfetch allow, all others deny; tools matching.

## Permission policy
- Default deny (`"*": "deny"`) with explicit allow for websearch, webfetch.
- Browser disabled initially (deny).
- Shell, file write/edit, read, glob, grep, list, task, todowrite all denied.
- Per-request `tools` field can further restrict but cannot weaken server-side deny rules.

## Isolation preparation
- Separate research server port/config directory/workspace/env vars documented.
- No access to dev workspace (external_directory not granted for research instance).
- No shared writable resources.
- Explicit endpoint configuration via `OPENCODE_RESEARCH_BASE_URL`.
- Isolation requirements not guaranteed by OpenCode config alone: network-level isolation and OS-level process separation require operator setup (separate OpenCode instance).

## Automated test results
- `test_wp_research_005`: 12 passed.
- Regression: `test_wp430_mcp_server` + `test_wp423_contracts` + `test_wp423_controller_api` + `test_auth_basic` + `test_wp425_opencode_execution` + `test_wp427_session_directory`: 109 passed.
- Full suite (excluding slow/playwright): 252 passed.

## Remaining security limitations
- Read-only enforcement at the OpenCode boundary is configured but not demonstrated (no isolated instance tested). Per WP-RESEARCH-004 verdict B.
- Research execution worker not implemented (no actual task execution).
- Browser access disabled pending separate authorization.
- No network-level isolation verified.

## Exact instructions for separately authorized isolated-instance test
1. Create `~/.config/opencode/agents/research.md` from `config/research_agent.md`.
2. Start a second OpenCode instance on a separate port with restricted config: `opencode serve --port 4098 --config /path/to/research_config.json`.
3. Set `OPENCODE_RESEARCH_BASE_URL=http://127.0.0.1:4098`.
4. Implement research worker using `OpenCodeAdapter(base_url=research_url, agent="research", tools=opencode_research_tools(), research_mode=True)`.
5. Run security test matrix (shell, file write, read, secret access, unapproved tools, prompt override, browser, session isolation).
6. Only then enable generic research execution.

## Verdict: A — READY FOR ISOLATED INSTANCE VALIDATION
Configuration and adapter extension are complete. Research endpoint/agent/tool restrictions are explicitly configured with default-deny. Existing ChatGPT task behavior preserved (backward-compatible). No services started, no live research, no commits. Isolated-instance security validation is the remaining step.