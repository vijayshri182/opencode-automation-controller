"""WP-423: versioned, validated contracts for the ChatGPT <-> Controller <-> OpenCode loop.

These are plain dict contracts (no new dependency) with explicit ``schema_version``
fields so the wire format can evolve without ambiguity. Every validator returns
``(ok, errors)`` and never raises, so callers can persist a rejected record and
report it instead of crashing the orchestrator.

Design rules enforced here:

* Message identity is *never invented*. ``message_id`` is required and
  ``message_identity_source`` records whether it came from the UI or was derived
  deterministically from content (in which case it is marked as derived).
* Payload sizes are bounded before any persistence happens.
* Unknown extra keys are ignored rather than trusted.
"""

from typing import Any, Dict, List, Optional, Tuple

# --- schema identifiers --------------------------------------------------

INBOUND_MESSAGE_SCHEMA = "wp423.inbound_message.v1"
DEV_TASK_SCHEMA = "wp423.dev_task.v1"
EXECUTION_SCHEMA = "wp423.execution.v1"
DELIVERY_SCHEMA = "wp423.delivery.v1"
RESEARCH_TASK_SCHEMA = "wp_research.research_task.v1"
RESEARCH_RESULT_SCHEMA = "wp_research.research_result.v1"

SUPPORTED_SCHEMAS = {
    INBOUND_MESSAGE_SCHEMA,
    DEV_TASK_SCHEMA,
    EXECUTION_SCHEMA,
    DELIVERY_SCHEMA,
    RESEARCH_TASK_SCHEMA,
    RESEARCH_RESULT_SCHEMA,
}

# --- limits --------------------------------------------------------------

MAX_MESSAGE_CONTENT_CHARS = 40_000
MAX_TASK_DESCRIPTION_CHARS = 40_000
MAX_ID_CHARS = 200
MAX_SHORT_TEXT_CHARS = 500
MAX_LIST_ITEMS = 100

SOURCES = {"chatgpt"}
IDENTITY_SOURCES = {"ui", "derived_content_hash"}

RISK_CLASSES = {"low", "medium", "high", "critical"}
TASK_STATUSES = {
    "draft",
    "validated",
    "awaiting_approval",
    "ready",
    "running",
    "completed",
    "failed",
    "blocked",
    "cancelled",
}
EXECUTION_STATUSES = {
    "pending",
    "submitted",
    "running",
    "completed",
    "failed",
    "interrupted",
    "uncertain",
    "blocked",
    "cancelled",
}
DELIVERY_STATUSES = {
    "pending",
    "attempting",
    "delivered",
    "failed",
    "uncertain",
    "abandoned",
}

RESEARCH_TASK_STATUSES = {"pending", "running", "completed", "failed", "cancelled", "timeout"}
RESEARCH_EVIDENCE_TYPES = {"SEARCH_SNIPPET", "FULL_PAGE", "BROWSER_CAPTURE"}


class ContractError(ValueError):
    """Raised only by the ``*_strict`` helpers."""


def _add(errors: List[str], message: str) -> None:
    errors.append(message)


def _req_str(
    payload: Dict[str, Any],
    key: str,
    errors: List[str],
    max_len: int = MAX_ID_CHARS,
    allow_empty: bool = False,
) -> str:
    value = payload.get(key)
    if not isinstance(value, str):
        _add(errors, f"{key}: must be a string")
        return ""
    if not allow_empty and not value.strip():
        _add(errors, f"{key}: must be non-empty")
        return ""
    if len(value) > max_len:
        _add(errors, f"{key}: exceeds {max_len} characters")
        return ""
    return value


def _opt_str(payload: Dict[str, Any], key: str, errors: List[str], max_len: int = MAX_SHORT_TEXT_CHARS) -> Optional[str]:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        _add(errors, f"{key}: must be a string or null")
        return None
    if len(value) > max_len:
        _add(errors, f"{key}: exceeds {max_len} characters")
        return None
    return value


def _req_number(payload: Dict[str, Any], key: str, errors: List[str]) -> Optional[float]:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _add(errors, f"{key}: must be a number")
        return None
    return float(value)


