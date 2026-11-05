# OpenCode Automation Controller

A reusable, local-only orchestration utility that connects ChatGPT, OpenCode and
explicitly authorized development repositories.

This is **not** an F&O application feature. It contains no trading logic, no
Upstox integration and no live-order capability.

## Quick start

```powershell
cd C:\Vijay_GitHub\opencode-automation-controller
$env:PYTHONPATH = "src"
$env:OPENCODE_MOCK = "1"
python -m opencode_bridge.cli --mock --port 8799
```

Health check:

```powershell
curl.exe http://127.0.0.1:8799/health
```

MCP endpoint: `POST http://127.0.0.1:8799/mcp` (JSON-RPC 2.0).

## Tests

```powershell
$env:PYTHONPATH = "src"
python -m pytest -q
```

## Browser integration (primary)

Playwright + Microsoft Edge is the exclusive browser integration. Chrome/Chromium fallbacks are not used. Secure MCP Tunnel remains optional and is not configured.

Run supervised automation via the `PlaywrightChatGPTController` in `src/opencode_bridge/browser_automation.py`. Playwright is not currently installed; install it with explicit authorization before using the real browser path. Mock browser adapter is available for tests.

## Secure startup (PowerShell)

Start OpenCode securely (recommended):

```powershell
$env:OPENCODE_SERVER_PASSWORD = "choose-a-strong-local-password"
opencode serve --hostname 127.0.0.1 --port 4096
```

Start controller:

```powershell
cd C:\Vijay_GitHub\opencode-automation-controller
$env:PYTHONPATH = "src"
$env:OPENCODE_BASE_URL = "http://127.0.0.1:4096"
$env:OPENCODE_SERVER_PASSWORD = "choose-a-strong-local-password"
$env:OPENCODE_MOCK = "0"
python -m opencode_bridge.cli --port 8799
```

Mock mode:

```powershell
$env:OPENCODE_MOCK = "1"
python -m opencode_bridge.cli --mock --port 8799
```

## Safety boundaries

- Only authorized workspace: `C:\Vijay_GitHub\fno-ai-paper-trading-dev`
- PROD repository is never authorized.
- No commits, pushes, deployments or releases.
- No credentials, tokens or `.env` reading.
- No trading-session control or live orders.
- Supervised mode only; continuous chaining disabled.
- Path allowlist is not an OS sandbox; see docs/security.md.