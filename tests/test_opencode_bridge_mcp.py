import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from fastapi.testclient import TestClient
from opencode_bridge.config import DEV_WORKSPACE
from opencode_bridge.db import BridgeDB
from opencode_bridge.controller import TaskController
from opencode_bridge.opencode_adapter import MockOpenCodeAdapter
from opencode_bridge.mcp_server import app, set_controller


def setup_controller(tmpdir):
    db = BridgeDB(Path(tmpdir) / "bridge.db")
    ctrl = TaskController(db=db, adapter=MockOpenCodeAdapter(response_text="MCP_OK"), auto_worker=False)
    set_controller(ctrl)
    return ctrl, db


def test_health():
    with tempfile.TemporaryDirectory() as d:
        setup_controller(d)
        c = TestClient(app)
        resp = c.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


def test_mcp_initialize_and_tools_list():
    with tempfile.TemporaryDirectory() as d:
        setup_controller(d)
        c = TestClient(app)
        r = c.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        assert r.status_code == 200
        assert r.json()["result"]["serverInfo"]["name"] == "opencode-bridge"
        r2 = c.post("/mcp", json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
        assert r2.status_code == 200
        tools = [t["name"] for t in r2.json()["result"]["tools"]]
        assert "submit_task" in tools
        assert "get_task_status" in tools


def test_mcp_submit_validation():
    with tempfile.TemporaryDirectory() as d:
        setup_controller(d)
        c = TestClient(app)
        # missing task
        r = c.post("/mcp", json={"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "submit_task", "arguments": {}}})
        assert r.status_code == 200
        assert "error" in r.json() or "error" in r.json().get("result", {}).get("content", [{}])[0].get("text", "")
        # valid submit
        r2 = c.post("/mcp", json={"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "submit_task", "arguments": {"task": "MCP task", "workspace": str(DEV_WORKSPACE)}}})
        assert r2.status_code == 200
        body = r2.json()
        assert "result" in body


def test_mcp_auth():
    os.environ["MCP_AUTH_TOKEN"] = "secrettoken"
    try:
        with tempfile.TemporaryDirectory() as d:
            setup_controller(d)
            c = TestClient(app)
            r = c.post("/mcp", json={"jsonrpc": "2.0", "id": 5, "method": "tools/list", "params": {}})
            assert r.status_code == 401
            r2 = c.post("/mcp", headers={"Authorization": "Bearer secrettoken"}, json={"jsonrpc": "2.0", "id": 6, "method": "tools/list", "params": {}})
            assert r2.status_code == 200
    finally:
        del os.environ["MCP_AUTH_TOKEN"]