def _str_list(payload: Dict[str, Any], key: str, errors: List[str], max_len: int = MAX_SHORT_TEXT_CHARS) -> List[str]:
    value = payload.get(key)
    if value is None:
        return []
    if not isinstance(value, list):
        _add(errors, f"{key}: must be a list")
        return []
    if len(value) > MAX_LIST_ITEMS:
        _add(errors, f"{key}: exceeds {MAX_LIST_ITEMS} items")
        return []
    out: List[str] = []
    for i, item in enumerate(value):
        if not isinstance(item, str):
            _add(errors, f"{key}[{i}]: must be a string")
            continue
        if len(item) > max_len:
            _add(errors, f"{key}[{i}]: exceeds {max_len} characters")
            continue
        out.append(item)
    return out


def _check_schema(payload: Dict[str, Any], expected: str, errors: List[str]) -> None:
    version = payload.get("schema_version")
    if version != expected:
        _add(errors, f"schema_version: expected {expected!r}, got {version!r}")


# --- inbound ChatGPT message --------------------------------------------


def validate_inbound_message(payload: Any) -> Tuple[bool, List[str]]:
    """Validate a ChatGPT inbound message envelope.

    ``received_at`` is required: the controller stamps it at ingestion time, so
    it is never a fabricated UI timestamp. ``message_timestamp`` is optional and
    is ``None`` when the UI does not expose one.
    """
    errors: List[str] = []
    if not isinstance(payload, dict):
        return False, ["payload: must be an object"]

    _check_schema(payload, INBOUND_MESSAGE_SCHEMA, errors)
    _req_str(payload, "message_id", errors)
    source = _req_str(payload, "source", errors, max_len=32)
    if source and source not in SOURCES:
        _add(errors, f"source: must be one of {sorted(SOURCES)}")
    _req_str(payload, "project_id", errors)
    _req_str(payload, "conversation_id", errors)
    _opt_str(payload, "message_timestamp", errors)
    _req_str(payload, "message_content", errors, max_len=MAX_MESSAGE_CONTENT_CHARS)
    _req_str(payload, "correlation_id", errors)
    _req_number(payload, "received_at", errors)

    identity = payload.get("message_identity_source", "ui")
    if identity not in IDENTITY_SOURCES:
        _add(errors, f"message_identity_source: must be one of {sorted(IDENTITY_SOURCES)}")

    return (not errors), errors


# --- development task ---------------------------------------------------


def validate_dev_task(payload: Any) -> Tuple[bool, List[str]]:
    errors: List[str] = []
    if not isinstance(payload, dict):
        return False, ["payload: must be an object"]

    _check_schema(payload, DEV_TASK_SCHEMA, errors)
    _req_str(payload, "task_id", errors)
    _req_str(payload, "mission_id", errors)
    _req_str(payload, "originating_message_id", errors)
    _req_str(payload, "task_title", errors)
    _req_str(payload, "task_description", errors, max_len=MAX_TASK_DESCRIPTION_CHARS)
    _req_str(payload, "target_repository", errors)
    _req_str(payload, "target_branch", errors)
    _str_list(payload, "scope", errors)
    _str_list(payload, "acceptance_criteria", errors)
    _str_list(payload, "required_verification", errors)

    risk = payload.get("risk_classification")
    if risk not in RISK_CLASSES:
        _add(errors, f"risk_classification: must be one of {sorted(RISK_CLASSES)}")

    approvals = payload.get("approval_requirements")
    if approvals is not None and not isinstance(approvals, list):
        _add(errors, "approval_requirements: must be a list")

    status = payload.get("task_status")
    if status not in TASK_STATUSES:
        _add(errors, f"task_status: must be one of {sorted(TASK_STATUSES)}")

    return (not errors), errors


# --- opencode execution -------------------------------------------------


