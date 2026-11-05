import json
import sqlite3
import threading
import time
from pathlib import Path
from contextlib import closing, contextmanager
from typing import Any, Dict, Iterator, List, Optional, Tuple

from .models import TaskRecord, TaskStatus, ApprovalRecord


SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    idempotency_key TEXT NOT NULL,
    task_text TEXT NOT NULL,
    metadata_json TEXT NOT NULL,
    workspace TEXT NOT NULL,
    branch TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at REAL NOT NULL,
    validated_at REAL,
    approved_at REAL,
    approval_hash TEXT,
    approved_by TEXT,
    queued_at REAL,
    started_at REAL,
    finished_at REAL,
    progress TEXT,
    result_json TEXT,
    error TEXT,
    opencode_session_id TEXT,
    timeout_seconds REAL NOT NULL,
    content_hash TEXT NOT NULL,
    cancel_requested INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_idem ON tasks(idempotency_key);

CREATE TABLE IF NOT EXISTS approvals (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    approved_at REAL NOT NULL,
    approved_by TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT,
    event TEXT NOT NULL,
    details TEXT,
    created_at REAL NOT NULL
);
"""


#: WP-423 orchestration tables. Additive: the WP-GUI02 ``tasks``/``approvals``
#: tables above are untouched so the existing controller keeps working.
#:
#: Uniqueness constraints are the duplicate-prevention mechanism, not an
#: application-level check: ``inbound_messages.message_id`` (idempotent
#: ingestion), ``dev_tasks(mission_id, originating_message_id)`` (one task per
#: message), ``executions.task_id`` (one execution per task) and
#: ``deliveries.originating_execution_id`` (one delivery per execution).
ORCH_SCHEMA = """
CREATE TABLE IF NOT EXISTS missions (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    target_repository TEXT NOT NULL,
    target_branch TEXT NOT NULL,
    state TEXT NOT NULL,
    paused INTEGER NOT NULL DEFAULT 0,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    required_action TEXT,
    last_error TEXT
);

