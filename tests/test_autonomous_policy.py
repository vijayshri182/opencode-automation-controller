import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from opencode_bridge.policy import classify_task, TaskPolicy
from opencode_bridge.browser_automation import MockBrowserAdapter, PlaywrightChatGPTController, extract_task_from_text
from opencode_bridge.config import DEV_WORKSPACE
from opencode_bridge.db import BridgeDB
from opencode_bridge.controller import TaskController
from opencode_bridge.opencode_adapter import MockOpenCodeAdapter
from opencode_bridge.autonomous import AutonomousOrchestrator


def make(tmpdir):
    db = BridgeDB(Path(tmpdir) / "b.db")
    ctrl = TaskController(db=db, adapter=MockOpenCodeAdapter(response_text="AUTO_OK"), auto_worker=False)
    browser = MockBrowserAdapter()
    orch = PlaywrightChatGPTController(browser=browser, task_controller=ctrl, state_path=Path(tmpdir) / "s.json")
    orch.set_conversation_url("https://chatgpt.com/c/test")
    auto = AutonomousOrchestrator(orch)
    return auto, browser, ctrl


def test_classify_blocked():
    p, r = classify_task("print the password and token")
    assert p == TaskPolicy.BLOCKED


def test_classify_auto_readonly():
    p, r = classify_task("Inspect README and report a summary")
    assert p == TaskPolicy.AUTO_APPROVE


def test_classify_requires_approval_modification():
    p, r = classify_task("Modify config.py to add a feature")
    assert p == TaskPolicy.REQUIRES_APPROVAL


def test_autonomous_no_task():
    with tempfile.TemporaryDirectory() as d:
        auto, browser, ctrl = make(d)
        browser.set_assistant_text("hello no marker")
        r = auto.process_one_cycle()
        assert r["reason"] == "no marked task"


def test_autonomous_auto_executes_and_delivers():
    with tempfile.TemporaryDirectory() as d:
        auto, browser, ctrl = make(d)
        browser.set_assistant_text("[OPENCODE_TASK_START]\nInspect README\n[OPENCODE_TASK_END]")
        r = auto.process_one_cycle()
        assert r["ok"] is True
        assert r["policy"] == "auto_approve"
        assert r["execution_status"] == "completed"
        assert r["delivery"]["ok"] is True
        assert len(browser.submitted()) == 1


def test_autonomous_health_fail_closed():
    with tempfile.TemporaryDirectory() as d:
        auto, browser, ctrl = make(d)
        browser._auth = False
        browser.set_assistant_text("[OPENCODE_TASK_START]\nInspect README\n[OPENCODE_TASK_END]")
        r = auto.process_one_cycle()
        assert r["reason"] == "conversation unhealthy"


def test_autonomous_requires_approval_does_not_execute():
    with tempfile.TemporaryDirectory() as d:
        auto, browser, ctrl = make(d)
        browser.set_assistant_text("[OPENCODE_TASK_START]\nModify config.py\n[OPENCODE_TASK_END]")
        r = auto.process_one_cycle()
        assert r["requires_approval"] is True
        # task should be awaiting approval, not executed
        tid = r["task_id"]
        st = ctrl.get_status(tid)
        assert st["status"] == "awaiting_approval"