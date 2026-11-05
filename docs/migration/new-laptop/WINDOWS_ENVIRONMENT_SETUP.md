# Windows Environment Setup

## Prerequisites
- Windows 10/11 64-bit, IST timezone (India Standard Time).
- Python 3.13.x (F&O), 3.12 (ai-career-agent), 3.11 (others).
- Git for Windows.
- PowerShell 5.1+.
- Node.js 20+ and npm (controller, F&O GUI).
- VS Code or preferred editor.
- OpenCode (optional, for agent workflows).
- Disk: >= 10 GB free.
- Network: GitHub, PyPI, Upstox API.

## Directory structure
```
C:\Vijay_GitHub\
  fno-ai-paper-trading\          (PROD)
  fno-ai-paper-trading-dev\      (DEV)
  opencode-automation-controller\ (optional)
  <other projects>
C:\ProgramData\FNO-App\secrets\  (credential store, created manually)
```

## Setup steps
1. Install Python, Git, Node.js, VS Code.
2. Set PowerShell execution policy: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`.
3. Clone repos: see GITHUB_REPOSITORY_RESTORATION.md.
4. Create venvs and install deps.
5. Create .env from .env.example (fill non-secret config).
6. Establish credential store (see CREDENTIAL_REESTABLISHMENT_CHECKLIST.md).
7. Run synthetic tests.
8. Do NOT start runner/scheduler.