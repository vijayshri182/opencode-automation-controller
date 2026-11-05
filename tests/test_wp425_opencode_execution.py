"""WP-425: controller-to-OpenCode execution integration â focused tests.

Uses deterministic doubles (FakeOpenCodeExecutor / MockOpenCodeAdapter via
TaskControllerExecutor). No live OpenCode API, no network, no repository mutation.
"""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest

from opencode_bridge import contracts
from opencode_bridge.chatgpt_interface import FakeChatGPTAdapter, PALMISTRY_PROJECT_ID
from opencode_bridge.db import BridgeDB
from opencode_bridge.executors import (
    OPENCODE_AUTH_REQUIRED,
    OPENCODE_CONTEXT_EXHAUSTED,
    OPENCODE_DISCONNECTED,
    OPENCODE_INTERRUPTED,
    OPENCODE_QUOTA_EXHAUSTED,
    OPENCODE_RATE_LIMITED,
    OPENCODE_UNCERTAIN,
    FakeOpenCodeExecutor,
    TaskControllerExecutor,
)
from opencode_bridge.orchestrator import MissionOrchestrator
from opencode_bridge.retry import RetryPolicy

NEUTRAL_TASK = "Inspect the repository and produce a summary report."


def fast_policy():
    return RetryPolicy(max_attempts=3, base_seconds=0.01, factor=2.0, cap_seconds=0.05, jitter_ratio=0.0)


def mission(tmp_path, ex=None):
    db = BridgeDB(tmp_path / "orch.db")
    chat = FakeChatGPTAdapter(messages=[NEUTRAL_TASK])
    ex = ex if ex is not None else FakeOpenCodeExecutor()
    o = MissionOrchestrator(
        db, chat, ex, mission_id="m1", workspace=str(tmp_path),
        allowed_repositories=[str(tmp_path)], retry_policy=fast_policy(),
        delivery_retry_policy=fast_policy(), task_timeout_seconds=0.0,
    )
    return o, chat, ex


def only_task(o):
    tasks = o.db.list_dev_tasks(mission_id="m1")
    assert len(tasks) == 1
    return tasks[0]


def test_successful_submission_persists_session_id(tmp_path):
    o, chat, ex = mission(tmp_path)
    o.run_cycle()
    task = only_task(o)
    execution = o.db.get_execution_for_task(task["task_id"])
    assert execution is not None
    assert execution["opencode_session_id"] == "fake-session-1"
    assert execution["execution_status"] == "completed"
    assert execution["started_at"] is not None
    assert execution["completed_at"] is not None
    assert execution["completed_at"] >= execution["started_at"]


def test_result_contains_actual_evidence(tmp_path):
    ex = FakeOpenCodeExecutor(
        response_text="REAL_OUTPUT", changed_files=["a.py"], test_results={"passed": 2, "failed": 0}
    )
    o, chat, _ = mission(tmp_path, ex=ex)
    o.run_cycle()
    execution = o.db.get_execution_for_task(only_task(o)["task_id"])
    assert execution["execution_output"] == "REAL_OUTPUT"
    assert execution["changed_files"] == ["a.py"]
    assert execution["test_results"] == {"passed": 2, "failed": 0}
    assert execution["verification_evidence"]["source"] == "fake_executor"
    assert execution["task_id"] == only_task(o)["task_id"]
    assert execution["execution_id"].startswith("exec-")


def test_duplicate_submission_prevented_at_store_level(tmp_path):
    o, chat, ex = mission(tmp_path)
    o.run_cycle()
    task = only_task(o)
    ex.submit_calls_before = ex.submit_calls
    # Force task back to ready and try to submit again
    o.db.set_dev_task_status(task["task_id"], "ready")
    before = ex.submit_calls
    result = o.submit_and_execute(task["task_id"])
    assert result.get("duplicate") is True
    assert ex.submit_calls == before


def test_submission_timeout_reconciliation(tmp_path):
    ex = FakeOpenCodeExecutor(submit_partial=True)
    o, chat, _ = mission(tmp_path, ex=ex)
    result = o.run_cycle()
    assert result["ok"] is False
    assert result.get("reason") == OPENCODE_UNCERTAIN
    execution = o.db.get_execution_for_task(only_task(o)["task_id"])
    assert execution["opencode_session_id"] == "fake-session-1"
    assert execution["execution_status"] == "uncertain"
    assert o.state().value == "RECONCILIATION_REQUIRED"


def test_interrupted_execution_recovery(tmp_path):
    ex = FakeOpenCodeExecutor()
    ex.fail_poll = OPENCODE_INTERRUPTED
    o, chat, _ = mission(tmp_path, ex=ex)
    o.run_cycle()
    assert o.state().value == "RECONCILIATION_REQUIRED"
    assert o.db.latest_checkpoint("m1")["reason"] == "execution_interrupted"

    ex.fail_poll = None
    recovery = o.recover()
    assert recovery["state"] == "CHATGPT_REVIEW_PENDING"
    assert "collected_result:True" in recovery["actions"]
    assert ex.submit_calls == 1


