# TEST-RESEARCH-ISOLATION-001 — Dedicated OpenCode Research Server Security Validation

## Preflight results
- Existing OpenCode dev server: running on 127.0.0.1:4097, version 1.18.30, healthy.
- Existing controller: running on 127.0.0.1:8799, healthy, 22 tools, READY state.
- Proposed research port 4098: free (no listener).
- Existing OpenCode config (`~/.config/opencode/opencode.jsonc`): permission object only grants `external_directory` for the dev workspace; no agent definitions, no deny-all baseline. Default agent "build" has `"*": "allow"`.
- OpenCode agents directory (`~/.config/opencode/agents/`): does not exist / empty. No "research" agent installed.
- Dedicated research workspace: not created.
- Dedicated research config file: not present.

## Blocker
Starting a separate OpenCode research instance requires:
1. A dedicated OpenCode config with a restricted "research" agent (deny-all baseline + allow websearch/webfetch) and no development workspace access.
2. Installation of that config into OpenCode's config path (file creation/modification).
3. A separate workspace directory.
4. Optionally `OPENCODE_CONFIG` env var pointing to the dedicated config.

None of these exist. Creating them would modify OpenCode configuration and create files, which violates the task's "Do not modify files" / "If startup requires modifying shared configuration, stop and report" constraints. The controller's `config/research_agent.md` is a documentation artifact in the controller repo, not an installed OpenCode agent.

## Positive tests
NOT PERFORMED (blocked at preflight).

## Negative security tests
NOT PERFORMED (blocked at preflight).

## Regression and isolation
NOT PERFORMED (blocked at preflight).

## Cleanup
No research instance was started. Nothing to clean up. Existing controller (8799) and OpenCode dev server (4097) remain running and untouched.

## Unresolved risks
- Without a dedicated restricted OpenCode instance, read-only research execution cannot be validated.
- The existing dev OpenCode server has `"*": "allow"` baseline — unsuitable for research.
- No research agent is installed in OpenCode.

## Verdict: C — BLOCKED
Blocker: dedicated research OpenCode instance cannot be started without creating/modifying OpenCode configuration files and installing a restricted research agent. Operator must authorize and perform: (1) create research agent config (from `config/research_agent.md`), (2) create separate OpenCode config with deny-all baseline, (3) create isolated workspace, (4) start research instance on separate port. Then re-run this validation.