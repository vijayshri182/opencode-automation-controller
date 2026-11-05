"""WP-423: explicit orchestration state machine.

A single mission advances through this machine. Transitions are declared as data
so both the orchestrator and the tests reason about the same table, and so an
invalid transition is an observable error rather than an implicit behaviour.

Key invariants:

* ``COMPLETED`` is only reachable from ``CHATGPT_REVIEW_PENDING`` — never from a
  submission, and never merely because OpenCode accepted a request.
* ``RESULT_PERSISTED`` sits strictly before any delivery state, so a completed
  OpenCode result cannot be lost by a failed ChatGPT delivery.
* Terminal states are ``COMPLETED`` and ``FAILED`` and have no outgoing edges.
"""

from enum import Enum
from typing import Dict, FrozenSet, Optional, Set


class OrchState(str, Enum):
    READY = "READY"
    CHATGPT_MESSAGE_DETECTED = "CHATGPT_MESSAGE_DETECTED"
    MESSAGE_PERSISTED = "MESSAGE_PERSISTED"
    TASK_VALIDATION = "TASK_VALIDATION"
    TASK_READY = "TASK_READY"
    OPENCODE_SUBMISSION = "OPENCODE_SUBMISSION"
    OPENCODE_EXECUTION = "OPENCODE_EXECUTION"
    RESULT_PERSISTED = "RESULT_PERSISTED"
    CHATGPT_DELIVERY_PENDING = "CHATGPT_DELIVERY_PENDING"
    CHATGPT_DELIVERED = "CHATGPT_DELIVERED"
    CHATGPT_REVIEW_PENDING = "CHATGPT_REVIEW_PENDING"

    # waiting / degraded
    PAUSED = "PAUSED"
    WAITING_FOR_APPROVAL = "WAITING_FOR_APPROVAL"
    WAITING_FOR_CHATGPT = "WAITING_FOR_CHATGPT"
    WAITING_FOR_OPENCODE = "WAITING_FOR_OPENCODE"
    QUOTA_EXHAUSTED = "QUOTA_EXHAUSTED"
    AUTHENTICATION_REQUIRED = "AUTHENTICATION_REQUIRED"
    EXECUTION_INTERRUPTED = "EXECUTION_INTERRUPTED"
    DELIVERY_FAILED = "DELIVERY_FAILED"
    RECONCILIATION_REQUIRED = "RECONCILIATION_REQUIRED"
    HUMAN_REVIEW_REQUIRED = "HUMAN_REVIEW_REQUIRED"

    # terminal
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


#: The documented happy-path order, useful for assertions and reports.
HAPPY_PATH = (
    OrchState.READY,
    OrchState.CHATGPT_MESSAGE_DETECTED,
    OrchState.MESSAGE_PERSISTED,
    OrchState.TASK_VALIDATION,
    OrchState.TASK_READY,
    OrchState.OPENCODE_SUBMISSION,
    OrchState.OPENCODE_EXECUTION,
    OrchState.RESULT_PERSISTED,
    OrchState.CHATGPT_DELIVERY_PENDING,
    OrchState.CHATGPT_DELIVERED,
    OrchState.CHATGPT_REVIEW_PENDING,
    OrchState.READY,
)

TERMINAL_STATES: FrozenSet[OrchState] = frozenset({OrchState.COMPLETED, OrchState.FAILED})

#: States that mean "the loop cannot proceed without an external actor".
WAITING_STATES: FrozenSet[OrchState] = frozenset(
    {
        OrchState.PAUSED,
        OrchState.WAITING_FOR_APPROVAL,
        OrchState.WAITING_FOR_CHATGPT,
        OrchState.WAITING_FOR_OPENCODE,
        OrchState.QUOTA_EXHAUSTED,
        OrchState.AUTHENTICATION_REQUIRED,
        OrchState.HUMAN_REVIEW_REQUIRED,
        OrchState.RECONCILIATION_REQUIRED,
    }
)

#: Work has been handed to OpenCode but no result has been persisted yet. This is
#: exactly the window in which a restart must reconcile rather than resubmit.
EXECUTION_IN_FLIGHT: FrozenSet[OrchState] = frozenset(
    {OrchState.OPENCODE_SUBMISSION, OrchState.OPENCODE_EXECUTION, OrchState.WAITING_FOR_OPENCODE}
)