CREATE TABLE IF NOT EXISTS inbound_messages (
    message_id TEXT PRIMARY KEY,
    schema_version TEXT NOT NULL,
    source TEXT NOT NULL,
    project_id TEXT NOT NULL,
    conversation_id TEXT NOT NULL,
    message_timestamp TEXT,
    message_identity_source TEXT NOT NULL,
    message_content TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    correlation_id TEXT NOT NULL,
    received_at REAL NOT NULL,
    processed INTEGER NOT NULL DEFAULT 0,
    duplicate_count INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_inbound_conv ON inbound_messages(conversation_id, received_at);

CREATE TABLE IF NOT EXISTS dev_tasks (
    task_id TEXT PRIMARY KEY,
    schema_version TEXT NOT NULL,
    mission_id TEXT NOT NULL,
    originating_message_id TEXT NOT NULL,
    task_title TEXT NOT NULL,
    task_description TEXT NOT NULL,
    target_repository TEXT NOT NULL,
    target_branch TEXT NOT NULL,
    scope_json TEXT NOT NULL,
    acceptance_json TEXT NOT NULL,
    verification_json TEXT NOT NULL,
    risk_classification TEXT NOT NULL,
    approvals_json TEXT NOT NULL,
    task_status TEXT NOT NULL,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    UNIQUE (mission_id, originating_message_id)
);
CREATE INDEX IF NOT EXISTS idx_dev_tasks_status ON dev_tasks(task_status);

CREATE TABLE IF NOT EXISTS executions (
    execution_id TEXT PRIMARY KEY,
    schema_version TEXT NOT NULL,
    task_id TEXT NOT NULL UNIQUE,
    opencode_session_id TEXT,
    submitted_at REAL NOT NULL,
    started_at REAL,
    completed_at REAL,
    execution_status TEXT NOT NULL,
    completion_status TEXT,
    changed_files_json TEXT NOT NULL,
    test_results_json TEXT NOT NULL,
    execution_output TEXT,
    error TEXT,
    verification_json TEXT NOT NULL,
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS deliveries (
    delivery_id TEXT PRIMARY KEY,
    schema_version TEXT NOT NULL,
    originating_execution_id TEXT NOT NULL UNIQUE,
    target_project_id TEXT NOT NULL,
    target_conversation_id TEXT NOT NULL,
    response_content TEXT NOT NULL,
    delivery_status TEXT NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    confirmation_json TEXT NOT NULL,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS approval_requests (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    risk_classification TEXT NOT NULL,
    requirements_json TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at REAL NOT NULL,
    decided_at REAL,
    decided_by TEXT,
    decision_reason TEXT
);
CREATE INDEX IF NOT EXISTS idx_approval_task ON approval_requests(task_id);

CREATE TABLE IF NOT EXISTS provider_state (
    provider TEXT PRIMARY KEY,
    available INTEGER NOT NULL DEFAULT 1,
    cooldown_until REAL,
    consecutive_failures INTEGER NOT NULL DEFAULT 0,
    retry_budget INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS checkpoints (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mission_id TEXT,
    task_id TEXT,
    execution_id TEXT,
    reason TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_checkpoint_mission ON checkpoints(mission_id, created_at);
"""

RESEARCH_SCHEMA = """
CREATE TABLE IF NOT EXISTS research_tasks (
    research_id TEXT PRIMARY KEY,
    idempotency_key TEXT NOT NULL UNIQUE,
    prompt TEXT NOT NULL,
    read_only INTEGER NOT NULL DEFAULT 1,
    timeout_seconds REAL NOT NULL DEFAULT 120.0,
    max_results INTEGER NOT NULL DEFAULT 10,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at REAL NOT NULL,
    started_at REAL,
    completed_at REAL,
    session_id TEXT,
    result_json TEXT,
    error TEXT,
    cancel_requested INTEGER NOT NULL DEFAULT 0,
    cancelled_at REAL
);
CREATE INDEX IF NOT EXISTS idx_research_tasks_status ON research_tasks(status);
CREATE INDEX IF NOT EXISTS idx_research_tasks_idempotency ON research_tasks(idempotency_key);
"""


class BridgeDB:
    def __init__(self, path: Path):
        self.path = Path(path)
        self._lock = threading.RLock()
        with closing(self._connect()) as conn:
            conn.executescript(SCHEMA)
            conn.executescript(ORCH_SCHEMA)
            conn.executescript(RESEARCH_SCHEMA)
            try:
                cols = {r[1] for r in conn.execute("PRAGMA table_info(executions)").fetchall()}
                if "started_at" not in cols:
                    conn.execute("ALTER TABLE executions ADD COLUMN started_at REAL")
                if "completed_at" not in cols:
                    conn.execute("ALTER TABLE executions ADD COLUMN completed_at REAL")
            except Exception:
                pass
            try:
                rcols = {r[1] for r in conn.execute("PRAGMA table_info(research_tasks)").fetchall()}
                if "cancel_requested" not in rcols:
                    conn.execute("ALTER TABLE research_tasks ADD COLUMN cancel_requested INTEGER NOT NULL DEFAULT 0")
                if "cancelled_at" not in rcols:
                    conn.execute("ALTER TABLE research_tasks ADD COLUMN cancelled_at REAL")
            except Exception:
                pass
            conn.commit()

    def _connect(self):
        conn = sqlite3.connect(str(self.path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """Atomic multi-row unit of work (``BEGIN IMMEDIATE`` + commit/rollback).

        Used wherever two records must land together — e.g. "message persisted"
        and "mission advanced" — so a crash cannot leave the pair inconsistent.
        """
        with self._lock:
            conn = self._connect()
            try:
                conn.execute("BEGIN IMMEDIATE")
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()

    def close(self):
        pass

    def _row_to_task(self, row) -> TaskRecord:
        return TaskRecord(
            id=row["id"],
            idempotency_key=row["idempotency_key"],
            task_text=row["task_text"],
            metadata=json.loads(row["metadata_json"] or "{}"),
            workspace=row["workspace"],
            branch=row["branch"],
            status=TaskStatus(row["status"]),
            created_at=row["created_at"],
            validated_at=row["validated_at"],
            approved_at=row["approved_at"],
            approval_hash=row["approval_hash"],
            approved_by=row["approved_by"],
            queued_at=row["queued_at"],
            started_at=row["started_at"],
            finished_at=row["finished_at"],
            progress=row["progress"] or "",
            result=json.loads(row["result_json"]) if row["result_json"] else None,
            error=row["error"],
            opencode_session_id=row["opencode_session_id"],
            timeout_seconds=row["timeout_seconds"],
            content_hash=row["content_hash"],
            cancel_requested=bool(row["cancel_requested"]),
        )

    def insert_task(self, task: TaskRecord) -> None:
        with self._lock:
            with closing(self._connect()) as conn:
                conn.execute(
                    """INSERT INTO tasks (id,idempotency_key,task_text,metadata_json,workspace,branch,status,created_at,validated_at,approved_at,approval_hash,approved_by,queued_at,started_at,finished_at,progress,result_json,error,opencode_session_id,timeout_seconds,content_hash,cancel_requested)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (task.id, task.idempotency_key, task.task_text, json.dumps(task.metadata), task.workspace, task.branch, task.status.value, task.created_at, task.validated_at, task.approved_at, task.approval_hash, task.approved_by, task.queued_at, task.started_at, task.finished_at, task.progress, json.dumps(task.result) if task.result is not None else None, task.error, task.opencode_session_id, task.timeout_seconds, task.content_hash, int(task.cancel_requested)),
                )
                conn.commit()

    def update_task(self, task: TaskRecord) -> None:
        with self._lock:
            with closing(self._connect()) as conn:
                conn.execute(
                    """UPDATE tasks SET status=?,validated_at=?,approved_at=?,approval_hash=?,approved_by=?,queued_at=?,started_at=?,finished_at=?,progress=?,result_json=?,error=?,opencode_session_id=?,cancel_requested=? WHERE id=?""",
                    (task.status.value, task.validated_at, task.approved_at, task.approval_hash, task.approved_by, task.queued_at, task.started_at, task.finished_at, task.progress, json.dumps(task.result) if task.result is not None else None, task.error, task.opencode_session_id, int(task.cancel_requested), task.id),
                )
                conn.commit()

    def get_task(self, task_id: str) -> Optional[TaskRecord]:
        with self._lock:
            with closing(self._connect()) as conn:
                row = conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
                return self._row_to_task(row) if row else None

    def list_tasks(self, limit: int = 20) -> List[TaskRecord]:
        with self._lock:
            with closing(self._connect()) as conn:
                rows = conn.execute("SELECT * FROM tasks ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
                return [self._row_to_task(r) for r in rows]

    def find_by_idempotency(self, key: str) -> Optional[TaskRecord]:
        with self._lock:
            with closing(self._connect()) as conn:
                row = conn.execute("SELECT * FROM tasks WHERE idempotency_key=? ORDER BY created_at DESC LIMIT 1", (key,)).fetchone()
                return self._row_to_task(row) if row else None

    def find_active_by_idempotency(self, key: str) -> Optional[TaskRecord]:
        with self._lock:
            with closing(self._connect()) as conn:
                rows = conn.execute("SELECT * FROM tasks WHERE idempotency_key=?", (key,)).fetchall()
                for r in rows:
                    t = self._row_to_task(r)
                    if t.status not in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.BLOCKED, TaskStatus.CANCELLED):
                        return t
                return None

    def insert_approval(self, approval: ApprovalRecord) -> None:
        with self._lock:
            with closing(self._connect()) as conn:
                conn.execute(
                    "INSERT INTO approvals (id,task_id,content_hash,approved_at,approved_by) VALUES (?,?,?,?,?)",
                    (approval.id, approval.task_id, approval.content_hash, approval.approved_at, approval.approved_by),
                )
                conn.commit()

    def get_approval(self, task_id: str) -> Optional[ApprovalRecord]:
        with self._lock:
            with closing(self._connect()) as conn:
                row = conn.execute("SELECT * FROM approvals WHERE task_id=? ORDER BY approved_at DESC LIMIT 1", (task_id,)).fetchone()
                if not row:
                    return None
                return ApprovalRecord(id=row["id"], task_id=row["task_id"], content_hash=row["content_hash"], approved_at=row["approved_at"], approved_by=row["approved_by"])

    def audit(self, task_id: Optional[str], event: str, details: str = "") -> None:
        with self._lock:
            with closing(self._connect()) as conn:
                conn.execute(
                    "INSERT INTO audit_events (task_id,event,details,created_at) VALUES (?,?,?,?)",
                    (task_id, event, details, time.time()),
                )
                conn.commit()

    def mark_interrupted_running(self) -> int:
        with self._lock:
            with closing(self._connect()) as conn:
                cur = conn.execute(
                    "UPDATE tasks SET status=?, error=?, finished_at=? WHERE status=?",
                    (TaskStatus.FAILED.value, "controller restarted; task interrupted", time.time(), TaskStatus.RUNNING.value),
                )
                conn.commit()
                return cur.rowcount

    # ------------------------------------------------------------------
    # WP-423 orchestration store
    # ------------------------------------------------------------------

    # missions

    def upsert_mission(
        self,
        mission_id: str,
        title: str,
        target_repository: str,
        target_branch: str,
        state: str,
    ) -> None:
        ts = time.time()
        with self._lock:
            with closing(self._connect()) as conn:
                conn.execute(
                    """INSERT INTO missions (id,title,target_repository,target_branch,state,paused,created_at,updated_at)
                       VALUES (?,?,?,?,?,0,?,?)
                       ON CONFLICT(id) DO UPDATE SET
                         state=excluded.state, updated_at=excluded.updated_at""",
                    (mission_id, title, target_repository, target_branch, state, ts, ts),
                )
                conn.commit()

    def get_mission(self, mission_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            with closing(self._connect()) as conn:
                row = conn.execute("SELECT * FROM missions WHERE id=?", (mission_id,)).fetchone()
                return dict(row) if row else None

    def set_mission_state(
        self, mission_id: str, state: str, required_action: Optional[str] = None, last_error: Optional[str] = None
    ) -> None:
        with self._lock:
            with closing(self._connect()) as conn:
                conn.execute(
                    "UPDATE missions SET state=?, required_action=?, last_error=?, updated_at=? WHERE id=?",
                    (state, required_action, last_error, time.time(), mission_id),
                )
                conn.commit()

    def set_mission_paused(self, mission_id: str, paused: bool, state: str) -> None:
        with self._lock:
            with closing(self._connect()) as conn:
                conn.execute(
                    "UPDATE missions SET paused=?, state=?, updated_at=? WHERE id=?",
                    (int(paused), state, time.time(), mission_id),
                )
                conn.commit()

    # inbound messages (idempotent)

    def ingest_inbound_message(self, msg: Dict[str, Any], content_hash: str) -> Tuple[bool, Dict[str, Any]]:
        """Persist an inbound message exactly once.

        Returns ``(inserted, row)``. A repeat ``message_id`` bumps
        ``duplicate_count`` and returns the original row with ``inserted=False``,
        so ingestion is idempotent without overwriting the first record.
        """
        with self._lock:
            with closing(self._connect()) as conn:
                conn.execute("BEGIN IMMEDIATE")
                try:
                    cur = conn.execute(
                        """INSERT INTO inbound_messages
                           (message_id,schema_version,source,project_id,conversation_id,message_timestamp,
                            message_identity_source,message_content,content_hash,correlation_id,received_at,processed,duplicate_count)
                           VALUES (?,?,?,?,?,?,?,?,?,?,?,0,0)
                           ON CONFLICT(message_id) DO NOTHING""",
                        (
                            msg["message_id"],
                            msg["schema_version"],
                            msg["source"],
                            msg["project_id"],
                            msg["conversation_id"],
                            msg.get("message_timestamp"),
                            msg.get("message_identity_source", "ui"),
                            msg["message_content"],
                            content_hash,
                            msg["correlation_id"],
                            msg["received_at"],
                        ),
                    )
                    inserted = cur.rowcount == 1
                    if not inserted:
                        conn.execute(
                            "UPDATE inbound_messages SET duplicate_count=duplicate_count+1 WHERE message_id=?",
                            (msg["message_id"],),
                        )
                    conn.commit()
                except Exception:
                    conn.rollback()
                    raise
                row = conn.execute(
                    "SELECT * FROM inbound_messages WHERE message_id=?", (msg["message_id"],)
                ).fetchone()
                return inserted, dict(row) if row else {}

    def get_inbound_message(self, message_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            with closing(self._connect()) as conn:
                row = conn.execute("SELECT * FROM inbound_messages WHERE message_id=?", (message_id,)).fetchone()
                return dict(row) if row else None

    def mark_inbound_processed(self, message_id: str) -> None:
        with self._lock:
            with closing(self._connect()) as conn:
                conn.execute("UPDATE inbound_messages SET processed=1 WHERE message_id=?", (message_id,))
                conn.commit()

    def list_inbound_messages(self, conversation_id: Optional[str] = None, limit: int = 20) -> List[Dict[str, Any]]:
        with self._lock:
            with closing(self._connect()) as conn:
                if conversation_id:
                    rows = conn.execute(
                        "SELECT * FROM inbound_messages WHERE conversation_id=? ORDER BY received_at DESC LIMIT ?",
                        (conversation_id, limit),
                    ).fetchall()
                else:
                    rows = conn.execute(
                        "SELECT * FROM inbound_messages ORDER BY received_at DESC LIMIT ?", (limit,)
                    ).fetchall()
                return [dict(r) for r in rows]

    def inbox_counts(self) -> Dict[str, int]:
        with self._lock:
            with closing(self._connect()) as conn:
                total = conn.execute("SELECT COUNT(*) FROM inbound_messages").fetchone()[0]
                processed = conn.execute("SELECT COUNT(*) FROM inbound_messages WHERE processed=1").fetchone()[0]
                duplicates = conn.execute("SELECT COUNT(*) FROM inbound_messages WHERE duplicate_count>0").fetchone()[0]
        return {"total": int(total), "processed": int(processed), "pending": int(total - processed), "with_duplicates": int(duplicates)}

    # development tasks

    def insert_dev_task(self, task: Dict[str, Any]) -> bool:
        """Insert a development task; returns False if this message already has one."""
        ts = time.time()
        with self._lock:
            with closing(self._connect()) as conn:
                cur = conn.execute(
                    """INSERT INTO dev_tasks
                       (task_id,schema_version,mission_id,originating_message_id,task_title,task_description,
                        target_repository,target_branch,scope_json,acceptance_json,verification_json,
                        risk_classification,approvals_json,task_status,created_at,updated_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                       ON CONFLICT DO NOTHING""",
                    (
                        task["task_id"],
                        task["schema_version"],
                        task["mission_id"],
                        task["originating_message_id"],
                        task["task_title"],
                        task["task_description"],
                        task["target_repository"],
                        task["target_branch"],
                        json.dumps(task.get("scope") or []),
                        json.dumps(task.get("acceptance_criteria") or []),
                        json.dumps(task.get("required_verification") or []),
                        task["risk_classification"],
                        json.dumps(task.get("approval_requirements") or []),
                        task["task_status"],
                        ts,
                        ts,
                    ),
                )
                conn.commit()
                return cur.rowcount == 1

    def _row_to_dev_task(self, row: sqlite3.Row) -> Dict[str, Any]:
        out = dict(row)
        out["scope"] = json.loads(out.pop("scope_json") or "[]")
        out["acceptance_criteria"] = json.loads(out.pop("acceptance_json") or "[]")
        out["required_verification"] = json.loads(out.pop("verification_json") or "[]")
        out["approval_requirements"] = json.loads(out.pop("approvals_json") or "[]")
        return out

    def get_dev_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            with closing(self._connect()) as conn:
                row = conn.execute("SELECT * FROM dev_tasks WHERE task_id=?", (task_id,)).fetchone()
                return self._row_to_dev_task(row) if row else None

    def get_dev_task_for_message(self, mission_id: str, message_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            with closing(self._connect()) as conn:
                row = conn.execute(
                    "SELECT * FROM dev_tasks WHERE mission_id=? AND originating_message_id=?",
                    (mission_id, message_id),
                ).fetchone()
                return self._row_to_dev_task(row) if row else None

    def set_dev_task_status(self, task_id: str, status: str) -> None:
        with self._lock:
            with closing(self._connect()) as conn:
                conn.execute(
                    "UPDATE dev_tasks SET task_status=?, updated_at=? WHERE task_id=?",
                    (status, time.time(), task_id),
                )
                conn.commit()

    def list_dev_tasks(self, mission_id: Optional[str] = None, limit: int = 20) -> List[Dict[str, Any]]:
        with self._lock:
            with closing(self._connect()) as conn:
                if mission_id:
                    rows = conn.execute(
                        "SELECT * FROM dev_tasks WHERE mission_id=? ORDER BY created_at DESC LIMIT ?",
                        (mission_id, limit),
                    ).fetchall()
                else:
                    rows = conn.execute(
                        "SELECT * FROM dev_tasks ORDER BY created_at DESC LIMIT ?", (limit,)
                    ).fetchall()
                return [self._row_to_dev_task(r) for r in rows]

    # executions

    def insert_execution(self, ex: Dict[str, Any]) -> bool:
        """Insert an execution intent. False when the task already has one."""
        ts = time.time()
        with self._lock:
            with closing(self._connect()) as conn:
                cur = conn.execute(
                    """INSERT INTO executions
                       (execution_id,schema_version,task_id,opencode_session_id,submitted_at,started_at,completed_at,execution_status,
                        completion_status,changed_files_json,test_results_json,execution_output,error,
                        verification_json,updated_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                       ON CONFLICT DO NOTHING""",
                    (
                        ex["execution_id"],
                        ex["schema_version"],
                        ex["task_id"],
                        ex.get("opencode_session_id"),
                        ex["submitted_at"],
                        ex.get("started_at", ex["submitted_at"]),
                        ex.get("completed_at"),
                        ex.get("execution_status", "pending"),
                        ex.get("completion_status"),
                        json.dumps(ex.get("changed_files") or []),
                        json.dumps(ex.get("test_results") or {}),
                        ex.get("execution_output"),
                        ex.get("error"),
                        json.dumps(ex.get("verification_evidence") or {}),
                        ts,
                    ),
                )
                conn.commit()
                return cur.rowcount == 1

    def _row_to_execution(self, row: sqlite3.Row) -> Dict[str, Any]:
        out = dict(row)
        out["changed_files"] = json.loads(out.pop("changed_files_json") or "[]")
        out["test_results"] = json.loads(out.pop("test_results_json") or "{}")
        out["verification_evidence"] = json.loads(out.pop("verification_json") or "{}")
        return out

    def get_execution(self, execution_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            with closing(self._connect()) as conn:
                row = conn.execute("SELECT * FROM executions WHERE execution_id=?", (execution_id,)).fetchone()
                return self._row_to_execution(row) if row else None

    def get_execution_for_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            with closing(self._connect()) as conn:
                row = conn.execute("SELECT * FROM executions WHERE task_id=?", (task_id,)).fetchone()
                return self._row_to_execution(row) if row else None

    def update_execution(self, execution_id: str, **fields: Any) -> None:
        if not fields:
            return
        mapping = {
            "opencode_session_id": ("opencode_session_id", lambda v: v),
            "execution_status": ("execution_status", lambda v: v),
            "completion_status": ("completion_status", lambda v: v),
            "changed_files": ("changed_files_json", lambda v: json.dumps(v or [])),
            "test_results": ("test_results_json", lambda v: json.dumps(v or {})),
            "execution_output": ("execution_output", lambda v: v),
            "error": ("error", lambda v: v),
            "verification_evidence": ("verification_json", lambda v: json.dumps(v or {})),
            "started_at": ("started_at", lambda v: v),
            "completed_at": ("completed_at", lambda v: v),
        }
        cols, values = [], []
        for key, value in fields.items():
            if key not in mapping:
                raise ValueError(f"unsupported execution field: {key}")
            col, conv = mapping[key]
            cols.append(f"{col}=?")
            values.append(conv(value))
        cols.append("updated_at=?")
        values.append(time.time())
        values.append(execution_id)
        with self._lock:
            with closing(self._connect()) as conn:
                conn.execute(f"UPDATE executions SET {', '.join(cols)} WHERE execution_id=?", tuple(values))
                conn.commit()

    # deliveries

    def insert_delivery(self, d: Dict[str, Any]) -> bool:
        ts = time.time()
        with self._lock:
            with closing(self._connect()) as conn:
                cur = conn.execute(
                    """INSERT INTO deliveries
                       (delivery_id,schema_version,originating_execution_id,target_project_id,target_conversation_id,
                        response_content,delivery_status,attempts,confirmation_json,created_at,updated_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?)
                       ON CONFLICT DO NOTHING""",
                    (
                        d["delivery_id"],
                        d["schema_version"],
                        d["originating_execution_id"],
                        d["target_project_id"],
                        d["target_conversation_id"],
                        d["response_content"],
                        d.get("delivery_status", "pending"),
                        int(d.get("attempts", 0)),
                        json.dumps(d.get("confirmation_evidence") or {}),
                        ts,
                        ts,
                    ),
                )
                conn.commit()
                return cur.rowcount == 1

    def _row_to_delivery(self, row: sqlite3.Row) -> Dict[str, Any]:
        out = dict(row)
        out["confirmation_evidence"] = json.loads(out.pop("confirmation_json") or "{}")
        return out

    def get_delivery(self, delivery_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            with closing(self._connect()) as conn:
                row = conn.execute("SELECT * FROM deliveries WHERE delivery_id=?", (delivery_id,)).fetchone()
                return self._row_to_delivery(row) if row else None

    def get_delivery_for_execution(self, execution_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            with closing(self._connect()) as conn:
                row = conn.execute(
                    "SELECT * FROM deliveries WHERE originating_execution_id=?", (execution_id,)
                ).fetchone()
                return self._row_to_delivery(row) if row else None

    def update_delivery(
        self,
        delivery_id: str,
        *,
        delivery_status: Optional[str] = None,
        attempts: Optional[int] = None,
        confirmation_evidence: Optional[Dict[str, Any]] = None,
    ) -> None:
        cols, values = [], []
        if delivery_status is not None:
            cols.append("delivery_status=?")
            values.append(delivery_status)
        if attempts is not None:
            cols.append("attempts=?")
            values.append(int(attempts))
        if confirmation_evidence is not None:
            cols.append("confirmation_json=?")
            values.append(json.dumps(confirmation_evidence))
        if not cols:
            return
        cols.append("updated_at=?")
        values.append(time.time())
        values.append(delivery_id)
        with self._lock:
            with closing(self._connect()) as conn:
                conn.execute(f"UPDATE deliveries SET {', '.join(cols)} WHERE delivery_id=?", tuple(values))
                conn.commit()

    # approval requests

    def create_approval_request(
        self, request_id: str, task_id: str, risk: str, requirements: List[str]
    ) -> None:
        with self._lock:
            with closing(self._connect()) as conn:
                conn.execute(
                    """INSERT INTO approval_requests (id,task_id,risk_classification,requirements_json,status,created_at)
                       VALUES (?,?,?,?,?,?)""",
                    (request_id, task_id, risk, json.dumps(requirements), "pending", time.time()),
                )
                conn.commit()

    def get_pending_approval_for_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            with closing(self._connect()) as conn:
                row = conn.execute(
                    "SELECT * FROM approval_requests WHERE task_id=? AND status='pending' ORDER BY created_at DESC LIMIT 1",
                    (task_id,),
                ).fetchone()
                if not row:
                    return None
                out = dict(row)
                out["requirements"] = json.loads(out.pop("requirements_json") or "[]")
                return out

    def decide_approval(self, request_id: str, decision: str, decided_by: str, reason: str = "") -> bool:
        with self._lock:
            with closing(self._connect()) as conn:
                cur = conn.execute(
                    """UPDATE approval_requests SET status=?, decided_at=?, decided_by=?, decision_reason=?
                       WHERE id=? AND status='pending'""",
                    (decision, time.time(), decided_by, reason, request_id),
                )
                conn.commit()
                return cur.rowcount == 1

    # provider availability / cooldowns

    def set_provider_state(
        self,
        provider: str,
        *,
        available: bool,
        cooldown_until: Optional[float] = None,
        consecutive_failures: int = 0,
        retry_budget: int = 0,
        last_error: str = "",
    ) -> None:
        with self._lock:
            with closing(self._connect()) as conn:
                conn.execute(
                    """INSERT INTO provider_state
                       (provider,available,cooldown_until,consecutive_failures,retry_budget,last_error,updated_at)
                       VALUES (?,?,?,?,?,?,?)
                       ON CONFLICT(provider) DO UPDATE SET
                         available=excluded.available, cooldown_until=excluded.cooldown_until,
                         consecutive_failures=excluded.consecutive_failures,
                         retry_budget=excluded.retry_budget,
                         last_error=excluded.last_error, updated_at=excluded.updated_at""",
                    (
                        provider,
                        int(bool(available)),
                        cooldown_until,
                        int(consecutive_failures),
                        int(retry_budget),
                        (last_error or "")[:500],
                        time.time(),
                    ),
                )
                conn.commit()

    def get_provider_state(self, provider: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            with closing(self._connect()) as conn:
                row = conn.execute("SELECT * FROM provider_state WHERE provider=?", (provider,)).fetchone()
                if not row:
                    return None
                out = dict(row)
                out["available"] = bool(out["available"])
                return out

    def list_provider_state(self) -> List[Dict[str, Any]]:
        with self._lock:
            with closing(self._connect()) as conn:
                rows = conn.execute("SELECT * FROM provider_state ORDER BY provider").fetchall()
                out = []
                for r in rows:
                    d = dict(r)
                    d["available"] = bool(d["available"])
                    out.append(d)
                return out

    # recovery checkpoints

    def save_checkpoint(
        self,
        reason: str,
        payload: Dict[str, Any],
        mission_id: Optional[str] = None,
        task_id: Optional[str] = None,
        execution_id: Optional[str] = None,
    ) -> int:
        with self._lock:
            with closing(self._connect()) as conn:
                cur = conn.execute(
                    """INSERT INTO checkpoints (mission_id,task_id,execution_id,reason,payload_json,created_at)
                       VALUES (?,?,?,?,?,?)""",
                    (mission_id, task_id, execution_id, reason, json.dumps(payload, default=str), time.time()),
                )
                conn.commit()
                return int(cur.lastrowid)

    def latest_checkpoint(self, mission_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        with self._lock:
            with closing(self._connect()) as conn:
                if mission_id:
                    row = conn.execute(
                        "SELECT * FROM checkpoints WHERE mission_id=? ORDER BY created_at DESC, id DESC LIMIT 1",
                        (mission_id,),
                    ).fetchone()
                else:
                    row = conn.execute(
                        "SELECT * FROM checkpoints ORDER BY created_at DESC, id DESC LIMIT 1"
                    ).fetchone()
                if not row:
                    return None
                out = dict(row)
                out["payload"] = json.loads(out.pop("payload_json") or "{}")
                return out

    def audit_orch(self, event: str, ref: str = "", details: str = "") -> None:
        """Structured audit row for orchestration events (reuses audit_events)."""
        self.audit(ref or None, event, details)

    def list_audit(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self._lock:
            with closing(self._connect()) as conn:
                rows = conn.execute(
                    "SELECT * FROM audit_events ORDER BY created_at DESC, id DESC LIMIT ?", (limit,)
                ).fetchall()
                return [dict(r) for r in rows]

    def insert_research_task(self, task: Dict[str, Any]) -> bool:
        """Insert a research task; returns False if idempotency key already exists."""
        ts = time.time()
        with self._lock:
            with closing(self._connect()) as conn:
                cur = conn.execute(
                    """INSERT INTO research_tasks
                       (research_id,idempotency_key,prompt,read_only,timeout_seconds,max_results,
                        status,created_at,started_at,completed_at,session_id,result_json,error)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                       ON CONFLICT DO NOTHING""",
                    (
                        task["research_id"],
                        task["idempotency_key"],
                        task["prompt"],
                        1 if task.get("read_only", True) else 0,
                        float(task.get("timeout_seconds", 120.0)),
                        int(task.get("max_results", 10)),
                        task.get("status", "pending"),
                        float(task.get("created_at", ts)),
                        task.get("started_at"),
                        task.get("completed_at"),
                        task.get("session_id"),
                        task.get("result_json"),
                        task.get("error"),
                    ),
                )
                conn.commit()
                return cur.rowcount == 1

    def get_research_task(self, research_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            with closing(self._connect()) as conn:
                row = conn.execute(
                    "SELECT * FROM research_tasks WHERE research_id = ?", (research_id,)
                ).fetchone()
                return dict(row) if row else None

    def get_research_task_by_idempotency(self, key: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            with closing(self._connect()) as conn:
                row = conn.execute(
                    "SELECT * FROM research_tasks WHERE idempotency_key = ?", (key,)
                ).fetchone()
                return dict(row) if row else None

    def update_research_task(self, research_id: str, **fields: Any) -> None:
        if not fields:
            return
        cols = []
        vals = []
        for k, v in fields.items():
            cols.append(k + " = ?")
            vals.append(v)
        vals.append(research_id)
        with self._lock:
            with closing(self._connect()) as conn:
                conn.execute(
                    "UPDATE research_tasks SET " + ", ".join(cols) + " WHERE research_id = ?",
                    tuple(vals),
                )
                conn.commit()

    def list_research_tasks(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self._lock:
            with closing(self._connect()) as conn:
                rows = conn.execute(
                    "SELECT * FROM research_tasks ORDER BY created_at DESC LIMIT ?", (limit,)
                ).fetchall()
                return [dict(r) for r in rows]

    def cancel_research_task(self, research_id: str) -> bool:
        """Mark a research task as cancelled (idempotent). Returns True if row updated."""
        with self._lock:
            with closing(self._connect()) as conn:
                cur = conn.execute(
                    "UPDATE research_tasks SET cancel_requested=1, cancelled_at=? "
                    "WHERE research_id=? AND status IN ('pending','running')",
                    (time.time(), research_id),
                )
                conn.commit()
                return cur.rowcount == 1
