"""WP-423: OpenCode execution boundary.

The orchestrator talks to an :class:`ExecutionInterface`, never to HTTP. Two
implementations exist:

* :class:`TaskControllerExecutor` — reuses the existing ``TaskController`` +
  ``OpenCodeAdapter`` (the authenticated local OpenCode API integration). No new
  client, no provider/model change.
* :class:`FakeOpenCodeExecutor` — deterministic scenario double covering quota
  exhaustion, 429 + ``Retry-After``, auth failure, disconnection, context
  exhaustion, interruption and success.

Every method returns a structured dict and never raises for *provider* problems,
so the orchestrator can persist a state transition instead of losing context.
"""

import random
import time
from typing import Any, Dict, List, Optional

from .config import opencode_model_provider, opencode_model_id

# Stable, machine-readable reasons.
OPENCODE_OK = "ok"
OPENCODE_QUOTA_EXHAUSTED = "opencode_quota_exhausted"
OPENCODE_RATE_LIMITED = "opencode_rate_limited"
OPENCODE_AUTH_REQUIRED = "opencode_authentication_required"
OPENCODE_UNAVAILABLE = "opencode_provider_unavailable"
OPENCODE_DISCONNECTED = "opencode_disconnected"
OPENCODE_CONTEXT_EXHAUSTED = "opencode_context_exhausted"
OPENCODE_INTERRUPTED = "opencode_execution_interrupted"
OPENCODE_UNCERTAIN = "opencode_submission_uncertain"
OPENCODE_TIMEOUT = "opencode_timeout"

RETRYABLE_REASONS = {
    OPENCODE_RATE_LIMITED,
    OPENCODE_DISCONNECTED,
    OPENCODE_UNCERTAIN,
    OPENCODE_TIMEOUT,
    OPENCODE_UNAVAILABLE,
}


class ExecutionInterface:
    """Operations the orchestrator needs from an OpenCode executor."""

    provider = "opencode"

    def health(self) -> Dict[str, Any]:  # pragma: no cover - interface
        raise NotImplementedError

    def submit(self, task: Dict[str, Any], prompt: str) -> Dict[str, Any]:  # pragma: no cover
        raise NotImplementedError

    def poll(self, execution: Dict[str, Any], timeout_seconds: float = 0.0) -> Dict[str, Any]:  # pragma: no cover
        raise NotImplementedError

    def reconcile(self, execution: Dict[str, Any]) -> Dict[str, Any]:  # pragma: no cover
        raise NotImplementedError

    def abort(self, execution: Dict[str, Any]) -> bool:  # pragma: no cover
        return False