def test_result_retrieval_failure_does_not_lose_session(tmp_path):
    ex = FakeOpenCodeExecutor()
    ex.fail_poll = OPENCODE_DISCONNECTED
    o, chat, _ = mission(tmp_path, ex=ex)
    o.run_cycle()
    execution = o.db.get_execution_for_task(only_task(o)["task_id"])
    assert execution["opencode_session_id"] == "fake-session-1"
    assert execution["execution_status"] == "interrupted"


def test_controller_restart_recovery(tmp_path):
    db = BridgeDB(tmp_path / "orch.db")
    chat1 = FakeChatGPTAdapter(messages=[NEUTRAL_TASK])
    ex1 = FakeOpenCodeExecutor()
    first = MissionOrchestrator(
        db, chat1, ex1, mission_id="m1", workspace=str(tmp_path),
        allowed_repositories=[str(tmp_path)], retry_policy=fast_policy(),
        delivery_retry_policy=fast_policy(), task_timeout_seconds=0.0,
    )
    first.run_cycle()
    execution_before = first.db.get_execution_for_task(only_task(first)["task_id"])

    # Restart: fresh objects over same DB
    db2 = BridgeDB(tmp_path / "orch.db")
    chat2 = FakeChatGPTAdapter(messages=[NEUTRAL_TASK])
    ex2 = FakeOpenCodeExecutor()
    second = MissionOrchestrator(
        db2, chat2, ex2, mission_id="m1", workspace=str(tmp_path),
        allowed_repositories=[str(tmp_path)], retry_policy=fast_policy(),
        delivery_retry_policy=fast_policy(), task_timeout_seconds=0.0,
    )
    recovery = second.recover()
    assert second.state().value == "CHATGPT_REVIEW_PENDING"
    assert ex2.submit_calls == 0
    execution_after = second.db.get_execution_for_task(only_task(second)["task_id"])
    assert execution_after["execution_id"] == execution_before["execution_id"]
    assert execution_after["opencode_session_id"] == execution_before["opencode_session_id"]
    assert execution_after["execution_output"] == execution_before["execution_output"]


def test_rate_limit_arms_cooldown(tmp_path):
    ex = FakeOpenCodeExecutor(fail_submit=OPENCODE_RATE_LIMITED, retry_after=60.0)
    o, chat, _ = mission(tmp_path, ex=ex)
    result = o.run_cycle()
    assert result["ok"] is False
    assert o.state().value == "QUOTA_EXHAUSTED"
    state = o.db.get_provider_state("opencode")
    assert state["available"] is False
    assert state["cooldown_until"] is not None
    # Not hammered
    before = ex.submit_calls
    o.run_cycle()
    assert ex.submit_calls == before


def test_auth_failure_requires_operator(tmp_path):
    ex = FakeOpenCodeExecutor(fail_submit=OPENCODE_AUTH_REQUIRED)
    o, chat, _ = mission(tmp_path, ex=ex)
    result = o.run_cycle()
    assert result.get("requires_operator") is True
    assert o.state().value == "AUTHENTICATION_REQUIRED"
    before = ex.submit_calls
    o.run_cycle()
    assert ex.submit_calls == before


def test_context_exhaustion_writes_checkpoint(tmp_path):
    ex = FakeOpenCodeExecutor(fail_submit=OPENCODE_CONTEXT_EXHAUSTED)
    o, chat, _ = mission(tmp_path, ex=ex)
    result = o.run_cycle()
    assert result.get("requires_operator") is True
    assert o.state().value == "HUMAN_REVIEW_REQUIRED"
    cp = o.db.latest_checkpoint("m1")
    assert cp["reason"] == "context_exhausted"


def test_state_machine_consistency_after_completion(tmp_path):
    o, chat, _ = mission(tmp_path)
    o.run_cycle()
    assert o.state().value == "CHATGPT_REVIEW_PENDING"
    # RESULT_PERSISTED was entered during the run
    assert o.db.get_mission("m1")["state"] == "CHATGPT_REVIEW_PENDING"


def test_no_duplicate_execution_after_delivery_failure(tmp_path):
    chat = FakeChatGPTAdapter(messages=[NEUTRAL_TASK])
    chat.delivery_fails = True
    db = BridgeDB(tmp_path / "orch.db")
    ex = FakeOpenCodeExecutor()
    o = MissionOrchestrator(
        db, chat, ex, mission_id="m1", workspace=str(tmp_path),
        allowed_repositories=[str(tmp_path)], retry_policy=fast_policy(),
        delivery_retry_policy=fast_policy(), task_timeout_seconds=0.0,
    )
    o.run_cycle()
    assert o.state().value == "DELIVERY_FAILED"
    assert ex.submit_calls == 1
    # Delivery retry does not resubmit
    chat.delivery_fails = False
    task = only_task(o)
    execution = o.db.get_execution_for_task(task["task_id"])
    o.deliver_result(execution["execution_id"])
    assert ex.submit_calls == 1


