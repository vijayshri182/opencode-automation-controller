import os
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from fastapi.testclient import TestClient
from opencode_bridge.config import DEV_WORKSPACE, MAX_TASK_CHARS
from opencode_bridge.db import BridgeDB
from opencode_bridge.controller import TaskController
from opencode_bridge.opencode_adapter import MockOpenCodeAdapter
from opencode_bridge.mcp_server import app, set_controller
from opencode_bridge.models import TaskStatus


def setup(tmpdir, adapter=None):
    db = BridgeDB(Path(tmpdir) / "bridge.db")
    ctrl = TaskController(db=db, adapter=adapter or MockOpenCodeAdapter(response_text="GUI03_OK"), auto_worker=False)
    set_controller(ctrl)
    return ctrl, db


def test_all_five_tools_present():
    with tempfile.TemporaryDirectory() as d:
        setup(d)
        c = TestClient(app)
        r = c.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}})
        names = [t["name"] for t in r.json()["result"]["tools"]]
        for required in ("submit_task", "get_task_status", "get_task_result", "list_recent_tasks", "cancel_task"):
            assert required in names
        for t in r.json()["result"]["tools"]:
            assert "inputSchema" in t


class _NeverRespondAdapter(MockOpenCodeAdapter):
    def send_prompt_async(self, session_id, text):
        return None
    def get_messages(self, session_id, limit=50):
        return []


def test_timeout_handling():
    with tempfile.TemporaryDirectory() as d:
        adapter = _NeverRespondAdapter(response_text="LATE", delay=0.0)
        ctrl, db = setup(d, adapter=adapter)
        r = ctrl.submit_task("timeout task", workspace=str(DEV_WORKSPACE), timeout_seconds=0.3)
        tid = r["task_id"]
        ctrl.approve_task(tid, approved_by="tester")
        ctrl.run_task_sync(tid)
        st = ctrl.get_status(tid)
        assert st["status"] == "failed"


def test_restart_recovery():
    with tempfile.TemporaryDirectory() as d:
        db_path = Path(d) / "bridge.db"
        db = BridgeDB(db_path)
        adapter = MockOpenCodeAdapter(response_text="X")
        ctrl = TaskController(db=db, adapter=adapter, auto_worker=False)
        r = ctrl.submit_task("recover task", workspace=str(DEV_WORKSPACE))
        tid = r["task_id"]
        ctrl.approve_task(tid, approved_by="tester")
        # simulate running
        task = db.get_task(tid)
        task.status = TaskStatus.RUNNING
        task.started_at = __import__("time").time()
        db.update_task(task)
        # restart
        db2 = BridgeDB(db_path)
        ctrl2 = TaskController(db=db2, adapter=adapter, auto_worker=False)
        t2 = db2.get_task(tid)
        assert t2.status == TaskStatus.FAILED
        assert "interrupted" in (t2.error or "")


def test_task_size_limit():
    with tempfile.TemporaryDirectory() as d:
        ctrl, db = setup(d)
        big = "x" * (MAX_TASK_CHARS + 10)
        r = ctrl.submit_task(big, workspace=str(DEV_WORKSPACE))
        assert r["status"] == "blocked"


def test_secret_redaction_basic():
    with tempfile.TemporaryDirectory() as d:
        ctrl, db = setup(d)
        r = ctrl.submit_task("safe task no secrets", workspace=str(DEV_WORKSPACE))
        tid = r["task_id"]
        st = ctrl.get_status(tid)
        assert "OPENCODE_SERVER_PASSWORD" not in str(st)
        res = ctrl.get_result(tid)
        assert "OPENCODE_SERVER_PASSWORD" not in str(res)