class FakeOpenCodeExecutor(ExecutionInterface):
    """Deterministic executor double.

    ``fail_submit`` fails the submission attempt (before any session exists).
    ``fail_poll`` fails result retrieval after a session exists — the case that
    must reconcile instead of resubmitting.
    """

    provider = "opencode"

    def __init__(
        self,
        *,
        response_text: str = "MOCK_OPENCODE_OK",
        changed_files: Optional[List[str]] = None,
        test_results: Optional[Dict[str, Any]] = None,
        fail_submit: Optional[str] = None,
        fail_poll: Optional[str] = None,
        submit_partial: bool = False,
        retry_after: Optional[float] = None,
        report_path: str = "reports/execution/mock_report.md",
        poll_steps: int = 1,
    ):
        self.response_text = response_text
        self.changed_files = list(changed_files or [])
        self.test_results = dict(test_results or {"passed": 1, "failed": 0})
        self.fail_submit = fail_submit
        self.fail_poll = fail_poll
        self.submit_partial = submit_partial
        self.retry_after = retry_after
        self.report_path = report_path
        self.poll_steps = max(1, int(poll_steps))
        self.sessions: Dict[str, Dict[str, Any]] = {}
        self.submit_calls = 0
        self.poll_calls = 0
        self.aborted: List[str] = []
        self._clock = time.time
        self._sessions_created = 0

    def health(self) -> Dict[str, Any]:
        if self.fail_submit == OPENCODE_DISCONNECTED:
            return {"ok": False, "reason": OPENCODE_DISCONNECTED}
        if self.fail_submit == OPENCODE_AUTH_REQUIRED:
            return {"ok": False, "reason": OPENCODE_AUTH_REQUIRED}
        return {"ok": True, "reason": OPENCODE_OK, "version": "fake"}

    def submit(self, task: Dict[str, Any], prompt: str) -> Dict[str, Any]:
        self.submit_calls += 1
        if self.fail_submit:
            return {
                "ok": False,
                "reason": self.fail_submit,
                "retryable": self.fail_submit in RETRYABLE_REASONS,
                "retry_after": self.retry_after,
            }
        self._sessions_created += 1
        session_id = f"fake-session-{self._sessions_created}"
        self.sessions[session_id] = {
            "task_id": task["task_id"],
            "prompt": prompt,
            "polls": 0,
            "created_at": self._clock(),
        }
        if self.submit_partial:
            # Session exists but the prompt may or may not have landed: the
            # classic uncertain submission that must be reconciled, not retried.
            return {
                "ok": False,
                "reason": OPENCODE_UNCERTAIN,
                "retryable": False,
                "opencode_session_id": session_id,
                "error": "prompt send failed after session creation",
            }
        return {"ok": True, "reason": OPENCODE_OK, "opencode_session_id": session_id, "execution_status": "submitted"}

    def poll(self, execution: Dict[str, Any], timeout_seconds: float = 0.0) -> Dict[str, Any]:
        self.poll_calls += 1
        session_id = execution.get("opencode_session_id") or ""
        session = self.sessions.get(session_id)
        if session is None:
            return {"ok": False, "reason": OPENCODE_UNCERTAIN, "retryable": False, "execution_status": "uncertain"}
        session["polls"] += 1
        if self.fail_poll:
            return {
                "ok": False,
                "reason": self.fail_poll,
                "retryable": self.fail_poll in RETRYABLE_REASONS,
                "execution_status": "interrupted",
            }
        if session["polls"] < self.poll_steps:
            return {"ok": True, "reason": OPENCODE_OK, "execution_status": "running", "finished": False}
        return {
            "ok": True,
            "reason": OPENCODE_OK,
            "execution_status": "completed",
            "finished": True,
            "execution_output": self.response_text,
            "changed_files": list(self.changed_files),
            "test_results": dict(self.test_results),
            "verification_evidence": {"report_path": self.report_path, "source": "fake_executor"},
        }

    def reconcile(self, execution: Dict[str, Any]) -> Dict[str, Any]:
        session_id = execution.get("opencode_session_id") or ""
        if session_id and session_id in self.sessions:
            return {"ok": True, "found": True, "opencode_session_id": session_id}
        return {"ok": True, "found": False, "opencode_session_id": session_id or None}

    def abort(self, execution: Dict[str, Any]) -> bool:
        session_id = execution.get("opencode_session_id") or ""
        if session_id:
            self.aborted.append(session_id)
        return True


