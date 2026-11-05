# OpenCode and Controller Restoration

## OpenCode installation
- Install OpenCode per official docs.
- Config: `%USERPROFILE%\.config\opencode\` (backed up in `opencode_config/`).
- Required: `opencode.jsonc`, `AGENTS.md`, `service.json`, `templates/project-memory.md`.

## Controller installation
1. Clone `opencode-automation-controller` (HEAD 9a6ac13).
2. Create venv: `python -m venv .venv; .\.venv\Scripts\pip install -r requirements.txt`.
3. Copy `.env.example` to `.env`, fill `OPENCODE_SERVER_PASSWORD` (strong local password).
4. Create `bridge.db` (auto-created on first run) or restore from backup.
5. Verify: `.\.venv\Scripts\python.exe -m pytest tests/ -q`.

## MCP and agents
- MCP config: `config/` directory.
- Agent definitions: `src/opencode_bridge/`.
- Tool discovery: controller exposes 22 MCP tools (submit/get research tasks, etc.).

## Ports
- Controller API: 8799
- OpenCode: 4096/4097/4098
- MCP: loopback only

## Browser automation
- Edge profiles must be recreated (auth state not portable).
- Interactive login required on new laptop.

## Health checks
- Controller: `GET http://127.0.0.1:8799/health`
- MCP: tool discovery via JSON-RPC.

## Not required for F&O
The controller is a separate project. F&O runs independently.