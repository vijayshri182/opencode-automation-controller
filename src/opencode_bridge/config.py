import os
from pathlib import Path

# Load local .env (gitignored) if present, without overriding existing env.
_env_path = Path(__file__).resolve().parent.parent.parent / ".env"
if _env_path.exists():
    try:
        for _line in _env_path.read_text(encoding="utf-8").splitlines():
            _line = _line.strip()
            if not _line or _line.startswith("#") or "=" not in _line:
                continue
            _k, _v = _line.split("=", 1)
            _k = _k.strip()
            _v = _v.strip().strip('"').strip("'")
            if _k and _k not in os.environ:
                os.environ[_k] = _v
    except Exception:
        pass

DEV_WORKSPACE = Path(r"C:\Vijay_GitHub\fno-ai-paper-trading-dev").resolve()
EXPECTED_BRANCH = "dev/phase-13"
PROD_WORKSPACE_HINTS = ("fno-ai-paper-trading",)  # prod path lacks -dev
SENSITIVE_KEYWORDS = (
    "commit", "push", "deploy", "release", "merge", "rebase",
    "session launch", "launch session", "live order", "live trading",
    ".env", "secret", "token", "credential", "oauth", "upstox",
    "reset", "clean", "stash", "force push", "delete branch",
)
MAX_TASK_CHARS = 20000
DEFAULT_TIMEOUT_SECONDS = 300.0
POLL_INTERVAL_SECONDS = 2.0
DB_FILENAME = "opencode_bridge.db"
MCP_DEFAULT_PORT = 8799
OPENCODE_DEFAULT_BASE_URL = "http://127.0.0.1:4096"


def dev_workspace() -> Path:
    return DEV_WORKSPACE


def opencode_base_url() -> str:
    return os.environ.get("OPENCODE_BASE_URL", OPENCODE_DEFAULT_BASE_URL).rstrip("/")


def opencode_password() -> str:
    return os.environ.get("OPENCODE_SERVER_PASSWORD", os.environ.get("OPENCODE_PASSWORD", ""))


def opencode_username() -> str:
    return os.environ.get("OPENCODE_SERVER_USERNAME", "opencode")


def mcp_auth_token() -> str:
    return os.environ.get("MCP_AUTH_TOKEN", "")


def use_mock_adapter() -> bool:
    return os.environ.get("OPENCODE_MOCK", "").lower() in ("1", "true", "yes")


def edge_executable_path() -> str:
    return os.environ.get("EDGE_EXECUTABLE_PATH", r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")


def opencode_timeout() -> float:
    try:
        return float(os.environ.get("OPENCODE_TIMEOUT_SECONDS", "30"))
    except ValueError:
        return 30.0


def opencode_max_retries() -> int:
    try:
        return int(os.environ.get("OPENCODE_MAX_RETRIES", "3"))
    except ValueError:
        return 3


def opencode_retry_backoff() -> float:
    try:
        return float(os.environ.get("OPENCODE_RETRY_BACKOFF", "0.5"))
    except ValueError:
        return 0.5


def opencode_model_provider() -> str:
    return os.environ.get("OPENCODE_MODEL_PROVIDER", "")


def opencode_model_id() -> str:
    return os.environ.get("OPENCODE_MODEL_ID", "")


def opencode_research_base_url() -> str:
    return os.environ.get("OPENCODE_RESEARCH_BASE_URL", "").rstrip("/")


def opencode_research_agent() -> str:
    return os.environ.get("OPENCODE_RESEARCH_AGENT", "research")


def opencode_research_tools() -> dict:
    # Default allowlist: websearch + webfetch only.
    return {"websearch": True, "webfetch": True, "bash": False, "write": False,
            "edit": False, "read": False, "glob": False, "grep": False, "list": False,
            "task": False, "todowrite": False}


def opencode_research_model_provider() -> str:
    return os.environ.get("OPENCODE_RESEARCH_MODEL_PROVIDER", "opencode-go")


def opencode_research_model_id() -> str:
    return os.environ.get("OPENCODE_RESEARCH_MODEL_ID", "beam-free")


def opencode_research_workspace() -> str:
    return os.environ.get("OPENCODE_RESEARCH_WORKSPACE",
                          r"C:\Vijay_GitHub\opencode-research-workspace")