# WP-RESEARCH-004 — OpenCode API Research Isolation & Security Feasibility Audit

## 1. Installed OpenCode version
- OpenCode server: **1.18.30** (verified via `GET /global/health` on port 4097).
- Config: `~/.config/opencode/opencode.jsonc` (permission + external_directory allowlists).

## 2. Actual server-side permission capabilities
OpenCode supports a server-side permission model:
- Global `permission` object: tool-name → action (`allow`/`ask`/`deny`) or granular patterns.
- Per-agent override via `agent.<name>.permission` (merged; agent rules take precedence).
- Per-agent `tools` field: enable/disable specific tools (`true`/`false` or `{"*": false}`).
- Markdown agent files (`~/.config/opencode/agents/<name>.md`) with frontmatter permissions.
- Permission keys are matched as wildcards against tool names (built-ins, custom, MCP).
- Explicit `deny` rules are enforced server-side (not prompt-level).
- `"*": "deny"` baseline + explicit allows creates a true allowlist.
- Auto-approve (`--auto`) only changes requests that would otherwise `ask`; explicit `deny` still enforced.

**Enforcement is server-side**, not prompt-level. The prompt body can also pass `tools: {name: bool}` and `agent: <name>` per request (per OpenCode API docs for `/session/:id/message` and `/session/:id/prompt_async`).

## 3. API session and agent permission behaviour
- `POST /session/:id/message` and `POST /session/:id/prompt_async` body accepts: `messageID?`, `model?`, `agent?`, `noReply?`, `system?`, `tools?`, `parts`.
- The `tools` field enables/disables tools for that prompt.
- The `agent` field selects which agent's permission profile applies.
- Agent switching mid-session supported via `POST /session/:id/agent`.
- Therefore, a research session can be created with a restricted agent, and each prompt can additionally pass a `tools` allowlist.

## 4. Dedicated-instance feasibility
- OpenCode supports separate config files (per-directory or `OPENCODE_CONFIG` env var) and separate ports (`opencode serve --port`).
- Separate agent definitions can be loaded from `~/.config/opencode/agents/` or config.json `agent` key.
- A dedicated instance can expose only approved tools via an agent with `"*": "deny"` + explicit allows.
- Environment variables and credentials can be isolated via separate `.env`/env vars (controller already uses `.env` loading).
- The instance can operate without access to the development workspace (external_directory permission scoped to research paths).
- Network access: OpenCode tools (websearch/webfetch) use their own network; cannot be network-restricted at OpenCode level, but filesystem/shell can be denied.
- Independent start/stop: yes (separate process/port).

## 5. Proposed isolated architecture
```
[AI Career Agent] -> [Controller MCP] -> [Research OpenCode Server (port N, separate config)]
                                          Agent: "research" (permission: * deny, websearch/webfetch/browser allow)
                                          tools: {websearch: true, webfetch: true, browser_*: true, bash: false, write: false, edit: false, ...}
```
- Existing dev OpenCode (4097) untouched.
- New research OpenCode instance on a separate port (e.g., 4098) with a restricted agent config.
- Controller adapter configured via env (`OPENCODE_RESEARCH_BASE_URL`) to point to the research instance.
- Reuse existing `OpenCodeAdapter` (create_session, send_prompt_async, get_messages) with added `agent`/`tools` params.

## 6. Allowlist and denylist enforcement analysis
**Enforceable at the server boundary** via:
1. Per-agent `permission` config: `"*": "deny"` baseline + explicit `allow` for websearch/webfetch/read (if needed).
2. Per-request `tools` field: disable all except approved.
3. `deny` rules are server-enforced (not prompt-level). Explicit deny cannot be overridden by prompt.

**Limitation**: `ask` mode prompts for approval (not suitable for autonomous). For autonomous research, use `allow` for approved tools and `deny` for everything else. The `*` wildcard deny ensures unknown tools are blocked.

