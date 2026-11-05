"""WP-423: versioned contracts, explicit state machine and retry/cooldown primitives.

These are pure unit tests (no I/O, no browser, no network).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import random

import pytest

from opencode_bridge import contracts
from opencode_bridge.retry import (
    CooldownGate,
    RetryBudget,
    RetryPolicy,
    parse_retry_after,
)
from opencode_bridge.state_machine import (
    EXECUTION_IN_FLIGHT,
    HAPPY_PATH,
    InvalidTransition,
    OrchState,
    REQUIRED_ACTION,
    TERMINAL_STATES,
    assert_transition,
    can_transition,
    describe,
    is_terminal,
    recovery_target,
    transitions_from,
)


# --- helpers -------------------------------------------------------------


def valid_inbound(**overrides):
    payload = contracts.inbound_message(
        message_id="msg-1",
        project_id="g-p-6ae87c1e48b08191a2cd33139c40639f",
        conversation_id="conv-0001",
        message_content="Inspect the repository and produce a summary report.",
        correlation_id="corr-1",
        received_at=1_700_000_000.0,
    )
    payload.update(overrides)
    return payload


def valid_task(**overrides):
    payload = contracts.dev_task(
        task_id="task-1",
        mission_id="m1",
        originating_message_id="msg-1",
        task_title="Inspect repository",
        task_description="Inspect the repository and produce a summary report.",
        target_repository=r"C:\tmp\repo",
        target_branch="dev/phase-13",
        risk_classification="low",
    )
    payload.update(overrides)
    return payload


# --- contracts: inbound message -----------------------------------------


def test_valid_inbound_message_accepted():
    ok, errors = contracts.validate_inbound_message(valid_inbound())
    assert ok is True, errors
    assert errors == []


def test_inbound_message_requires_every_logical_field():
    required = [
        "message_id",
        "source",
        "project_id",
        "conversation_id",
        "message_content",
        "correlation_id",
        "received_at",
        "schema_version",
    ]
    for field in required:
        payload = valid_inbound()
        payload.pop(field)
        ok, errors = contracts.validate_inbound_message(payload)
        assert ok is False, f"missing {field} was accepted"
        assert any(field in e for e in errors), (field, errors)


def test_inbound_message_rejects_wrong_schema_version():
    ok, errors = contracts.validate_inbound_message(valid_inbound(schema_version="wp423.inbound_message.v0"))
    assert ok is False
    assert any("schema_version" in e for e in errors)


def test_inbound_message_rejects_oversized_content():
    payload = valid_inbound(message_content="x" * (contracts.MAX_MESSAGE_CONTENT_CHARS + 1))
    ok, errors = contracts.validate_inbound_message(payload)
    assert ok is False
    assert any("message_content" in e for e in errors)


def test_inbound_message_rejects_unknown_source_and_identity_source():
    ok, errors = contracts.validate_inbound_message(valid_inbound(source="telegram"))
    assert ok is False and any("source" in e for e in errors)

    ok, errors = contracts.validate_inbound_message(valid_inbound(message_identity_source="invented"))
    assert ok is False and any("message_identity_source" in e for e in errors)


def test_inbound_message_timestamp_is_optional_but_never_invented():
    payload = valid_inbound()
    assert payload["message_timestamp"] is None
    ok, _ = contracts.validate_inbound_message(payload)
    assert ok is True

    # A fabricated/typed timestamp is rejected rather than silently coerced.
    ok, errors = contracts.validate_inbound_message(valid_inbound(message_timestamp=12345))
    assert ok is False


def test_non_object_payload_rejected():
    ok, errors = contracts.validate_inbound_message("not-an-object")
    assert ok is False and errors == ["payload: must be an object"]


# --- contracts: development task ----------------------------------------


def test_valid_dev_task_accepted():
    ok, errors = contracts.validate_dev_task(valid_task())
    assert ok is True, errors


def test_dev_task_rejects_bad_risk_and_status():
    ok, errors = contracts.validate_dev_task(valid_task(risk_classification="apocalyptic"))
    assert ok is False and any("risk_classification" in e for e in errors)

    ok, errors = contracts.validate_dev_task(valid_task(task_status="sort_of_done"))
    assert ok is False and any("task_status" in e for e in errors)


def test_dev_task_rejects_oversized_list_and_non_string_items():
    ok, errors = contracts.validate_dev_task(valid_task(scope=["a"] * (contracts.MAX_LIST_ITEMS + 1)))
    assert ok is False and any("scope" in e for e in errors)

    ok, errors = contracts.validate_dev_task(valid_task(scope=["ok", 7]))
    assert ok is False and any("scope[1]" in e for e in errors)


# --- contracts: execution + delivery ------------------------------------


def test_execution_contract_round_trips():
    payload = contracts.execution(execution_id="exec-1", task_id="task-1", submitted_at=1.0)
    ok, errors = contracts.validate_execution(payload)
    assert ok is True, errors
    assert payload["schema_version"] == contracts.EXECUTION_SCHEMA
    assert payload["completion_status"] is None
    assert payload["changed_files"] == []


def test_execution_rejects_unknown_status():
    payload = contracts.execution(execution_id="exec-1", task_id="task-1", submitted_at=1.0)
    payload["execution_status"] = "finished_maybe"
    ok, errors = contracts.validate_execution(payload)
    assert ok is False and any("execution_status" in e for e in errors)


def test_delivery_contract_round_trips_and_validates_attempts():
    payload = contracts.delivery(
        delivery_id="deliv-1",
        originating_execution_id="exec-1",
        target_project_id="g-p-x",
        target_conversation_id="conv-1",
        response_content="result",
    )
    ok, errors = contracts.validate_delivery(payload)
    assert ok is True, errors
    assert payload["delivery_status"] == "pending"

    payload["attempts"] = -1
    ok, errors = contracts.validate_delivery(payload)
    assert ok is False and any("attempts" in e for e in errors)

    payload["attempts"] = True  # bool must not pass as int
    ok, errors = contracts.validate_delivery(payload)
    assert ok is False and any("attempts" in e for e in errors)


def test_all_declared_schemas_are_supported():
    assert contracts.INBOUND_MESSAGE_SCHEMA in contracts.SUPPORTED_SCHEMAS
    assert contracts.DEV_TASK_SCHEMA in contracts.SUPPORTED_SCHEMAS
    assert contracts.EXECUTION_SCHEMA in contracts.SUPPORTED_SCHEMAS
    assert contracts.DELIVERY_SCHEMA in contracts.SUPPORTED_SCHEMAS


# --- state machine -------------------------------------------------------


def test_happy_path_has_documented_twelve_states_and_is_fully_connected():
    assert len(HAPPY_PATH) == 12
    assert HAPPY_PATH[0] is OrchState.READY
    assert HAPPY_PATH[-1] is OrchState.READY
    for source, target in zip(HAPPY_PATH, HAPPY_PATH[1:]):
        assert can_transition(source, target), f"{source.value} -> {target.value} not allowed"


def test_all_required_degraded_states_exist():
    required = {
        "PAUSED",
        "WAITING_FOR_APPROVAL",
        "WAITING_FOR_CHATGPT",
        "WAITING_FOR_OPENCODE",
        "QUOTA_EXHAUSTED",
        "AUTHENTICATION_REQUIRED",
        "EXECUTION_INTERRUPTED",
        "DELIVERY_FAILED",
        "RECONCILIATION_REQUIRED",
        "HUMAN_REVIEW_REQUIRED",
        "COMPLETED",
        "FAILED",
    }
    assert required <= {s.value for s in OrchState}
    for name in required:
        assert REQUIRED_ACTION.get(OrchState(name)) or name in ("COMPLETED", "FAILED")


def test_completed_is_only_reachable_from_review_pending():
    sources = [state for state in OrchState if can_transition(state, OrchState.COMPLETED)]
    assert sources == [OrchState.CHATGPT_REVIEW_PENDING]


def test_no_execution_state_can_jump_straight_to_a_delivery_state():
    delivery_states = {
        OrchState.CHATGPT_DELIVERY_PENDING,
        OrchState.CHATGPT_DELIVERED,
        OrchState.CHATGPT_REVIEW_PENDING,
        OrchState.COMPLETED,
    }
    for state in (
        OrchState.OPENCODE_SUBMISSION,
        OrchState.OPENCODE_EXECUTION,
        OrchState.WAITING_FOR_OPENCODE,
    ):
        assert not (transitions_from(state) & delivery_states), state


def test_terminal_states_have_no_outgoing_edges():
    for state in TERMINAL_STATES:
        assert transitions_from(state) == set()
        assert is_terminal(state) is True


def test_invalid_transition_raises_and_can_transition_is_false():
    assert can_transition(OrchState.READY, OrchState.COMPLETED) is False
    with pytest.raises(InvalidTransition) as exc:
        assert_transition(OrchState.READY, OrchState.COMPLETED)
    assert "READY -> COMPLETED" in str(exc.value)


def test_recovery_target_reconciles_instead_of_retrying_execution():
    for state in EXECUTION_IN_FLIGHT:
        assert recovery_target(state) is OrchState.RECONCILIATION_REQUIRED
    assert recovery_target(OrchState.RECONCILIATION_REQUIRED, has_result=True) is OrchState.CHATGPT_DELIVERY_PENDING
    assert recovery_target(OrchState.RESULT_PERSISTED) is OrchState.CHATGPT_DELIVERY_PENDING
    assert recovery_target(OrchState.COMPLETED) is OrchState.COMPLETED
    assert recovery_target(OrchState.FAILED) is OrchState.FAILED


def test_describe_exposes_operator_action():
    info = describe(OrchState.QUOTA_EXHAUSTED)
    assert info["state"] == "QUOTA_EXHAUSTED"
    assert info["waiting"] is True
    assert info["terminal"] is False
    assert "quota" in info["required_action"].lower()


# --- retry / cooldown ----------------------------------------------------


def test_backoff_is_bounded_exponential():
    policy = RetryPolicy(max_attempts=6, base_seconds=1.0, factor=2.0, cap_seconds=8.0)
    assert [policy.raw_delay(a) for a in (1, 2, 3, 4, 5, 6)] == [1.0, 2.0, 4.0, 8.0, 8.0, 8.0]


def test_retry_after_always_overrides_computed_backoff():
    policy = RetryPolicy(base_seconds=1.0, factor=2.0, cap_seconds=60.0)
    assert policy.delay_for(5, retry_after=42.0) == 42.0
    assert policy.delay_for(1, retry_after=0.0) == 0.0


def test_jitter_is_deterministic_and_within_bounds():
    policy = RetryPolicy(base_seconds=4.0, factor=2.0, cap_seconds=60.0, jitter_ratio=0.25)
    a = policy.delay_for(1, rng=random.Random(7))
    b = policy.delay_for(1, rng=random.Random(7))
    assert a == b
    assert 3.0 <= a <= 5.0


def test_retry_policy_rejects_nonsense_configuration():
    with pytest.raises(ValueError):
        RetryPolicy(max_attempts=0)
    with pytest.raises(ValueError):
        RetryPolicy(jitter_ratio=1.0)


def test_parse_retry_after_handles_seconds_http_date_and_garbage():
    assert parse_retry_after("120") == 120.0
    assert parse_retry_after("  ") is None
    assert parse_retry_after(None) is None
    assert parse_retry_after("not-a-date") is None

    from email.utils import parsedate_to_datetime

    stamp = "Wed, 21 Oct 2015 07:28:00 GMT"
    target = parsedate_to_datetime(stamp).timestamp()
    assert parse_retry_after(stamp, now=target - 90) == pytest.approx(90.0, abs=0.001)


def test_cooldown_gate_is_a_hard_gate_and_expires():
    now = [1000.0]
    gate = CooldownGate(clock=lambda: now[0])
    assert gate.is_open(None) is True
    assert gate.is_open(now[0] + 30) is False
    assert gate.remaining(now[0] + 30) == 30.0
    now[0] += 31
    assert gate.is_open(now[0] - 1) is True
    assert gate.remaining(now[0] - 1) == 0.0
    assert gate.until(10) == now[0] + 10


def test_retry_budget_bounds_attempts():
    budget = RetryBudget(RetryPolicy(max_attempts=2))
    assert budget.remaining == 2
    budget.consume()
    assert budget.remaining == 1 and budget.exhausted is False
    budget.consume()
    assert budget.exhausted is True
    with pytest.raises(RuntimeError):
        budget.consume()
    assert budget.to_dict()["used"] == 2
