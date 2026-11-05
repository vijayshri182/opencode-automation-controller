import hashlib
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class TaskStatus(str, Enum):
    DRAFT = "draft"
    VALIDATED = "validated"
    AWAITING_APPROVAL = "awaiting_approval"
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"


TERMINAL_STATUSES = {TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.BLOCKED, TaskStatus.CANCELLED}

SENSITIVE_BLOCKED = "blocked_sensitive"


@dataclass
class TaskRecord:
    id: str
    idempotency_key: str
    task_text: str
    metadata: Dict[str, Any]
    workspace: str
    branch: str
    status: TaskStatus
    created_at: float
    validated_at: Optional[float] = None
    approved_at: Optional[float] = None
    approval_hash: Optional[str] = None
    approved_by: Optional[str] = None
    queued_at: Optional[float] = None
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    progress: str = ""
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    opencode_session_id: Optional[str] = None
    timeout_seconds: float = 300.0
    content_hash: str = ""
    cancel_requested: bool = False


@dataclass
class ApprovalRecord:
    id: str
    task_id: str
    content_hash: str
    approved_at: float
    approved_by: str


def content_hash(task_text: str, metadata: Dict[str, Any], workspace: str) -> str:
    payload = json.dumps({"task": task_text, "metadata": metadata, "workspace": workspace}, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def idempotency_key(task_text: str, metadata: Dict[str, Any], workspace: str) -> str:
    return content_hash(task_text, metadata, workspace)


def redact_secrets(text: str) -> str:
    # Best-effort: never store obvious token-like values; this is a safety net only.
    if not text:
        return text
    out = text
    for key in ("OPENCODE_SERVER_PASSWORD", "MCP_AUTH_TOKEN", "UPSTOX", "TOKEN"):
        # no-op placeholder; real redaction happens by not collecting secrets
        pass
    return out


def now() -> float:
    return time.time()