def validate_execution(payload: Any) -> Tuple[bool, List[str]]:
    errors: List[str] = []
    if not isinstance(payload, dict):
        return False, ["payload: must be an object"]

    _check_schema(payload, EXECUTION_SCHEMA, errors)
    _req_str(payload, "execution_id", errors)
    _req_str(payload, "task_id", errors)
    _opt_str(payload, "opencode_session_id", errors)
    _req_number(payload, "submitted_at", errors)

    exec_status = payload.get("execution_status")
    if exec_status not in EXECUTION_STATUSES:
        _add(errors, f"execution_status: must be one of {sorted(EXECUTION_STATUSES)}")

    completion = payload.get("completion_status")
    if completion not in (None, "", "completed", "failed", "partial"):
        _add(errors, "completion_status: must be null, completed, failed or partial")

    _str_list(payload, "changed_files", errors)
    _opt_str(payload, "execution_output", errors, max_len=MAX_MESSAGE_CONTENT_CHARS)
    _opt_str(payload, "error", errors, max_len=MAX_MESSAGE_CONTENT_CHARS)
    return (not errors), errors


# --- chatgpt delivery ---------------------------------------------------


def validate_delivery(payload: Any) -> Tuple[bool, List[str]]:
    errors: List[str] = []
    if not isinstance(payload, dict):
        return False, ["payload: must be an object"]

    _check_schema(payload, DELIVERY_SCHEMA, errors)
    _req_str(payload, "delivery_id", errors)
    _req_str(payload, "originating_execution_id", errors)
    _req_str(payload, "target_project_id", errors)
    _req_str(payload, "target_conversation_id", errors)
    _req_str(payload, "response_content", errors, max_len=MAX_MESSAGE_CONTENT_CHARS)

    status = payload.get("delivery_status")
    if status not in DELIVERY_STATUSES:
        _add(errors, f"delivery_status: must be one of {sorted(DELIVERY_STATUSES)}")

    attempts = payload.get("attempts", 0)
    if isinstance(attempts, bool) or not isinstance(attempts, int) or attempts < 0:
        _add(errors, "attempts: must be a non-negative integer")

    return (not errors), errors


# --- constructors (stamp the schema version) ----------------------------


def inbound_message(
    *,
    message_id: str,
    project_id: str,
    conversation_id: str,
    message_content: str,
    correlation_id: str,
    received_at: float,
    message_timestamp: Optional[str] = None,
    message_identity_source: str = "ui",
    source: str = "chatgpt",
) -> Dict[str, Any]:
    return {
        "schema_version": INBOUND_MESSAGE_SCHEMA,
        "message_id": message_id,
        "source": source,
        "project_id": project_id,
        "conversation_id": conversation_id,
        "message_timestamp": message_timestamp,
        "message_content": message_content,
        "correlation_id": correlation_id,
        "received_at": received_at,
        "message_identity_source": message_identity_source,
    }


def dev_task(
    *,
    task_id: str,
    mission_id: str,
    originating_message_id: str,
    task_title: str,
    task_description: str,
    target_repository: str,
    target_branch: str,
    risk_classification: str,
    task_status: str = "draft",
    scope: Optional[List[str]] = None,
    acceptance_criteria: Optional[List[str]] = None,
    required_verification: Optional[List[str]] = None,
    approval_requirements: Optional[List[str]] = None,
) -> Dict[str, Any]:
    return {
        "schema_version": DEV_TASK_SCHEMA,
        "task_id": task_id,
        "mission_id": mission_id,
        "originating_message_id": originating_message_id,
        "task_title": task_title,
        "task_description": task_description,
        "target_repository": target_repository,
        "target_branch": target_branch,
        "scope": list(scope or []),
        "acceptance_criteria": list(acceptance_criteria or []),
        "required_verification": list(required_verification or []),
        "risk_classification": risk_classification,
        "approval_requirements": list(approval_requirements or []),
        "task_status": task_status,
    }


def execution(
    *,
    execution_id: str,
    task_id: str,
    submitted_at: float,
    execution_status: str = "pending",
    opencode_session_id: Optional[str] = None,
) -> Dict[str, Any]:
    return {
        "schema_version": EXECUTION_SCHEMA,
        "execution_id": execution_id,
        "task_id": task_id,
        "opencode_session_id": opencode_session_id,
        "submitted_at": submitted_at,
        "execution_status": execution_status,
        "completion_status": None,
        "changed_files": [],
        "test_results": {},
        "execution_output": None,
        "error": None,
        "verification_evidence": {},
    }