_TRANSITIONS: Dict[OrchState, Set[OrchState]] = {
    OrchState.READY: {
        OrchState.CHATGPT_MESSAGE_DETECTED,
        OrchState.PAUSED,
    },
    OrchState.CHATGPT_MESSAGE_DETECTED: {
        OrchState.MESSAGE_PERSISTED,
        OrchState.PAUSED,
        OrchState.FAILED,
    },
    OrchState.MESSAGE_PERSISTED: {
        OrchState.TASK_VALIDATION,
        # A replayed/duplicate message returns straight to READY, no new task.
        OrchState.READY,
        OrchState.PAUSED,
        OrchState.FAILED,
    },
    OrchState.TASK_VALIDATION: {
        OrchState.TASK_READY,
        OrchState.HUMAN_REVIEW_REQUIRED,
        OrchState.PAUSED,
        OrchState.FAILED,
    },
    OrchState.TASK_READY: {
        OrchState.WAITING_FOR_APPROVAL,
        OrchState.OPENCODE_SUBMISSION,
        OrchState.PAUSED,
        OrchState.FAILED,
    },
    OrchState.WAITING_FOR_APPROVAL: {
        OrchState.OPENCODE_SUBMISSION,
        OrchState.HUMAN_REVIEW_REQUIRED,
        OrchState.PAUSED,
        OrchState.FAILED,
    },
    OrchState.OPENCODE_SUBMISSION: {
        OrchState.OPENCODE_EXECUTION,
        OrchState.WAITING_FOR_OPENCODE,
        OrchState.QUOTA_EXHAUSTED,
        OrchState.AUTHENTICATION_REQUIRED,
        OrchState.EXECUTION_INTERRUPTED,
        OrchState.RECONCILIATION_REQUIRED,
        OrchState.HUMAN_REVIEW_REQUIRED,
        OrchState.PAUSED,
        OrchState.FAILED,
    },
    OrchState.OPENCODE_EXECUTION: {
        OrchState.RESULT_PERSISTED,
        OrchState.WAITING_FOR_OPENCODE,
        OrchState.QUOTA_EXHAUSTED,
        OrchState.AUTHENTICATION_REQUIRED,
        OrchState.EXECUTION_INTERRUPTED,
        OrchState.RECONCILIATION_REQUIRED,
        OrchState.PAUSED,
        OrchState.FAILED,
    },
    OrchState.WAITING_FOR_OPENCODE: {
        OrchState.OPENCODE_EXECUTION,
        OrchState.RESULT_PERSISTED,
        OrchState.QUOTA_EXHAUSTED,
        OrchState.AUTHENTICATION_REQUIRED,
        OrchState.EXECUTION_INTERRUPTED,
        OrchState.RECONCILIATION_REQUIRED,
        OrchState.PAUSED,
        OrchState.FAILED,
    },
    OrchState.RESULT_PERSISTED: {
        OrchState.CHATGPT_DELIVERY_PENDING,
        OrchState.PAUSED,
        OrchState.FAILED,
    },
    OrchState.CHATGPT_DELIVERY_PENDING: {
        OrchState.CHATGPT_DELIVERED,
        OrchState.DELIVERY_FAILED,
        OrchState.WAITING_FOR_CHATGPT,
        OrchState.RECONCILIATION_REQUIRED,
        OrchState.AUTHENTICATION_REQUIRED,
        # Delivery budget exhausted: hand over to a human, never loop forever.
        OrchState.HUMAN_REVIEW_REQUIRED,
        OrchState.PAUSED,
        OrchState.FAILED,
    },
    OrchState.CHATGPT_DELIVERED: {
        OrchState.CHATGPT_REVIEW_PENDING,
        OrchState.PAUSED,
    },
    OrchState.CHATGPT_REVIEW_PENDING: {
        # Only here can a mission be declared complete.
        OrchState.READY,
        OrchState.COMPLETED,
        OrchState.PAUSED,
    },
    OrchState.DELIVERY_FAILED: {
        OrchState.CHATGPT_DELIVERY_PENDING,
        OrchState.HUMAN_REVIEW_REQUIRED,
        OrchState.PAUSED,
        OrchState.FAILED,
    },
    OrchState.QUOTA_EXHAUSTED: {
        OrchState.OPENCODE_SUBMISSION,
        OrchState.OPENCODE_EXECUTION,
        OrchState.WAITING_FOR_OPENCODE,
        OrchState.HUMAN_REVIEW_REQUIRED,
        OrchState.PAUSED,
        OrchState.FAILED,
    },
    OrchState.AUTHENTICATION_REQUIRED: {
        OrchState.OPENCODE_SUBMISSION,
        OrchState.CHATGPT_DELIVERY_PENDING,
        OrchState.HUMAN_REVIEW_REQUIRED,
        OrchState.PAUSED,
        OrchState.FAILED,
    },
    OrchState.EXECUTION_INTERRUPTED: {
        OrchState.RECONCILIATION_REQUIRED,
        OrchState.PAUSED,
        OrchState.FAILED,
    },
    OrchState.RECONCILIATION_REQUIRED: {
        # Resume polling an existing session, or accept an already-persisted result.
        OrchState.OPENCODE_EXECUTION,
        OrchState.WAITING_FOR_OPENCODE,
        OrchState.RESULT_PERSISTED,
        OrchState.CHATGPT_DELIVERY_PENDING,
        OrchState.HUMAN_REVIEW_REQUIRED,
        OrchState.PAUSED,
        OrchState.FAILED,
    },
    OrchState.WAITING_FOR_CHATGPT: {
        OrchState.READY,
        OrchState.CHATGPT_REVIEW_PENDING,
        # A pending delivery may be resumed once the transport recovers.
        OrchState.CHATGPT_DELIVERY_PENDING,
        OrchState.PAUSED,
        OrchState.FAILED,
    },
    OrchState.HUMAN_REVIEW_REQUIRED: {
        OrchState.READY,
        OrchState.TASK_READY,
        OrchState.OPENCODE_SUBMISSION,
        OrchState.CHATGPT_DELIVERY_PENDING,
        OrchState.PAUSED,
        OrchState.FAILED,
    },
    OrchState.PAUSED: {
        OrchState.READY,
        OrchState.CHATGPT_MESSAGE_DETECTED,
        OrchState.OPENCODE_SUBMISSION,
        OrchState.OPENCODE_EXECUTION,
        OrchState.RECONCILIATION_REQUIRED,
        OrchState.CHATGPT_DELIVERY_PENDING,
        OrchState.HUMAN_REVIEW_REQUIRED,
    },
    OrchState.COMPLETED: set(),
    OrchState.FAILED: set(),
}

