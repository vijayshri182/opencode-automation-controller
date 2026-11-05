"""WP-423: durable controller state — idempotency, uniqueness, atomicity, restart.

Uses the real SQLite store (``BridgeDB``) on a temporary database file, so these
tests exercise actual constraints and an actual reopen rather than a stub.
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest

from opencode_bridge import contracts
from opencode_bridge.db import BridgeDB
from opencode_bridge.models import TaskStatus


def make_db(tmp_path, name="orch.db"):
    return BridgeDB(tmp_path / name)


def inbound(**overrides):
    payload = contracts.inbound_message(
        message_id=overrides.pop("message_id", "msg-1"),
        project_id="g-p-6ae87c1e48b08191a2cd33139c40639f",
        conversation_id=overrides.pop("conversation_id", "conv-0001"),
        message_content=overrides.pop("message_content", "Inspect the repository and produce a summary report."),
        correlation_id=overrides.pop("correlation_id", "corr-1"),
        received_at=overrides.pop("received_at", 1_700_000_000.0),
    )
    payload.update(overrides)
    return payload


def task(task_id="task-1", message_id="msg-1", mission_id="m1"):
    return contracts.dev_task(
        task_id=task_id,
        mission_id=mission_id,
        originating_message_id=message_id,
        task_title="Inspect repository",
        task_description="Inspect the repository and produce a summary report.",
        target_repository=r"C:\tmp\repo",
        target_branch="dev/phase-13",
        risk_classification="low",
    )


def execution(execution_id="exec-1", task_id="task-1"):
    return contracts.execution(execution_id=execution_id, task_id=task_id, submitted_at=1.0)


def delivery(delivery_id="deliv-1", execution_id="exec-1"):
    return contracts.delivery(
        delivery_id=delivery_id,
        originating_execution_id=execution_id,
        target_project_id="g-p-x",
        target_conversation_id="conv-1",
        response_content="result",
    )


# --- mission -------------------------------------------------------------


def test_mission_upsert_is_idempotent_and_state_is_readable(tmp_path):
    db = make_db(tmp_path)
    db.upsert_mission("m1", "Mission", r"C:\tmp\repo", "dev/phase-13", "READY")
    db.upsert_mission("m1", "Mission renamed", r"C:\tmp\repo", "dev/phase-13", "TASK_READY")

    mission = db.get_mission("m1")
    assert mission["state"] == "TASK_READY"
    assert mission["title"] == "Mission"  # first write wins for descriptive fields
    assert mission["paused"] == 0


def test_mission_pause_is_persisted(tmp_path):
    db = make_db(tmp_path)
    db.upsert_mission("m1", "Mission", r"C:\tmp\repo", "dev/phase-13", "READY")
    db.set_mission_paused("m1", True, "PAUSED")
    assert db.get_mission("m1")["paused"] == 1
    assert db.get_mission("m1")["state"] == "PAUSED"


# --- idempotent ingestion ------------------------------------------------


def test_message_ingestion_is_idempotent_and_counts_duplicates(tmp_path):
    db = make_db(tmp_path)
    payload = inbound()

    inserted, row = db.ingest_inbound_message(payload, "hash-a")
    assert inserted is True
    assert row["message_id"] == "msg-1"
    assert row["duplicate_count"] == 0

    inserted, row = db.ingest_inbound_message(payload, "hash-a")
    assert inserted is False
    assert row["duplicate_count"] == 1
    # Original record must not be overwritten by the replay.
    assert row["message_content"] == payload["message_content"]

    inserted, row = db.ingest_inbound_message(payload, "hash-a")
    assert inserted is False
    assert row["duplicate_count"] == 2

    assert db.inbox_counts() == {"total": 1, "processed": 0, "pending": 1, "with_duplicates": 1}


def test_message_identity_is_the_primary_key(tmp_path):
    db = make_db(tmp_path)
    db.ingest_inbound_message(inbound(), "hash-a")
    db.ingest_inbound_message(inbound(message_id="msg-2", correlation_id="corr-2"), "hash-b")
    assert db.inbox_counts()["total"] == 2
    assert db.get_inbound_message("msg-1")["correlation_id"] == "corr-1"
    assert db.get_inbound_message("msg-2")["correlation_id"] == "corr-2"
    assert db.get_inbound_message("missing") is None


def test_processed_flag_round_trip(tmp_path):
    db = make_db(tmp_path)
    db.ingest_inbound_message(inbound(), "hash-a")
    db.mark_inbound_processed("msg-1")
    assert db.get_inbound_message("msg-1")["processed"] == 1
    assert db.inbox_counts()["pending"] == 0


# --- unique identities --------------------------------------------------


def test_one_task_per_originating_message(tmp_path):
    db = make_db(tmp_path)
    assert db.insert_dev_task(task("task-1")) is True
    # Different task id, same (mission, originating message) -> rejected.
    assert db.insert_dev_task(task("task-2")) is False
    assert db.get_dev_task_for_message("m1", "msg-1")["task_id"] == "task-1"


def test_one_execution_per_task(tmp_path):
    db = make_db(tmp_path)
    from opencode_bridge.db import SCHEMA  # noqa: F401  (task table is separate from dev_tasks)

    db.insert_dev_task(task("task-1"))
    assert db.insert_execution(execution("exec-1")) is True
    assert db.insert_execution(execution("exec-2")) is False
    assert db.get_execution_for_task("task-1")["execution_id"] == "exec-1"


def test_one_delivery_per_execution(tmp_path):
    db = make_db(tmp_path)
    db.insert_dev_task(task("task-1"))
    db.insert_execution(execution("exec-1"))
    assert db.insert_delivery(delivery("deliv-1")) is True
    assert db.insert_delivery(delivery("deliv-2")) is False
    assert db.get_delivery_for_execution("exec-1")["delivery_id"] == "deliv-1"


def test_execution_update_rejects_unknown_field(tmp_path):
    db = make_db(tmp_path)
    db.insert_execution(execution("exec-1"))
    with pytest.raises(ValueError):
        db.update_execution("exec-1", not_a_column="x")


def test_execution_json_fields_round_trip(tmp_path):
    db = make_db(tmp_path)
    db.insert_execution(execution("exec-1"))
    db.update_execution(
        "exec-1",
        execution_status="completed",
        completion_status="completed",
        changed_files=["src/a.py"],
        test_results={"passed": 3},
        execution_output="done",
        verification_evidence={"report": "r.md"},
    )
    row = db.get_execution("exec-1")
    assert row["changed_files"] == ["src/a.py"]
    assert row["test_results"] == {"passed": 3}
    assert row["verification_evidence"] == {"report": "r.md"}


# --- atomic transactions ------------------------------------------------


def test_transaction_commits_both_rows(tmp_path):
    db = make_db(tmp_path)
    with db.transaction() as conn:
        conn.execute(
            "INSERT INTO missions (id,title,target_repository,target_branch,state,paused,created_at,updated_at)"
            " VALUES (?,?,?,?,?,0,?,?)",
            ("m-tx", "Mission", r"C:\tmp\repo", "dev/phase-13", "READY", 1.0, 1.0),
        )
        conn.execute("INSERT INTO audit_events (task_id,event,details,created_at) VALUES (?,?,?,?)",
                     ("m-tx", "tx_event", "details", 1.0))
    assert db.get_mission("m-tx") is not None
    assert any(r["event"] == "tx_event" for r in db.list_audit(10))


def test_transaction_rolls_back_everything_on_error(tmp_path):
    db = make_db(tmp_path)
    with pytest.raises(RuntimeError):
        with db.transaction() as conn:
            conn.execute(
                "INSERT INTO missions (id,title,target_repository,target_branch,state,paused,created_at,updated_at)"
                " VALUES (?,?,?,?,?,0,?,?)",
                ("m-tx", "Mission", r"C:\tmp\repo", "dev/phase-13", "READY", 1.0, 1.0),
            )
            conn.execute("INSERT INTO audit_events (task_id,event,details,created_at) VALUES (?,?,?,?)",
                         ("m-tx", "tx_event", "details", 1.0))
            raise RuntimeError("boom")
    assert db.get_mission("m-tx") is None
    assert not any(r["event"] == "tx_event" for r in db.list_audit(10))


# --- approvals ----------------------------------------------------------


def test_approval_can_only_be_decided_once(tmp_path):
    db = make_db(tmp_path)
    db.insert_dev_task(task("task-1"))
    db.create_approval_request("apr-1", "task-1", "medium", ["human_approval:write"])

    pending = db.get_pending_approval_for_task("task-1")
    assert pending["requirements"] == ["human_approval:write"]

    assert db.decide_approval("apr-1", "approved", "operator", "ok") is True
    assert db.decide_approval("apr-1", "approved", "operator", "again") is False
    assert db.get_pending_approval_for_task("task-1") is None


# --- provider state / checkpoints --------------------------------------


def test_provider_cooldown_is_persisted_and_upserted(tmp_path):
    db = make_db(tmp_path)
    db.set_provider_state("chatgpt", available=False, cooldown_until=1234.5, consecutive_failures=2,
                          retry_budget=1, last_error="rate limited")
    state = db.get_provider_state("chatgpt")
    assert state["available"] is False
    assert state["cooldown_until"] == 1234.5
    assert state["consecutive_failures"] == 2

    db.set_provider_state("chatgpt", available=True, cooldown_until=None, consecutive_failures=0)
    state = db.get_provider_state("chatgpt")
    assert state["available"] is True
    assert state["cooldown_until"] is None
    assert len(db.list_provider_state()) == 1


def test_checkpoints_keep_history_and_latest(tmp_path):
    db = make_db(tmp_path)
    first = db.save_checkpoint("context_exhausted", {"n": 1}, mission_id="m1")
    second = db.save_checkpoint("execution_interrupted", {"n": 2}, mission_id="m1", task_id="task-1")
    assert second > first
    latest = db.latest_checkpoint("m1")
    assert latest["reason"] == "execution_interrupted"
    assert latest["payload"] == {"n": 2}
    assert db.latest_checkpoint("other") is None


# --- restart recovery ---------------------------------------------------


def test_all_state_survives_a_process_restart(tmp_path):
    path = tmp_path / "orch.db"
    db = BridgeDB(path)
    db.upsert_mission("m1", "Mission", r"C:\tmp\repo", "dev/phase-13", "RESULT_PERSISTED")
    db.ingest_inbound_message(inbound(), "hash-a")
    db.mark_inbound_processed("msg-1")
    db.insert_dev_task(task("task-1"))
    db.insert_execution(execution("exec-1"))
    db.update_execution("exec-1", execution_status="completed", execution_output="done",
                        changed_files=["a.py"], test_results={"passed": 1})
    db.insert_delivery(delivery("deliv-1"))
    db.update_delivery("deliv-1", delivery_status="failed", attempts=2)
    db.set_provider_state("opencode", available=False, cooldown_until=time.time() + 60)
    db.save_checkpoint("execution_interrupted", {"task_id": "task-1"}, mission_id="m1")
    db.audit_orch("result_persisted", "task-1", "exec-1")

    # Simulate a restart: a brand-new object over the same file.
    reopened = BridgeDB(path)
    assert reopened.get_mission("m1")["state"] == "RESULT_PERSISTED"
    assert reopened.get_inbound_message("msg-1")["processed"] == 1
    assert reopened.get_dev_task("task-1")["task_id"] == "task-1"
    execution_row = reopened.get_execution("exec-1")
    assert execution_row["execution_status"] == "completed"
    assert execution_row["changed_files"] == ["a.py"]
    delivery_row = reopened.get_delivery_for_execution("exec-1")
    assert delivery_row["delivery_status"] == "failed"
    assert delivery_row["attempts"] == 2
    assert reopened.get_provider_state("opencode")["available"] is False
    assert reopened.latest_checkpoint("m1")["reason"] == "execution_interrupted"
    assert any(r["event"] == "result_persisted" for r in reopened.list_audit(20))


def test_legacy_task_table_recovery_still_works(tmp_path):
    """The pre-existing WP-GUI02 task recovery must stay untouched."""
    from opencode_bridge.models import content_hash

    db = make_db(tmp_path)
    chash = content_hash("task text", {}, r"C:\tmp\repo")
    with db.transaction() as conn:
        conn.execute(
            "INSERT INTO tasks (id,idempotency_key,task_text,metadata_json,workspace,branch,status,created_at,"
            "timeout_seconds,content_hash) VALUES (?,?,?,?,?,?,?,?,?,?)",
            ("t1", chash, "task text", "{}", r"C:\tmp\repo", "dev/phase-13",
             TaskStatus.RUNNING.value, 1.0, 30.0, chash),
        )
    assert db.mark_interrupted_running() == 1
    row = db.get_task("t1")
    assert row.status is TaskStatus.FAILED
    assert "interrupted" in (row.error or "")
