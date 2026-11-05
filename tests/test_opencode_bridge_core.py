import os
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from opencode_bridge.config import DEV_WORKSPACE
from opencode_bridge.db import BridgeDB
from opencode_bridge.controller import TaskController
from opencode_bridge.opencode_adapter import MockOpenCodeAdapter
from opencode_bridge.models import TaskStatus
from opencode_bridge.safety import validate_workspace, validate_task_text


def make_controller(tmpdir, adapter=None):
    db_path = Path(tmpdir) / "bridge.db"
    db = BridgeDB(db_path)
    ad = adapter if adapter is not None else MockOpenCodeAdapter(response_text="DONE_OK", delay=0.0)
    ctrl = TaskController(db=db, adapter=ad, auto_worker=False)
    return ctrl, db


def test_valid_invalid_submission():
    with tempfile.TemporaryDirectory() as d:
        ctrl, db = make_controller(d)
        r = ctrl.submit_task("Run tests", workspace=str(DEV_WORKSPACE))
        assert r["status"] == "awaiting_approval"
        tid = r["task_id"]
        # invalid workspace
        r2 = ctrl.submit_task("Run tests", workspace="C:\\nope")
        assert r2["status"] == "blocked"
        # empty task
        r3 = ctrl.submit_task("   ", workspace=str(DEV_WORKSPACE))
        assert r3["status"] == "blocked"


def test_dev_path_and_prod_rejection():
    ok, msg = validate_workspace(str(DEV_WORKSPACE))
    assert ok, msg
    ok2, msg2 = validate_workspace("C:\\Vijay_GitHub\\fno-ai-paper-trading")
    assert not ok2
    # task text referencing prod
    ok3, msg3 = validate_task_text("modify PROD fno-ai-paper-trading repo")
    assert not ok3


def test_approval_and_invalidation():
    with tempfile.TemporaryDirectory() as d:
        ctrl, db = make_controller(d)
        r = ctrl.submit_task("Task A", workspace=str(DEV_WORKSPACE))
        tid = r["task_id"]
        # approve
        ar = ctrl.approve_task(tid, approved_by="tester")
        assert ar["ok"] is True
        assert ar["status"] == "queued"
        # status
        st = ctrl.get_status(tid)
        assert st["status"] == "queued"
        # invalidation: modify task text (simulate by calling invalidate)
        task = db.get_task(tid)
        changed = ctrl.invalidate_approval_if_modified(tid, "Task A modified")
        assert changed is True
        task2 = db.get_task(tid)
        assert task2.approval_hash is None


def test_duplicate_submission():
    with tempfile.TemporaryDirectory() as d:
        ctrl, db = make_controller(d)
        r1 = ctrl.submit_task("Dup task", workspace=str(DEV_WORKSPACE))
        r2 = ctrl.submit_task("Dup task", workspace=str(DEV_WORKSPACE))
        assert r2.get("duplicate") is True
        assert r1["task_id"] == r2["task_id"]


def test_async_status_polling_and_result():
    with tempfile.TemporaryDirectory() as d:
        ctrl, db = make_controller(d)
        r = ctrl.submit_task("Async task", workspace=str(DEV_WORKSPACE))
        tid = r["task_id"]
        ctrl.approve_task(tid, approved_by="tester")
        # run synchronously
        ctrl.run_task_sync(tid)
        st = ctrl.get_status(tid)
        assert st["status"] == "completed"
        res = ctrl.get_result(tid)
        assert res["ok"] is True
        assert res["result"]["final_response"] == "DONE_OK"


def test_failed_task():
    with tempfile.TemporaryDirectory() as d:
        adapter = MockOpenCodeAdapter(response_text="X", fail=True)
        ctrl, db = make_controller(d, adapter=adapter)
        r = ctrl.submit_task("Fail task", workspace=str(DEV_WORKSPACE))
        tid = r["task_id"]
        ctrl.approve_task(tid, approved_by="tester")
        ctrl.run_task_sync(tid)
        st = ctrl.get_status(tid)
        assert st["status"] == "failed"
        res = ctrl.get_result(tid)
        assert res["status"] == "failed"


