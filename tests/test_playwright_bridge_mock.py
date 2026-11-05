import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from opencode_bridge.browser_automation import (
    MockBrowserAdapter, extract_task_from_text, build_result_message, PlaywrightChatGPTController, TASK_MARKER_START, TASK_MARKER_END,
)
from opencode_bridge.config import DEV_WORKSPACE
from opencode_bridge.db import BridgeDB
from opencode_bridge.controller import TaskController
from opencode_bridge.opencode_adapter import MockOpenCodeAdapter


def make(tmpdir):
    db = BridgeDB(Path(tmpdir) / "b.db")
    ctrl = TaskController(db=db, adapter=MockOpenCodeAdapter(response_text="BROWSER_OK"), auto_worker=False)
    browser = MockBrowserAdapter()
    state_path = Path(tmpdir) / "state.json"
    orch = PlaywrightChatGPTController(browser=browser, task_controller=ctrl, state_path=state_path)
    return orch, browser, ctrl


def test_extract_task_marker():
    text = f"Here is task:\n{TASK_MARKER_START}\nDo thing\n{TASK_MARKER_END}\n"
    assert extract_task_from_text(text) == "Do thing"


def test_extract_task_bracket_marker():
    from opencode_bridge.browser_automation import TASK_START_BRACKET, TASK_END_BRACKET
    text = f"Intro\n{TASK_START_BRACKET}\nLine1\n```python\nprint('x')\n```\n{TASK_END_BRACKET}\n"
    assert extract_task_from_text(text) == "Line1\n```python\nprint('x')\n```"


def test_extract_task_duplicate_markers_rejected():
    from opencode_bridge.browser_automation import TASK_START_BRACKET, TASK_END_BRACKET
    text = f"{TASK_START_BRACKET}a{TASK_END_BRACKET} {TASK_START_BRACKET}b{TASK_END_BRACKET}"
    assert extract_task_from_text(text) is None


def test_extract_task_incomplete_marker_rejected():
    from opencode_bridge.browser_automation import TASK_START_BRACKET
    text = f"{TASK_START_BRACKET}no end"
    assert extract_task_from_text(text) is None


def test_extract_task_fenced():
    text = "OPENCODE_TASK:\n```python\nprint('hi')\n```"
    assert extract_task_from_text(text) == "print('hi')"


def test_no_task_returns_none():
    assert extract_task_from_text("hello world") is None


def test_run_one_cycle_and_approve():
    with tempfile.TemporaryDirectory() as d:
        orch, browser, ctrl = make(d)
        orch.set_conversation_url("https://chatgpt.com/c/test")
        browser.set_assistant_text(f"Task follows:\n{TASK_MARKER_START}\nRun tests\n{TASK_MARKER_END}")
        r = orch.run_one_cycle()
        assert r["ok"] is True
        tid = r["task_id"]
        # approve & execute
        ar = orch.approve_current_task(approved_by="tester")
        assert ar["ok"] is True
        st = ctrl.get_status(tid)
        assert st["status"] == "completed"
        # return result
        rr = orch.return_result_to_chatgpt()
        assert rr["ok"] is True
        assert len(browser.submitted()) == 1
        assert tid in browser.submitted()[0]


def test_pause_resume_cancel():
    with tempfile.TemporaryDirectory() as d:
        orch, browser, ctrl = make(d)
        orch.pause()
        r = orch.run_one_cycle()
        assert r["reason"] == "paused"
        orch.resume()
        orch.cancel()
        assert orch.state.status == "cancelled"


def test_build_result_message():
    msg = build_result_message("t1", "completed", "out", "report.md", "10 passed", "clean", "")
    assert "t1" in msg and "completed" in msg and "report.md" in msg


def test_open_project_conversation_mock():
    with tempfile.TemporaryDirectory() as d:
        orch, browser, ctrl = make(d)
        url = browser.create_project_chat("Palmistry Project")
        assert "Palmistry" in url or "mock" in url
        assert orch.ensure_project_conversation("https://chatgpt.com/g/p", "abc123") is True


def test_verify_conversation_wrong():
    with tempfile.TemporaryDirectory() as d:
        orch, browser, ctrl = make(d)
        orch.set_conversation_url("https://chatgpt.com/c/abc")
        browser.navigate("https://chatgpt.com/c/xyz")
        assert orch.verify_conversation() is False
        assert "mismatch" in orch.state.last_error


def test_recover():
    with tempfile.TemporaryDirectory() as d:
        orch, browser, ctrl = make(d)
        orch.set_conversation_url("https://chatgpt.com/c/abc")
        browser.navigate("https://chatgpt.com/c/abc")
        assert orch.recover() is True
        assert browser.current_url() == "https://chatgpt.com/c/abc"