#: Operator-facing reason each degraded state needs attendance.
REQUIRED_ACTION: Dict[OrchState, str] = {
    OrchState.PAUSED: "mission paused; resume to continue",
    OrchState.WAITING_FOR_APPROVAL: "approve or reject the pending development task",
    OrchState.WAITING_FOR_CHATGPT: "waiting for a new ChatGPT message",
    OrchState.WAITING_FOR_OPENCODE: "waiting for the OpenCode execution to finish",
    OrchState.QUOTA_EXHAUSTED: "provider quota exhausted; wait for cooldown or raise the limit",
    OrchState.AUTHENTICATION_REQUIRED: "authentication expired; operator must re-authenticate",
    OrchState.EXECUTION_INTERRUPTED: "execution interrupted; reconcile before any retry",
    OrchState.DELIVERY_FAILED: "ChatGPT delivery failed; retry within the retry budget",
    OrchState.RECONCILIATION_REQUIRED: "uncertain submission or delivery; reconcile before retrying",
    OrchState.HUMAN_REVIEW_REQUIRED: "human review required before continuing",
}


def transitions_from(state: OrchState) -> Set[OrchState]:
    return set(_TRANSITIONS.get(OrchState(state), set()))


def is_terminal(state: OrchState) -> bool:
    return OrchState(state) in TERMINAL_STATES


def can_transition(source: OrchState, target: OrchState) -> bool:
    try:
        return OrchState(target) in _TRANSITIONS[OrchState(source)]
    except (KeyError, ValueError):
        return False


class InvalidTransition(RuntimeError):
    def __init__(self, source: OrchState, target: OrchState):
        self.source = OrchState(source)
        self.target = OrchState(target)
        super().__init__(f"invalid transition {self.source.value} -> {self.target.value}")


def assert_transition(source: OrchState, target: OrchState) -> None:
    if not can_transition(source, target):
        raise InvalidTransition(source, target)


def recovery_target(state: OrchState, has_result: bool = False, has_session: bool = False) -> OrchState:
    """Map a persisted state to its safe post-restart state.

    Submission and execution states are *always* reconciled rather than retried:
    a restart must never create a second OpenCode execution.
    """
    state = OrchState(state)
    if state in TERMINAL_STATES:
        return state
    if state in EXECUTION_IN_FLIGHT:
        return OrchState.RECONCILIATION_REQUIRED
    if state == OrchState.RECONCILIATION_REQUIRED:
        if has_result:
            return OrchState.CHATGPT_DELIVERY_PENDING
        return OrchState.RECONCILIATION_REQUIRED
    if state == OrchState.RESULT_PERSISTED:
        return OrchState.CHATGPT_DELIVERY_PENDING
    if state == OrchState.CHATGPT_DELIVERED:
        return OrchState.CHATGPT_REVIEW_PENDING
    if state == OrchState.EXECUTION_INTERRUPTED:
        return OrchState.RECONCILIATION_REQUIRED
    if state == OrchState.PAUSED:
        return OrchState.PAUSED
    return state


def describe(state: OrchState) -> Dict[str, Optional[str]]:
    state = OrchState(state)
    return {
        "state": state.value,
        "terminal": is_terminal(state),
        "waiting": state in WAITING_STATES,
        "required_action": REQUIRED_ACTION.get(state),
    }