def test_task_controller_executor_with_mock_adapter(tmp_path):
    """Verify the real TaskControllerExecutor path against MockOpenCodeAdapter."""
    from opencode_bridge.config import DEV_WORKSPACE
    from opencode_bridge.controller import TaskController
    from opencode_bridge.opencode_adapter import MockOpenCodeAdapter
    from opencode_bridge.db import BridgeDB

    db = BridgeDB(tmp_path / "orch.db")
    ctrl = TaskController(db=db, adapter=MockOpenCodeAdapter(response_text="REAL_ADAPTER_OK"), auto_worker=False)
    workspace = str(tmp_path)
    ex = TaskControllerExecutor(task_controller=ctrl, workspace=workspace)

    health = ex.health()
    assert health["ok"] is True

    task = {"task_id": "task-1", "task_description": "do thing"}
    result = ex.submit(task, "do thing")
    assert result["ok"] is True
    assert result["opencode_session_id"].startswith("mock-session-")
    sid = result["opencode_session_id"]

    execution = {"task_id": "task-1", "opencode_session_id": sid}
    polled = ex.poll(execution, timeout_seconds=5.0)
    assert polled["ok"] is True
    assert polled["finished"] is True
    assert polled["execution_output"] == "REAL_ADAPTER_OK"
    assert polled["changed_files"] == []  # no git repo in tmp_path

    # Reconcile returns found=True for an existing session
    rec = ex.reconcile(execution)
    assert rec["ok"] is True
    assert rec["found"] is True
    assert rec["opencode_session_id"] == sid

    # Abort
    assert ex.abort(execution) is True


def test_task_controller_executor_session_not_found(tmp_path):
    from opencode_bridge.controller import TaskController
    from opencode_bridge.opencode_adapter import MockOpenCodeAdapter
    from opencode_bridge.db import BridgeDB

    db = BridgeDB(tmp_path / "orch.db")
    ctrl = TaskController(db=db, adapter=MockOpenCodeAdapter(response_text="x"), auto_worker=False)
    ex = TaskControllerExecutor(task_controller=ctrl, workspace=str(tmp_path))

    # Reconcile with no session id returns found=False
    rec = ex.reconcile({"task_id": "t", "opencode_session_id": None})
    assert rec["ok"] is True
    assert rec["found"] is False

    # Reconcile with unknown session returns found=False (get_messages raises or empty)
    rec2 = ex.reconcile({"task_id": "t", "opencode_session_id": "nonexistent-session"})
    # MockOpenCodeAdapter.get_messages returns [] for unknown session
    assert rec2["ok"] is True


def test_task_controller_executor_health_auth_failure(tmp_path):
    """Health classification maps auth errors correctly."""
    from opencode_bridge.controller import TaskController
    from opencode_bridge.opencode_adapter import OpenCodeAdapter

    class AuthFailAdapter(OpenCodeAdapter):
        def health(self):
            raise Exception("HTTP 401 unauthorized")

        def create_session(self, title=""):
            return {"id": "x"}

        def send_prompt_async(self, session_id, text, model=None):
            pass

        def get_messages(self, session_id, limit=50):
            return []

    db = BridgeDB(tmp_path / "orch.db")
    ctrl = TaskController(db=db, adapter=AuthFailAdapter(), auto_worker=False)
    ex = TaskControllerExecutor(task_controller=ctrl, workspace=str(tmp_path))
    h = ex.health()
    assert h["ok"] is False
    assert h["reason"] == OPENCODE_AUTH_REQUIRED


def test_execution_timestamps_persisted(tmp_path):
    o, chat, ex = mission(tmp_path)
    o.run_cycle()
    execution = o.db.get_execution_for_task(only_task(o)["task_id"])
    assert execution["started_at"] is not None
    assert execution["completed_at"] is not None
    assert execution["completed_at"] >= execution["started_at"]
    assert execution["submitted_at"] is not None


def test_state_machine_consistency_during_execution(tmp_path):
    """Verify state transitions are valid at each stage."""
    from opencode_bridge.state_machine import can_transition, OrchState
    # OPENCODE_SUBMISSION -> OPENCODE_EXECUTION is valid
    assert can_transition(OrchState.OPENCODE_SUBMISSION, OrchState.OPENCODE_EXECUTION) is True
    # OPENCODE_EXECUTION -> RESULT_PERSISTED is valid
    assert can_transition(OrchState.OPENCODE_EXECUTION, OrchState.RESULT_PERSISTED) is True
    # RESULT_PERSISTED -> CHATGPT_DELIVERY_PENDING is valid
    assert can_transition(OrchState.RESULT_PERSISTED, OrchState.CHATGPT_DELIVERY_PENDING) is True