**Prompt injection**: a submitted prompt cannot weaken `deny` rules (server enforces). It also cannot enable denied tools via the `tools` field if the server-side agent permission denies them (agent rules take precedence for deny).

## 7. Threat model and security test matrix

| # | Test | Expected result | Enforcement mechanism | Verification | Requires isolated runtime |
|---|------|-----------------|----------------------|--------------|--------------------------|
| 1 | Invoke shell (bash) | Denied | agent permission `bash: deny` + tools field | OpenCode returns permission denied / tool not available | Yes |
| 2 | Write a file | Denied | `edit: deny`, `write: deny` | Tool unavailable or denied | Yes |
| 3 | Read controller/dev workspace files | Denied | `external_directory: deny` (no allow paths) + `read` deny | Denied | Yes |
| 4 | Access env secrets | Denied | No shell/read tools; agent can't read .env | Denied | Yes |
| 5 | Invoke unapproved MCP tool | Denied | `mymcp_*: deny` or tool not registered | Denied | Yes |
| 6 | Override permissions via prompt | Denied (deny rules enforced) | Server-side permission merge; agent rules take precedence | Denied | Yes |
| 7 | Browser form submission | Denied | browser tool deny or no browser tool enabled | Denied | Yes |
| 8 | Access another session's resources | Denied (session isolation) | OpenCode session scoping | Denied | Yes |
| 9 | Access dev OpenCode server from research env | N/A (separate process/instance) | Network/process isolation | N/A | Yes |
| 10 | Escape execution limits | Denied (timeout/result-size enforced by controller) | Controller-side limits | Enforced | Partial (controller) |

All tests require a future isolated runtime (disposable OpenCode instance with restricted agent config). None performed in this audit.

## 8. Required controller adapter changes
Minimal changes needed (not implemented in this audit):
1. Extend `OpenCodeAdapter` to accept `agent` and `tools` params in `create_session`/`send_prompt_async` (pass through to body).
2. Add config: `OPENCODE_RESEARCH_BASE_URL`, `OPENCODE_RESEARCH_AGENT` (default "research"), `OPENCODE_RESEARCH_TOOLS` (default allowlist).
3. Research executor: create session with restricted agent, submit prompt with `tools` allowlist, poll, retrieve result.
4. No changes to existing dev adapter or ChatGPT task flow.

Configuration alone is NOT sufficient (adapter must pass `agent`/`tools` fields). Small adapter extension required.

## 9. Operational dependencies and limitations
- Requires a second OpenCode server instance with a restricted agent config (operator must create `~/.config/opencode/agents/research.md` or a separate config).
- The restricted agent must have `permission: {"*": "deny", "websearch": "allow", "webfetch": "allow"}` (and optionally read-only browser tools).
- The research instance should run on a separate port with separate config (`OPENCODE_CONFIG` env var or separate user config dir).
- Network-level isolation (firewall) is not strictly required if tool allowlist is enforced, but recommended for defense-in-depth.
- OpenCode server version must support `tools`/`agent` fields in prompt body (verified in docs for v1.18.30).

## 10. Exact next implementation step
Operator authorizes:
1. Create a restricted OpenCode agent config (`research` agent with deny-all + allow websearch/webfetch).
2. Start a second OpenCode instance on a separate port with that config.
3. Extend `OpenCodeAdapter` to accept `agent`/`tools` params.
4. Implement the research execution worker (claim → create session with restricted agent → submit prompt with tools allowlist → poll → retrieve → persist).
5. Run the security test matrix against the disposable instance.
6. Only then enable generic research execution.

## Verdict: B — CONDITIONALLY READY
Architecture is feasible and OpenCode's server-side permission model supports enforceable allowlists via per-agent config + per-request `tools` field. However, the actual enforcement boundary has NOT been demonstrated (no isolated instance tested). The adapter needs a small extension to pass `agent`/`tools`. Isolated-instance validation is required before claiming read-only security is verified.