def delivery(
    *,
    delivery_id: str,
    originating_execution_id: str,
    target_project_id: str,
    target_conversation_id: str,
    response_content: str,
) -> Dict[str, Any]:
    return {
        "schema_version": DELIVERY_SCHEMA,
        "delivery_id": delivery_id,
        "originating_execution_id": originating_execution_id,
        "target_project_id": target_project_id,
        "target_conversation_id": target_conversation_id,
        "response_content": response_content,
        "delivery_status": "pending",
        "attempts": 0,
        "confirmation_evidence": {},
    }


# --- research task -------------------------------------------------------

RESEARCH_TASK_STATUSES = {"pending", "running", "completed", "failed", "cancelled", "timeout"}
RESEARCH_EVIDENCE_TYPES = {"SEARCH_SNIPPET", "FULL_PAGE", "BROWSER_CAPTURE"}


def research_task(
    *,
    research_id: str,
    idempotency_key: str,
    prompt: str,
    read_only: bool = True,
    timeout_seconds: float = 120.0,
    max_results: int = 10,
    created_at: float,
    status: str = "pending",
) -> Dict[str, Any]:
    return {
        "schema_version": RESEARCH_TASK_SCHEMA,
        "research_id": research_id,
        "idempotency_key": idempotency_key,
        "prompt": prompt,
        "read_only": read_only,
        "timeout_seconds": timeout_seconds,
        "max_results": max_results,
        "status": status,
        "created_at": created_at,
    }


def validate_research_task(payload: Any) -> Tuple[bool, List[str]]:
    errors: List[str] = []
    if not isinstance(payload, dict):
        return False, ["payload: must be an object"]
    _check_schema(payload, RESEARCH_TASK_SCHEMA, errors)
    _req_str(payload, "research_id", errors)
    _req_str(payload, "idempotency_key", errors)
    _req_str(payload, "prompt", errors, max_len=MAX_MESSAGE_CONTENT_CHARS)
    if not isinstance(payload.get("read_only"), bool):
        _add(errors, "read_only: must be a boolean")
    ts = payload.get("timeout_seconds")
    if not isinstance(ts, (int, float)) or isinstance(ts, bool) or ts <= 0 or ts > 600:
        _add(errors, "timeout_seconds: must be a number in (0, 600]")
    mr = payload.get("max_results")
    if not isinstance(mr, int) or isinstance(mr, bool) or mr < 1 or mr > 50:
        _add(errors, "max_results: must be an integer in [1, 50]")
    status = payload.get("status", "pending")
    if status not in RESEARCH_TASK_STATUSES:
        _add(errors, "status: must be one of " + str(sorted(RESEARCH_TASK_STATUSES)))
    _req_number(payload, "created_at", errors)
    return (not errors), errors


def research_result(
    *,
    research_id: str,
    status: str,
    completed_at: float,
    output: Optional[str] = None,
    error: Optional[str] = None,
    session_id: Optional[str] = None,
    evidence: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    return {
        "schema_version": RESEARCH_RESULT_SCHEMA,
        "research_id": research_id,
        "status": status,
        "completed_at": completed_at,
        "output": output,
        "error": error,
        "session_id": session_id,
        "evidence": evidence or [],
    }


def validate_research_result(payload: Any) -> Tuple[bool, List[str]]:
    errors: List[str] = []
    if not isinstance(payload, dict):
        return False, ["payload: must be an object"]
    _check_schema(payload, RESEARCH_RESULT_SCHEMA, errors)
    _req_str(payload, "research_id", errors)
    status = payload.get("status")
    if status not in RESEARCH_TASK_STATUSES:
        _add(errors, "status: must be one of " + str(sorted(RESEARCH_TASK_STATUSES)))
    _req_number(payload, "completed_at", errors)
    _opt_str(payload, "output", errors, max_len=MAX_MESSAGE_CONTENT_CHARS)
    _opt_str(payload, "error", errors, max_len=MAX_SHORT_TEXT_CHARS)
    _opt_str(payload, "session_id", errors)
    ev = payload.get("evidence", [])
    if not isinstance(ev, list):
        _add(errors, "evidence: must be a list")
    elif len(ev) > MAX_LIST_ITEMS:
        _add(errors, "evidence: exceeds " + str(MAX_LIST_ITEMS) + " items")
    return (not errors), errors
