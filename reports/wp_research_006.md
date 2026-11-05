# WP-RESEARCH-006 — Create Dedicated Isolated OpenCode Research Environment

## Exact paths created
- Research config directory: `C:\Users\user\.config\opencode-research\`
- Research agent: `C:\Users\user\.config\opencode-research\agents\research.md`
- Research OpenCode config: `C:\Users\user\.config\opencode-research\opencode.jsonc`
- Research workspace: `C:\Vijay_GitHub\opencode-research-workspace\` (empty)

## Agent configuration and effective permissions
- Default deny: `"*": "deny"` (both global and per-agent).
- Allowed: `websearch`, `webfetch`.
- Denied: `read`, `edit`, `bash`, `write`, `glob`, `grep`, `list`, `task`, `todowrite`, `external_directory`.
- Browser access: disabled (not in allow list).
- Agent mode: `subagent`.

## Workspace isolation details
- Dedicated empty directory: `C:\Vijay_GitHub\opencode-research-workspace`.
- No source files, credentials, or environment files.
- No shared writable directories with development workflows.
- Limitation: OS-level process isolation (user permissions) cannot be guaranteed on this Windows machine (same user identity); isolation relies on OpenCode config + separate port.

## Configuration validation results
- JSON valid (parsed successfully).
- Agent "research" present in config.
- Default deny confirmed: `permission["*"] == "deny"`.
- websearch: allow, webfetch: allow.
- All unapproved tools: deny.

## Controller endpoint readiness
- `OPENCODE_RESEARCH_BASE_URL` env var supported (defaults to empty; caller must set to `http://127.0.0.1:4098`).
- `OPENCODE_RESEARCH_AGENT` env var supported (default "research").
- `opencode_research_tools()` returns default allowlist (websearch+webfetch only).
- Existing dev endpoint (4097) and ChatGPT task behavior preserved.

## Development environment integrity checks
- Dev OpenCode config (`~/.config/opencode/opencode.jsonc`): unchanged (verified identical to prior state).
- Dev OpenCode server (4097): healthy, untouched.
- Controller (8799): healthy, untouched.
- Port 4098: free.
- No dev credentials or files copied to research workspace.

## Remaining security limitations
- Research server not started (no live validation). Tool enforcement not demonstrated against a running instance.
- Browser access disabled pending separate authorization.
- Network-level isolation not configured (relies on OpenCode tool allowlist).
- OS-level isolation not achievable (same Windows user).

## Confirmation
No services were started. No files modified in dev config or workspace. No credentials accessed. No commits or pushes.

## Verdict: A — READY FOR ISOLATED INSTANCE VALIDATION
Dedicated research config, agent, and workspace are created and validated. Controller can target the research endpoint via env vars. Port 4098 is free. Existing dev environment is untouched. Isolated-instance security validation (TEST-RESEARCH-ISOLATION-001) can now proceed once the operator authorizes starting the research server.