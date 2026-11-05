import json
import logging
import subprocess
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from .config import DEV_WORKSPACE, DEFAULT_TIMEOUT_SECONDS, POLL_INTERVAL_SECONDS
from .db import BridgeDB
from .models import TaskRecord, TaskStatus, TERMINAL_STATUSES, content_hash, idempotency_key, now
from .opencode_adapter import OpenCodeAdapter, OpenCodeError
from .safety import validate_workspace, validate_branch, validate_task_text

logger = logging.getLogger("opencode_bridge.controller")


class ControllerError(Exception):
    pass


class TaskController:
    def __init__(self, db: BridgeDB, adapter: OpenCodeAdapter, auto_worker: bool = True):
        self.db = db
        self.adapter = adapter
        self._lock = threading.RLock()
        self._worker_stop = threading.Event()
        self._worker_thread = None
        # recover interrupted
        self.db.mark_interrupted_running()
        if auto_worker:
            self.start_worker()

    def start_worker(self):
        if self._worker_thread and self._worker_thread.is_alive():
            return
        self._worker_stop.clear()
        self._worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
        self._worker_thread.start()

    def stop_worker(self):
        self._worker_stop.set()
        if self._worker_thread:
            self._worker_thread.join(timeout=5)

    def _worker_loop(self):
        while not self._worker_stop.is_set():
            task = self._next_queued()
            if task is None:
                time.sleep(0.5)
                continue
            self._execute_task(task)

    def _next_queued(self) -> Optional[TaskRecord]:
        for t in self.db.list_tasks(limit=100):
            if t.status == TaskStatus.QUEUED:
                return t
        return None

    def validate(self, task_text: str, workspace: str, branch_expected: str = None) -> Dict[str, Any]:
        ok, msg = validate_workspace(workspace)
        if not ok:
            return {"ok": False, "reason": msg}
        ok, msg, actual_branch = validate_branch(workspace)
        if not ok:
            return {"ok": False, "reason": msg, "branch": actual_branch}
        ok, msg = validate_task_text(task_text)
        if not ok:
            return {"ok": False, "reason": msg}
        return {"ok": True, "reason": "ok", "branch": actual_branch}

    def submit_task(self, task_text: str, metadata: Optional[Dict[str, Any]] = None, workspace: str = None, timeout_seconds: float = None, idempotency: Optional[str] = None) -> Dict[str, Any]:
        metadata = metadata or {}
        workspace = workspace or str(DEV_WORKSPACE)
        # validation
        v = self.validate(task_text, workspace)
        if not v["ok"]:
            # create blocked task record? We'll return blocked without DB maybe. But spec wants execution record.
            tid = str(uuid.uuid4())
            status = TaskStatus.BLOCKED
            if "sensitive" in v["reason"]:
                status = TaskStatus.BLOCKED
            tr = TaskRecord(
                id=tid,
                idempotency_key=idempotency or idempotency_key(task_text, metadata, workspace),
                task_text=task_text,
                metadata=metadata,
                workspace=workspace,
                branch=v.get("branch", ""),
                status=status,
                created_at=now(),
                content_hash=content_hash(task_text, metadata, workspace),
                error=v["reason"],
                timeout_seconds=timeout_seconds or DEFAULT_TIMEOUT_SECONDS,
            )
            self.db.insert_task(tr)
            self.db.audit(tid, "submit_blocked", v["reason"])
            return {"task_id": tid, "status": status.value, "reason": v["reason"]}
        # duplicate check
        key = idempotency or idempotency_key(task_text, metadata, workspace)
        existing = self.db.find_active_by_idempotency(key)
        if existing is not None:
            self.db.audit(existing.id, "duplicate_submit", "returned existing task")
            return {"task_id": existing.id, "status": existing.status.value, "duplicate": True, "reason": "duplicate active task"}
        tid = str(uuid.uuid4())
        ch = content_hash(task_text, metadata, workspace)
        branch = v.get("branch", "")
        tr = TaskRecord(
            id=tid,
            idempotency_key=key,
            task_text=task_text,
            metadata=metadata,
            workspace=workspace,
            branch=branch,
            status=TaskStatus.AWAITING_APPROVAL,
            created_at=now(),
            validated_at=now(),
            content_hash=ch,
            timeout_seconds=timeout_seconds or DEFAULT_TIMEOUT_SECONDS,
        )
        self.db.insert_task(tr)
        self.db.audit(tid, "submitted", "awaiting approval")
        return {"task_id": tid, "status": TaskStatus.AWAITING_APPROVAL.value, "content_hash": ch}

    def approve_task(self, task_id: str, approved_by: str = "operator") -> Dict[str, Any]:
        task = self.db.get_task(task_id)
        if task is None:
            return {"ok": False, "reason": "task not found"}
        if task.status != TaskStatus.AWAITING_APPROVAL:
            return {"ok": False, "reason": f"task not awaiting approval (status={task.status.value})"}
        # bind approval to exact content
        approval_id = str(uuid.uuid4())
        from .models import ApprovalRecord
        rec = ApprovalRecord(id=approval_id, task_id=task_id, content_hash=task.content_hash, approved_at=now(), approved_by=approved_by)
        self.db.insert_approval(rec)
        task.status = TaskStatus.QUEUED
        task.approved_at = rec.approved_at
        task.approval_hash = task.content_hash
        task.approved_by = approved_by
        task.queued_at = now()
        self.db.update_task(task)
        self.db.audit(task_id, "approved", f"by {approved_by}")
        return {"ok": True, "task_id": task_id, "status": TaskStatus.QUEUED.value}

    def reject_task(self, task_id: str, reason: str = "") -> Dict[str, Any]:
        task = self.db.get_task(task_id)
        if task is None:
            return {"ok": False, "reason": "task not found"}
        if task.status in TERMINAL_STATUSES:
            return {"ok": False, "reason": "task already terminal"}
        task.status = TaskStatus.BLOCKED
        task.error = reason or "rejected by operator"
        task.finished_at = now()
        self.db.update_task(task)
        self.db.audit(task_id, "rejected", reason)
        return {"ok": True, "task_id": task_id, "status": TaskStatus.BLOCKED.value}

    def invalidate_approval_if_modified(self, task_id: str, new_task_text: str) -> bool:
        task = self.db.get_task(task_id)
        if task is None or task.approval_hash is None:
            return False
        new_hash = content_hash(new_task_text, task.metadata, task.workspace)
        if new_hash != task.approval_hash:
            # invalidate
            task.approval_hash = None
            task.approved_at = None
            if task.status == TaskStatus.QUEUED:
                task.status = TaskStatus.AWAITING_APPROVAL
            self.db.update_task(task)
            self.db.audit(task_id, "approval_invalidated", "task content changed")
            return True
        return False

    def get_status(self, task_id: str) -> Dict[str, Any]:
        task = self.db.get_task(task_id)
        if task is None:
            return {"ok": False, "reason": "task not found"}
        return {
            "ok": True,
            "task_id": task.id,
            "status": task.status.value,
            "created_at": task.created_at,
            "started_at": task.started_at,
            "finished_at": task.finished_at,
            "progress": task.progress,
            "error": task.error,
            "cancel_requested": task.cancel_requested,
        }

    def get_result(self, task_id: str) -> Dict[str, Any]:
        task = self.db.get_task(task_id)
        if task is None:
            return {"ok": False, "reason": "task not found", "status": "missing"}
        if task.status not in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.BLOCKED, TaskStatus.CANCELLED):
            return {"ok": False, "reason": "result not ready", "status": task.status.value}
        return {
            "ok": True,
            "task_id": task.id,
            "status": task.status.value,
            "result": task.result,
            "error": task.error,
            "started_at": task.started_at,
            "finished_at": task.finished_at,
        }

    def list_recent(self, limit: int = 20) -> List[Dict[str, Any]]:
        out = []
        for t in self.db.list_tasks(limit=limit):
            out.append({
                "task_id": t.id,
                "status": t.status.value,
                "created_at": t.created_at,
                "progress": t.progress,
                "error": t.error,
            })
        return out

    def cancel_task(self, task_id: str, reason: str = "") -> Dict[str, Any]:
        task = self.db.get_task(task_id)
        if task is None:
            return {"ok": False, "reason": "task not found"}
        if task.status in TERMINAL_STATUSES:
            return {"ok": False, "reason": f"task already terminal ({task.status.value})"}
        task.cancel_requested = True
        if task.status == TaskStatus.RUNNING and task.opencode_session_id:
            try:
                self.adapter.abort(task.opencode_session_id)
            except Exception:
                pass
        if task.status in (TaskStatus.QUEUED, TaskStatus.AWAITING_APPROVAL):
            task.status = TaskStatus.CANCELLED
            task.finished_at = now()
            task.error = reason or "cancelled by operator"
        self.db.update_task(task)
        self.db.audit(task_id, "cancel_requested", reason)
        return {"ok": True, "task_id": task_id, "status": task.status.value, "cancel_requested": True}

    def _execute_task(self, task: TaskRecord):
        # re-fetch latest
        task = self.db.get_task(task.id)
        if task is None or task.status != TaskStatus.QUEUED:
            return
        if task.cancel_requested:
            task.status = TaskStatus.CANCELLED
            task.finished_at = now()
            self.db.update_task(task)
            return
        task.status = TaskStatus.RUNNING
        task.started_at = now()
        task.progress = "starting"
        logger.info("Task %s started", task.id)
        self.db.update_task(task)
        self.db.audit(task.id, "running", "")
        session_id = None
        try:
            # re-validate
            v = self.validate(task.task_text, task.workspace)
            if not v["ok"]:
                raise ControllerError(v["reason"])
            # approval check
            approval = self.db.get_approval(task.id)
            if approval is None or approval.content_hash != task.content_hash:
                raise ControllerError("approval missing or invalidated")
            # OpenCode health
            try:
                self.adapter.health()
            except Exception as e:
                raise ControllerError(f"opencode health failed: {e}")
            # create session
            sess = self.adapter.create_session(title=f"bridge-task-{task.id[:8]}")
            session_id = sess.get("id") if isinstance(sess, dict) else None
            if not session_id:
                raise ControllerError("opencode did not return session id")
            task.opencode_session_id = session_id
            task.progress = "session created"
            self.db.update_task(task)
            # wrap prompt with safety preamble
            prompt = self._build_prompt(task)
            model = task.metadata.get("model") if isinstance(task.metadata, dict) else None
            self.adapter.send_prompt_async(session_id, prompt, model=model)
            task.progress = "prompt sent; waiting for response"
            self.db.update_task(task)
            # poll
            deadline = time.time() + task.timeout_seconds
            final_text = ""
            while time.time() < deadline:
                if self._is_cancel_requested(task.id):
                    self.adapter.abort(session_id)
                    task = self.db.get_task(task.id)
                    task.status = TaskStatus.CANCELLED
                    task.finished_at = now()
                    task.error = "cancelled during execution"
                    self.db.update_task(task)
                    return
                msgs = self.adapter.get_messages(session_id, limit=50)
                txt = OpenCodeAdapter.extract_final_assistant(msgs)
                if txt:
                    final_text = txt
                    # allow a short settle; break
                    break
                task.progress = f"waiting ({int(time.time()-task.started_at)}s)"
                self.db.update_task(task)
                time.sleep(POLL_INTERVAL_SECONDS)
            if not final_text:
                raise ControllerError("timeout or no assistant response")
            # collect git evidence (read-only)
            git_status = self._git_status(task.workspace)
            git_diff_stat = self._git_diff_stat(task.workspace)
            result = {
                "final_response": final_text,
                "opencode_session_id": session_id,
                "git_status": git_status,
                "git_diff_stat": git_diff_stat,
            }
            task = self.db.get_task(task.id)
            task.status = TaskStatus.COMPLETED
            task.finished_at = now()
            task.progress = "completed"
            task.result = result
            self.db.update_task(task)
            self.db.audit(task.id, "completed", "")
            logger.info("Task %s completed", task.id)
        except Exception as e:
            task = self.db.get_task(task.id)
            if task is None:
                return
            if task.status != TaskStatus.CANCELLED:
                task.status = TaskStatus.FAILED
                task.finished_at = now()
                task.error = str(e)[:2000]
                task.progress = "failed"
                self.db.update_task(task)
                self.db.audit(task.id, "failed", str(e)[:500])
                logger.error("Task %s failed: %s", task.id, str(e)[:500])

    def _is_cancel_requested(self, task_id: str) -> bool:
        t = self.db.get_task(task_id)
        return bool(t and t.cancel_requested)

    def _build_prompt(self, task: TaskRecord) -> str:
        return (
            "You are operating in the F&O DEV repository only. "
            "Do not access PROD, credentials, .env secrets, or launch trading sessions. "
            "Preserve existing dirty/untracked files. Do not commit or push. "
            "Complete the following task and produce a report under reports/execution/ when applicable.\n\n"
            f"TASK:\n{task.task_text}\n"
        )

    def _git_status(self, workspace: str) -> str:
        try:
            out = subprocess.run(["git", "status", "--porcelain"], cwd=workspace, capture_output=True, text=True, timeout=10)
            return out.stdout.strip()
        except Exception as e:
            return f"git status unavailable: {e}"

    def _git_diff_stat(self, workspace: str) -> str:
        try:
            out = subprocess.run(["git", "diff", "--stat"], cwd=workspace, capture_output=True, text=True, timeout=10)
            return out.stdout.strip()
        except Exception as e:
            return f"git diff stat unavailable: {e}"

    def process_next(self) -> bool:
        task = self._next_queued()
        if task is None:
            return False
        self._execute_task(task)
        return True

    def run_task_sync(self, task_id: str):
        task = self.db.get_task(task_id)
        if task and task.status == TaskStatus.QUEUED:
            self._execute_task(task)