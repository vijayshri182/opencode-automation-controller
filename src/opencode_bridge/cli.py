import argparse
import os
import sys
import threading
from pathlib import Path

# ensure importable when run as script
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from opencode_bridge.config import (
    DEV_WORKSPACE,
    mcp_auth_token,
    opencode_base_url,
    opencode_password,
    opencode_username,
    use_mock_adapter,
)
from opencode_bridge.db import BridgeDB
from opencode_bridge.mcp_server import MCPServer, MCPServerHTTP
from opencode_bridge.opencode_adapter import MockOpenCodeAdapter, OpenCodeAdapter
from opencode_bridge.orchestrator import MissionOrchestrator
from opencode_bridge.retry import RetryPolicy


def build_orchestrator(db, workspace, mock=False):
    """Construct a MissionOrchestrator for the MCP server.

    ChatGPT adapter: a lightweight offline adapter is used so the server can
    start without a live browser/CDP session. The OpenCode adapter is real
    unless mock mode is requested.
    """
    if mock:
        from opencode_bridge.chatgpt_interface import FakeChatGPTAdapter
        from opencode_bridge.executors import FakeOpenCodeExecutor

        chat = FakeChatGPTAdapter(messages=[])
        executor = FakeOpenCodeExecutor()
    else:
        from opencode_bridge.chatgpt_interface import FakeChatGPTAdapter

        chat = FakeChatGPTAdapter(messages=[])
        executor = OpenCodeAdapter()

    retry = RetryPolicy()
    return MissionOrchestrator(
        db,
        chat,
        executor,
        mission_id="mcp-server",
        mission_title="OpenCode Automation Controller",
        workspace=workspace,
        allowed_repositories=[workspace],
        retry_policy=retry,
        delivery_retry_policy=retry,
        task_timeout_seconds=300.0,
    )


def build_server(host="127.0.0.1", port=8799, db_path=None, mock=False, workspace=None):
    if host not in ("127.0.0.1", "localhost", "::1"):
        raise ValueError(f"only loopback host allowed; got {host!r}")

    if workspace is None:
        workspace = str(DEV_WORKSPACE)
    ws_path = Path(workspace)
    if db_path is None:
        db_path = ws_path / ".opencode_bridge" / "bridge.db"
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    db = BridgeDB(db_path)
    orchestrator = build_orchestrator(db, workspace, mock=mock)
    # Research executor (optional): only wired when a dedicated research endpoint is configured.
    research_executor = None
    try:
        from opencode_bridge.config import opencode_research_base_url
        if opencode_research_base_url():
            from opencode_bridge.research_executor import ResearchExecutor
            research_executor = ResearchExecutor(db)
    except Exception:
        research_executor = None
    mcp = MCPServer(orchestrator, token_provider=lambda: mcp_auth_token(), research_executor=research_executor)
    http = MCPServerHTTP(mcp, host=host, port=port)
    return http, db


def main():
    parser = argparse.ArgumentParser(description="OpenCode Automation Controller (MCP server)")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8799)
    parser.add_argument("--db", default=None)
    parser.add_argument("--workspace", default=None)
    parser.add_argument("--mock", action="store_true")
    args = parser.parse_args()

    mock = args.mock or use_mock_adapter()

    try:
        http, db = build_server(
            host=args.host, port=args.port, db_path=args.db,
            mock=mock, workspace=args.workspace,
        )
    except Exception as exc:
        print(f"ERROR: failed to initialize controller: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2

    server = http.create_http_server()
    print(f"OpenCode Controller starting on http://{args.host}:{server.server_port}")
    print(f"Workspace: {http.mcp.orchestrator.workspace if hasattr(http.mcp.orchestrator, 'workspace') else 'n/a'}")
    print(f"Mock adapter: {mock}")
    print(f"Auth token configured: {bool(mcp_auth_token())}")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        try:
            server.shutdown()
        except Exception:
            pass
        try:
            server.server_close()
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