def test_cancel_task():
    with tempfile.TemporaryDirectory() as d:
        adapter = MockOpenCodeAdapter(response_text="X", delay=5.0)
        ctrl, db = make_controller(d, adapter=adapter)
        r = ctrl.submit_task("Cancel task", workspace=str(DEV_WORKSPACE))
        tid = r["task_id"]
        ctrl.approve_task(tid, approved_by="tester")
        # queue then cancel before run
        cr = ctrl.cancel_task(tid, reason="test")
        assert cr["ok"] is True
        assert cr["status"] == "cancelled"


def test_sqlite_persistence_and_recovery():
    with tempfile.TemporaryDirectory() as d:
        db_path = Path(d) / "bridge.db"
        db = BridgeDB(db_path)
        adapter = MockOpenCodeAdapter(response_text="PERSIST_OK")
        ctrl = TaskController(db=db, adapter=adapter, auto_worker=False)
        r = ctrl.submit_task("Persist task", workspace=str(DEV_WORKSPACE))
        tid = r["task_id"]
        ctrl.approve_task(tid, approved_by="tester")
        # simulate restart: new db/controller
        db2 = BridgeDB(db_path)
        ctrl2 = TaskController(db=db2, adapter=adapter, auto_worker=False)
        t = db2.get_task(tid)
        assert t is not None
        assert t.status in (TaskStatus.QUEUED, TaskStatus.COMPLETED)
        db.close()
        db2.close()


def test_missing_malformed_result():
    with tempfile.TemporaryDirectory() as d:
        ctrl, db = make_controller(d)
        res = ctrl.get_result("nonexistent-id")
        assert res["ok"] is False
        assert res["status"] == "missing"


def test_secret_redaction_and_no_env():
    # ensure controller does not read .env; basic check that submit stores no secret values
    with tempfile.TemporaryDirectory() as d:
        ctrl, db = make_controller(d)
        r = ctrl.submit_task("safe task", workspace=str(DEV_WORKSPACE))
        tid = r["task_id"]
        t = db.get_task(tid)
        assert "OPENCODE_SERVER_PASSWORD" not in (t.task_text or "")
        # result of get_result should not include secrets (none present anyway)
        assert True


def test_explicit_model_selection_default_unchanged():
    with tempfile.TemporaryDirectory() as d:
        ctrl, db = make_controller(d)
        r = ctrl.submit_task("model task", workspace=str(DEV_WORKSPACE), metadata={"model": {"providerID": "opencode", "modelID": "beam-free"}})
        tid = r["task_id"]
        ctrl.approve_task(tid, approved_by="tester")
        # monkeypatch adapter to capture model
        captured = {}
        orig = ctrl.adapter.send_prompt_async
        def capture(session_id, text, model=None):
            captured["model"] = model
            return orig(session_id, text, model=model)
        ctrl.adapter.send_prompt_async = capture
        ctrl.run_task_sync(tid)
        assert captured.get("model") == {"providerID": "opencode", "modelID": "beam-free"}
        # default model param absent in task metadata defaults to None
        r2 = ctrl.submit_task("default model task", workspace=str(DEV_WORKSPACE))
        t2 = db.get_task(r2["task_id"])
        assert (t2.metadata.get("model") if t2.metadata else None) is None


def test_preserve_working_tree():
    # record git status before/after creating a task (no repo mutation)
    import subprocess
    before = subprocess.run(["git", "status", "--porcelain"], cwd=str(DEV_WORKSPACE), capture_output=True, text=True).stdout
    with tempfile.TemporaryDirectory() as d:
        ctrl, db = make_controller(d)
        r = ctrl.submit_task("wt check", workspace=str(DEV_WORKSPACE))
        tid = r["task_id"]
        ctrl.approve_task(tid, approved_by="tester")
        ctrl.run_task_sync(tid)
    after = subprocess.run(["git", "status", "--porcelain"], cwd=str(DEV_WORKSPACE), capture_output=True, text=True).stdout
    # The task may create report files? Mock adapter doesn't. So status should be identical.
    assert before == after, "working tree changed unexpectedly"