class TaskControllerExecutor(ExecutionInterface):
    """Reuses the existing ``TaskController`` + authenticated OpenCode adapter.

    The controller creates the OpenCode session, sends the prompt and polls for
    the final assistant message; this class only adapts its vocabulary to the
    WP-423 execution contract. No provider or model configuration is touched.
    """

    provider = "opencode"

    def __init__(self, task_controller, workspace: str):
        self.task_controller = task_controller
        self.workspace = workspace

    def health(self) -> Dict[str, Any]:
        try:
            self.task_controller.adapter.health()
            return {"ok": True, "reason": OPENCODE_OK}
        except Exception as exc:
            message = str(exc)
            lowered = message.lower()
            if "401" in lowered or "403" in lowered or "auth" in lowered:
                reason = OPENCODE_AUTH_REQUIRED
            elif "429" in lowered or "quota" in lowered or "limit" in lowered:
                reason = OPENCODE_QUOTA_EXHAUSTED
            elif "connection" in lowered or "refused" in lowered:
                reason = OPENCODE_DISCONNECTED
            else:
                reason = OPENCODE_UNAVAILABLE
            return {"ok": False, "reason": reason, "error": message[:500]}

    def submit(self, task: Dict[str, Any], prompt: str) -> Dict[str, Any]:
        adapter = self.task_controller.adapter
        try:
            session = adapter.create_session(title=f"wp423-{task['task_id'][:8]}", directory=self.workspace)
        except Exception as exc:
            return {
                "ok": False,
                "reason": _classify_exception(exc),
                "retryable": False,
                "error": str(exc)[:500],
            }
        session_id = session.get("id") if isinstance(session, dict) else None
        if not session_id:
            return {"ok": False, "reason": OPENCODE_UNCERTAIN, "retryable": False, "error": "no session id returned"}
        try:
            provider = opencode_model_provider()
            model_id = opencode_model_id()
            model = {"providerID": provider, "modelID": model_id} if provider and model_id else None
            adapter.send_prompt_async(session_id, prompt, model=model, directory=self.workspace)
        except Exception as exc:
            # Session exists but the prompt may or may not have landed.
            return {
                "ok": False,
                "reason": OPENCODE_UNCERTAIN,
                "retryable": False,
                "opencode_session_id": session_id,
                "error": str(exc)[:500],
            }
        return {
            "ok": True,
            "reason": OPENCODE_OK,
            "opencode_session_id": session_id,
            "execution_status": "submitted",
        }

    def poll(self, execution: Dict[str, Any], timeout_seconds: float = 0.0) -> Dict[str, Any]:
        session_id = execution.get("opencode_session_id") or ""
        if not session_id:
            return {"ok": False, "reason": OPENCODE_UNCERTAIN, "execution_status": "uncertain"}
        adapter = self.task_controller.adapter
        deadline = time.time() + max(0.0, timeout_seconds)
        while True:
            try:
                messages = adapter.get_messages(session_id, limit=50, directory=self.workspace)
            except Exception as exc:
                return {
                    "ok": False,
                    "reason": _classify_exception(exc),
                    "retryable": True,
                    "execution_status": "interrupted",
                    "error": str(exc)[:500],
                }
            text = adapter.extract_final_assistant(messages)
            if text:
                return {
                    "ok": True,
                    "reason": OPENCODE_OK,
                    "execution_status": "completed",
                    "finished": True,
                    "execution_output": text,
                    "changed_files": self._git_changed_files(),
                    "test_results": {},
                    "verification_evidence": {"source": "task_controller", "git_status": self._git_status()},
                }
            if time.time() >= deadline:
                return {"ok": True, "reason": OPENCODE_OK, "execution_status": "running", "finished": False}
            time.sleep(1.0)

    def reconcile(self, execution: Dict[str, Any]) -> Dict[str, Any]:
        """Only a *persisted* session id may be resumed; never invent or resubmit."""
        session_id = execution.get("opencode_session_id") or ""
        if not session_id:
            return {"ok": True, "found": False, "opencode_session_id": None}
        try:
            messages = self.task_controller.adapter.get_messages(session_id, limit=10, directory=self.workspace)
        except Exception as exc:
            return {
                "ok": False,
                "found": False,
                "reason": _classify_exception(exc),
                "error": str(exc)[:300],
            }
        return {"ok": True, "found": bool(messages) or True, "opencode_session_id": session_id}

    def abort(self, execution: Dict[str, Any]) -> bool:
        session_id = execution.get("opencode_session_id") or ""
        if not session_id:
            return False
        try:
            return bool(self.task_controller.adapter.abort(session_id, directory=self.workspace))
        except Exception:
            return False

    # read-only evidence helpers (no repository mutation)

    def _git_status(self) -> str:
        import subprocess

        try:
            out = subprocess.run(
                ["git", "status", "--porcelain"], cwd=self.workspace, capture_output=True, text=True, timeout=10
            )
            return out.stdout.strip()
        except Exception as exc:
            return f"git status unavailable: {exc}"

    def _git_changed_files(self) -> List[str]:
        import subprocess

        try:
            out = subprocess.run(
                ["git", "status", "--porcelain"], cwd=self.workspace, capture_output=True, text=True, timeout=10
            )
        except Exception:
            return []
        files: List[str] = []
        for line in out.stdout.splitlines():
            path = line[3:].strip() if len(line) > 3 else ""
            if path:
                files.append(path)
        return files


def _classify_exception(exc: Exception) -> str:
    message = str(exc).lower()
    if "401" in message or "403" in message or "auth" in message:
        return OPENCODE_AUTH_REQUIRED
    if "429" in message or "quota" in message or "rate limit" in message:
        return OPENCODE_RATE_LIMITED
    if "context" in message or "too large" in message or "token limit" in message:
        return OPENCODE_CONTEXT_EXHAUSTED
    if "connection" in message or "refused" in message or "unreachable" in message:
        return OPENCODE_DISCONNECTED
    if "timeout" in message or "timed out" in message:
        return OPENCODE_TIMEOUT
    return OPENCODE_UNAVAILABLE


def jittered_backoff(policy, attempt: int, retry_after: Optional[float] = None, seed: int = 0) -> float:
    return policy.delay_for(attempt, retry_after=retry_after, rng=random.Random(seed))
