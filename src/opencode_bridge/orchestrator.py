"""WP-423: mission orchestrator — state owner and execution authority.

This module is the only component allowed to advance a mission's state. It owns:

* idempotent ingestion of ChatGPT messages,
* task validation + governance (never treats ChatGPT text as authorisation),
* the approval gate,
* OpenCode submission with identity persisted *before* the call,
* result persistence *before* any ChatGPT delivery,
* delivery with a persisted attempt budget and reconciliation of uncertainty,
* restart recovery that reconciles instead of resubmitting,
* the operator-facing status report.

It never launches a browser, never touches credentials and never commits.
"""

import json
import logging
import os
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from . import contracts
from .config import DEV_WORKSPACE, EXPECTED_BRANCH
from .db import BridgeDB
from .executors import (
    OPENCODE_AUTH_REQUIRED,
    OPENCODE_CONTEXT_EXHAUSTED,
    OPENCODE_DISCONNECTED,
    OPENCODE_INTERRUPTED,
    OPENCODE_OK,
    OPENCODE_QUOTA_EXHAUSTED,
    OPENCODE_RATE_LIMITED,
    OPENCODE_UNAVAILABLE,
    OPENCODE_UNCERTAIN,
)
from .policy import TaskPolicy, classify_task
from .retry import CooldownGate, RetryPolicy
from .state_machine import (
    InvalidTransition,
    OrchState,
    REQUIRED_ACTION,
    assert_transition,
    can_transition,
    is_terminal,
    recovery_target,
)

logger = logging.getLogger("opencode_bridge.orchestrator")

MAX_CYCLES_HARD_LIMIT = 50

#: Repository/operation governance keywords. Deliberately stricter than
#: ``policy.BLOCKED_KEYWORDS``: these are refused outright, never auto-approved.
DESTRUCTIVE_PATTERNS = (
    "rm -rf",
    "del /f",
    "rmdir /s",
    "format ",
    "drop table",
    "truncate table",
    "git reset --hard",
    "git clean -fd",
    "git push --force",
    "force push",
    "delete branch",
    "--no-verify",
    "bypass auth",
    "disable auth",
    "disable safety",
    "skip safety",
    "no-sandbox",
)

CREDENTIAL_PATTERNS = (
    ".env",
    "api key",
    "apikey",
    "secret",
    "token",
    "credential",
    "password",
    "cookie",
    "oauth",
)

PRODUCTION_PATTERNS = (
    "production",
    "prod deploy",
    "deploy to prod",
    "live trading",
    "live order",
    "launch session",
    "session launch",
)

COMMIT_PUSH_PATTERNS = ("commit", "push", "merge", "rebase", "release", "tag ")


class OrchestrationError(Exception):
    """Programming/contract error (not a provider failure)."""


@dataclass
class GovernanceDecision:
    decision: str  # "auto" | "requires_approval" | "blocked"
    risk: str
    reasons: List[str]
    approval_requirements: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "decision": self.decision,
            "risk": self.risk,
            "reasons": list(self.reasons),
            "approval_requirements": list(self.approval_requirements),
        }


class MissionOrchestrator:
    provider_chatgpt = "chatgpt"
    provider_opencode = "opencode"

    def __init__(
        self,
        db: BridgeDB,
        chatgpt,
        executor,
        *,
        mission_id: str,
        mission_title: str = "ChatGPT-controlled development mission",
        workspace: Optional[str] = None,
        target_branch: str = EXPECTED_BRANCH,
        allowed_repositories: Optional[List[str]] = None,
        project_url: Optional[str] = None,
        conversation_id: Optional[str] = None,
        retry_policy: Optional[RetryPolicy] = None,
        delivery_retry_policy: Optional[RetryPolicy] = None,
        clock=None,
        task_timeout_seconds: float = 300.0,
    ):
        self.db = db
        self.chatgpt = chatgpt
        self.executor = executor
        self.mission_id = mission_id
        self.mission_title = mission_title
        self.workspace = str(Path(workspace or str(DEV_WORKSPACE)).resolve())
        self.target_branch = target_branch
        self.allowed_repositories = [
            str(Path(p).resolve()) for p in (allowed_repositories or [self.workspace])
        ]
        self.project_url = project_url or getattr(chatgpt, "project_url", None)
        self.conversation_id = conversation_id
        self.retry_policy = retry_policy or RetryPolicy(max_attempts=3, base_seconds=0.5, factor=2.0, cap_seconds=30.0)
        self.delivery_retry_policy = delivery_retry_policy or RetryPolicy(
            max_attempts=3, base_seconds=1.0, factor=2.0, cap_seconds=60.0
        )
        self._clock = clock or time.time
        self.task_timeout_seconds = task_timeout_seconds
        self.cooldowns = CooldownGate(clock=self._clock)
        self.last_recovery: Dict[str, Any] = {}
        self._ensure_mission()

    # ------------------------------------------------------------------
    # state
    # ------------------------------------------------------------------

    def _ensure_mission(self) -> None:
        existing = self.db.get_mission(self.mission_id)
        if existing is None:
            self.db.upsert_mission(
                self.mission_id,
                self.mission_title,
                self.workspace,
                self.target_branch,
                OrchState.READY.value,
            )
            self.db.audit_orch("mission_created", self.mission_id, self.workspace)

    def state(self) -> OrchState:
        mission = self.db.get_mission(self.mission_id) or {}
        try:
            return OrchState(mission.get("state", OrchState.READY.value))
        except ValueError:
            return OrchState.HUMAN_REVIEW_REQUIRED

    def is_paused(self) -> bool:
        mission = self.db.get_mission(self.mission_id) or {}
        return bool(mission.get("paused"))

    def _set_state(self, target: OrchState, reason: str = "", error: Optional[str] = None) -> OrchState:
        source = self.state()
        if source == OrchState(target):
            return source
        if not can_transition(source, target):
            raise InvalidTransition(source, target)
        assert_transition(source, target)
        self.db.set_mission_state(
            self.mission_id,
            OrchState(target).value,
            required_action=REQUIRED_ACTION.get(OrchState(target)),
            last_error=error,
        )
        self.db.audit_orch(
            "state_transition",
            self.mission_id,
            f"{OrchState(source).value}->{OrchState(target).value} {reason}".strip(),
        )
        logger.info("mission %s %s -> %s (%s)", self.mission_id, source.value, target.value, reason)
        return OrchState(target)

    def _try_state(self, target: OrchState, reason: str = "", error: Optional[str] = None) -> bool:
        try:
            self._set_state(target, reason, error)
            return True
        except InvalidTransition:
            logger.warning("ignored invalid transition %s -> %s", self.state().value, target.value)
            return False

    # ------------------------------------------------------------------
    # governance
    # ------------------------------------------------------------------

    def evaluate_governance(self, task: Dict[str, Any], message: Optional[Dict[str, Any]]) -> GovernanceDecision:
        """Independent policy gate. ChatGPT text is evidence, never authorisation."""
        reasons: List[str] = []
        requirements: List[str] = []
        blocked = False
        risk = "low"

        # 1. repository identity (exact allowlist match, resolved)
        repo = str(Path(task["target_repository"]).resolve()) if task.get("target_repository") else ""
        if repo not in self.allowed_repositories:
            blocked = True
            reasons.append(f"repository_not_allowed: {repo or '(empty)'}")

        # 2. branch identity
        if task.get("target_branch") != self.target_branch:
            blocked = True
            reasons.append(
                f"branch_not_allowed: {task.get('target_branch')!r} (expected {self.target_branch!r})"
            )

        # 3. provenance: the originating message must be a persisted inbound message
        if message is None:
            blocked = True
            reasons.append("provenance_unknown: originating message not found")
        else:
            if message.get("message_id") != task.get("originating_message_id"):
                blocked = True
                reasons.append("provenance_mismatch: message id does not match")
            if message.get("project_id") and message.get("project_id") != getattr(
                self.chatgpt, "project_id", message.get("project_id")
            ):
                blocked = True
                reasons.append("project_identity_mismatch")

        text = (task.get("task_description") or "").lower()

        # 4. destructive operations -> blocked outright
        for pattern in DESTRUCTIVE_PATTERNS:
            if pattern in text:
                blocked = True
                reasons.append(f"destructive_operation: {pattern}")
                risk = "critical"

        # 5. credentials / env files -> blocked (never read or written)
        for pattern in CREDENTIAL_PATTERNS:
            if pattern in text:
                blocked = True
                reasons.append(f"credential_or_secret_access: {pattern}")
                risk = "critical"

        # 6. production/deployment restrictions
        for pattern in PRODUCTION_PATTERNS:
            if pattern in text:
                blocked = True
                reasons.append(f"production_restriction: {pattern}")
                risk = "critical"

        # 7. commit/push is never automatic, always human
        for pattern in COMMIT_PUSH_PATTERNS:
            if pattern in text:
                requirements.append(f"human_approval:{pattern.strip()}")
                risk = _raise_risk(risk, "high")

        if reason_list := self._safety_task_text_reasons(task.get("task_description") or ""):
            blocked = True
            reasons.extend(reason_list)
            risk = "critical"

        # 8. reuse the existing keyword policy for the residual classification
        policy, policy_reason = classify_task(task.get("task_description") or "")
        if policy is TaskPolicy.BLOCKED:
            blocked = True
            reasons.append(f"policy_blocked: {policy_reason}")
        elif policy is TaskPolicy.REQUIRES_APPROVAL:
            requirements.append(f"human_approval:{policy_reason}")
            risk = _raise_risk(risk, "medium")

        if risk == "low" and task.get("risk_classification") in ("medium", "high", "critical"):
            risk = task["risk_classification"]

        if blocked:
            decision = "blocked"
        elif requirements:
            decision = "requires_approval"
        else:
            decision = "auto"

        return GovernanceDecision(decision=decision, risk=risk, reasons=reasons or ["ok"], approval_requirements=requirements)

    @staticmethod
    def _safety_task_text_reasons(text: str) -> List[str]:
        """Reuse existing PROD-path guards without requiring a git checkout."""
        from .config import SENSITIVE_KEYWORDS

        reasons: List[str] = []
        low = (text or "").lower()
        if "fno-ai-paper-trading" in low and "fno-ai-paper-trading-dev" not in low:
            reasons.append("production_repository_referenced")
        for keyword in SENSITIVE_KEYWORDS:
            if keyword in low:
                reasons.append(f"sensitive_action: {keyword}")
                break
        return reasons

    # ------------------------------------------------------------------
    # ingestion + task creation
    # ------------------------------------------------------------------

    def ingest_message(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        ok, errors = contracts.validate_inbound_message(payload)
        if not ok:
            self.db.audit_orch("inbound_rejected", "", "; ".join(errors)[:500])
            return {"ok": False, "reason": "schema_invalid", "errors": errors}

        content_hash = _hash(payload["message_content"])
        inserted, row = self.db.ingest_inbound_message(payload, content_hash)
        self.db.audit_orch(
            "inbound_persisted" if inserted else "inbound_duplicate",
            payload["message_id"],
            payload["correlation_id"],
        )
        return {
            "ok": True,
            "inserted": inserted,
            "duplicate": not inserted,
            "message_id": payload["message_id"],
            "duplicate_count": int(row.get("duplicate_count", 0)) if row else 0,
            "content_hash": content_hash,
        }

    def _mission_identity(self) -> Tuple[str, str]:
        """Resolve the Project/conversation identity the mission is bound to.

        The conversation id falls back to the transport's verified conversation
        so identity validation is never silently skipped when only the adapter
        knows the id.
        """
        project_id = getattr(self.chatgpt, "project_id", None) or ""
        conversation_id = self.conversation_id or getattr(self.chatgpt, "conversation_id", None) or ""
        return project_id, conversation_id

    def create_task(self, message: Dict[str, Any]) -> Dict[str, Any]:
        project_id, conversation_id = self._mission_identity()

        # Reject a message from a different Project or conversation outright.
        if message.get("project_id") and project_id and message["project_id"] != project_id:
            return {"ok": False, "reason": "project_identity_mismatch"}
        if conversation_id and message.get("conversation_id") and message["conversation_id"] != conversation_id:
            return {"ok": False, "reason": "conversation_identity_mismatch"}

        existing = self.db.get_dev_task_for_message(self.mission_id, message["message_id"])
        if existing:
            return {"ok": True, "duplicate": True, "task": existing, "task_id": existing["task_id"]}

        task_text = message["message_content"]
        task_id = f"task-{uuid.uuid4().hex[:16]}"
        task = contracts.dev_task(
            task_id=task_id,
            mission_id=self.mission_id,
            originating_message_id=message["message_id"],
            task_title=_title_from(task_text),
            task_description=task_text,
            target_repository=self.workspace,
            target_branch=self.target_branch,
            risk_classification="low",
            task_status="draft",
        )
        valid, errors = contracts.validate_dev_task(task)
        if not valid:
            return {"ok": False, "reason": "task_contract_invalid", "errors": errors}

        decision = self.evaluate_governance(task, message)
        task["risk_classification"] = decision.risk
        task["approval_requirements"] = decision.approval_requirements
        task["task_status"] = "blocked" if decision.decision == "blocked" else "validated"

        inserted = self.db.insert_dev_task(task)
        if not inserted:
            existing = self.db.get_dev_task_for_message(self.mission_id, message["message_id"])
            return {"ok": True, "duplicate": True, "task": existing, "task_id": existing["task_id"]}

        self.db.audit_orch(
            "task_created",
            task_id,
            json.dumps({"decision": decision.decision, "risk": decision.risk, "reasons": decision.reasons})[:500],
        )

        if decision.decision == "blocked":
            self._try_state(OrchState.HUMAN_REVIEW_REQUIRED, "task blocked by governance", "; ".join(decision.reasons))
            return {
                "ok": False,
                "reason": "governance_blocked",
                "task_id": task_id,
                "governance": decision.to_dict(),
            }

        self._try_state(OrchState.TASK_VALIDATION, "governance evaluated")
        self._try_state(OrchState.TASK_READY, "task validated")

        if decision.decision == "requires_approval":
            self.db.create_approval_request(
                f"apr-{uuid.uuid4().hex[:16]}", task_id, decision.risk, decision.approval_requirements
            )
            self.db.set_dev_task_status(task_id, "awaiting_approval")
            self._try_state(OrchState.WAITING_FOR_APPROVAL, "approval required")
            return {
                "ok": True,
                "task_id": task_id,
                "requires_approval": True,
                "governance": decision.to_dict(),
            }

        self.db.set_dev_task_status(task_id, "ready")
        return {"ok": True, "task_id": task_id, "requires_approval": False, "governance": decision.to_dict()}

    # ------------------------------------------------------------------
    # execution
    # ------------------------------------------------------------------

    def approve_task(self, task_id: str, approved_by: str = "operator", reason: str = "") -> Dict[str, Any]:
        task = self.db.get_dev_task(task_id)
        if not task:
            return {"ok": False, "reason": "task_not_found"}
        if task["task_status"] not in ("awaiting_approval", "validated"):
            return {"ok": False, "reason": f"task_not_approvable ({task['task_status']})"}
        request = self.db.get_pending_approval_for_task(task_id)
        if request and not self.db.decide_approval(request["id"], "approved", approved_by, reason):
            return {"ok": False, "reason": "approval_already_decided"}
        self.db.set_dev_task_status(task_id, "ready")
        self.db.audit_orch("task_approved", task_id, approved_by)
        self._try_state(OrchState.OPENCODE_SUBMISSION, f"approved by {approved_by}")
        return {"ok": True, "task_id": task_id, "status": "ready"}

    def reject_task(self, task_id: str, reason: str = "", rejected_by: str = "operator") -> Dict[str, Any]:
        task = self.db.get_dev_task(task_id)
        if not task:
            return {"ok": False, "reason": "task_not_found"}
        request = self.db.get_pending_approval_for_task(task_id)
        if request:
            self.db.decide_approval(request["id"], "rejected", rejected_by, reason)
        self.db.set_dev_task_status(task_id, "blocked")
        self.db.audit_orch("task_rejected", task_id, reason)
        self._try_state(OrchState.HUMAN_REVIEW_REQUIRED, "task rejected")
        return {"ok": True, "task_id": task_id, "status": "blocked", "reason": reason}

    def _gate_provider(self, provider: str) -> Optional[Dict[str, Any]]:
        state = self.db.get_provider_state(provider)
        if state and not self.cooldowns.is_open(state.get("cooldown_until")):
            return {
                "cooldown": True,
                "cooldown_until": state.get("cooldown_until"),
                "remaining": self.cooldowns.remaining(state.get("cooldown_until")),
                "last_error": state.get("last_error"),
            }
        return None

    def submit_and_execute(self, task_id: str) -> Dict[str, Any]:
        task = self.db.get_dev_task(task_id)
        if not task:
            return {"ok": False, "reason": "task_not_found"}
        if task["task_status"] not in ("ready",):
            return {"ok": False, "reason": f"task_not_ready ({task['task_status']})"}

        message = self.db.get_inbound_message(task["originating_message_id"])
        decision = self.evaluate_governance(task, message)
        if decision.decision == "blocked":
            self.db.set_dev_task_status(task_id, "blocked")
            self._try_state(OrchState.HUMAN_REVIEW_REQUIRED, "blocked at submission re-validation")
            return {"ok": False, "reason": "governance_blocked", "governance": decision.to_dict()}

        gate = self._gate_provider(self.provider_opencode)
        if gate:
            self._try_state(OrchState.QUOTA_EXHAUSTED, "provider cooling down")
            return {"ok": False, "reason": "provider_cooldown", **gate}

        # Idempotency: an execution row is created once per task (UNIQUE task_id)
        # and is persisted *before* the call, so a crash can never double-submit.
        execution_id = f"exec-{uuid.uuid4().hex[:16]}"
        intent = contracts.execution(execution_id=execution_id, task_id=task_id, submitted_at=self._clock())
        created = self.db.insert_execution(intent)
        if not created:
            existing = self.db.get_execution_for_task(task_id)
            return {"ok": True, "duplicate": True, "execution": existing}

        self._try_state(OrchState.OPENCODE_SUBMISSION, "execution intent persisted")

        healthy = self.executor.health()
        if not healthy.get("ok"):
            return self._handle_opencode_failure(task_id, intent, healthy, phase="health")

        prompt = self._build_prompt(task)
        self.db.set_dev_task_status(task_id, "running")
        result = self.executor.submit(task, prompt)

        if not result.get("ok"):
            return self._handle_opencode_failure(task_id, intent, result, phase="submit")

        self.db.update_execution(
            execution_id,
            opencode_session_id=result.get("opencode_session_id"),
            execution_status="submitted",
            started_at=self._clock(),
            verification_evidence={"submitted_at": self._clock(), "workspace": self.workspace},
        )
        self.db.audit_orch("execution_submitted", task_id, result.get("opencode_session_id") or "")
        self._try_state(OrchState.OPENCODE_EXECUTION, "session created")

        return self._collect_result(task_id, execution_id)

    def _handle_opencode_failure(
        self, task_id: str, execution: Dict[str, Any], failure: Dict[str, Any], phase: str
    ) -> Dict[str, Any]:
        reason = failure.get("reason", OPENCODE_UNAVAILABLE)
        error = failure.get("error", "")
        execution_id = execution.get("execution_id")
        if execution_id:
            # A health/submit failure with no session is *failed* (nothing was
            # created). Once a session id exists the outcome is *uncertain*: the
            # prompt may or may not have landed, so it must be reconciled rather
            # than resubmitted.
            session_id = failure.get("opencode_session_id")
            if session_id:
                status = "uncertain"
            elif phase == "submit" and reason == OPENCODE_UNCERTAIN:
                status = "uncertain"
            else:
                status = "failed"
            fields: Dict[str, Any] = {
                "execution_status": status,
                "error": f"{phase}:{reason}:{error}"[:2000],
            }
            if session_id:
                # Persist the identity before anything else so a restart can
                # resume/reconcile this exact session.
                fields["opencode_session_id"] = session_id
            self.db.update_execution(execution_id, **fields)
        self.db.audit_orch("execution_failure", task_id, f"{phase}:{reason}")

        if reason in (OPENCODE_AUTH_REQUIRED,):
            self._try_state(OrchState.AUTHENTICATION_REQUIRED, "opencode auth", error[:500])
            return {"ok": False, "reason": reason, "requires_operator": True}

        if reason in (OPENCODE_QUOTA_EXHAUSTED, OPENCODE_RATE_LIMITED):
            retry_after = failure.get("retry_after")
            delay = self.retry_policy.delay_for(1, retry_after=retry_after)
            self.db.set_provider_state(
                self.provider_opencode,
                available=False,
                cooldown_until=self.cooldowns.until(delay),
                consecutive_failures=1,
                last_error=reason,
            )
            self._try_state(OrchState.QUOTA_EXHAUSTED, f"quota/rate limit ({reason})", error[:500])
            return {"ok": False, "reason": reason, "cooldown_seconds": delay}

        if reason in (OPENCODE_CONTEXT_EXHAUSTED,):
            self.db.save_checkpoint(
                "context_exhausted",
                {"task_id": task_id, "execution_id": execution_id, "reason": reason},
                mission_id=self.mission_id,
                task_id=task_id,
                execution_id=execution_id,
            )
            self._try_state(OrchState.HUMAN_REVIEW_REQUIRED, "opencode context exhausted", error[:500])
            return {"ok": False, "reason": reason, "checkpoint": True, "requires_operator": True}

        if reason == OPENCODE_UNCERTAIN:
            # Session may exist: reconcile, never resubmit.
            self._try_state(OrchState.RECONCILIATION_REQUIRED, "uncertain submission", error[:500])
            return {"ok": False, "reason": reason, "reconcile": True}

        self._try_state(OrchState.RECONCILIATION_REQUIRED, f"opencode failure ({reason})", error[:500])
        return {"ok": False, "reason": reason}

    def _collect_result(self, task_id: str, execution_id: str) -> Dict[str, Any]:
        execution = self.db.get_execution(execution_id)
        if not execution:
            return {"ok": False, "reason": "execution_missing"}
        try:
            polled = self.executor.poll(execution, timeout_seconds=self.task_timeout_seconds)
        except Exception as exc:  # defensive: never lose the execution row
            polled = {"ok": False, "reason": OPENCODE_INTERRUPTED, "error": f"{type(exc).__name__}: {exc}"}

        if polled.get("ok") and polled.get("finished"):
            self._persist_result(task_id, execution_id, polled)
            self.db.set_dev_task_status(task_id, "completed")
            self._try_state(OrchState.RESULT_PERSISTED, "execution result persisted")
            return {"ok": True, "task_id": task_id, "execution": self.db.get_execution(execution_id)}

        if polled.get("ok") and not polled.get("finished"):
            self.db.update_execution(execution_id, execution_status="running")
            self._try_state(OrchState.WAITING_FOR_OPENCODE, "execution still running")
            return {"ok": True, "task_id": task_id, "waiting": True, "execution": self.db.get_execution(execution_id)}

        reason = polled.get("reason", OPENCODE_INTERRUPTED)
        if reason in (OPENCODE_AUTH_REQUIRED,):
            self._try_state(OrchState.AUTHENTICATION_REQUIRED, "opencode auth during poll")
            return {"ok": False, "reason": reason, "requires_operator": True}
        if reason in (OPENCODE_QUOTA_EXHAUSTED, OPENCODE_RATE_LIMITED):
            delay = self.retry_policy.delay_for(1, retry_after=polled.get("retry_after"))
            self.db.set_provider_state(
                self.provider_opencode,
                available=False,
                cooldown_until=self.cooldowns.until(delay),
                consecutive_failures=1,
                last_error=reason,
            )
            self._try_state(OrchState.QUOTA_EXHAUSTED, "quota during poll")
            return {"ok": False, "reason": reason, "cooldown_seconds": delay}

        self.db.update_execution(
            execution_id, execution_status="interrupted", error=str(polled.get("error", reason))[:2000]
        )
        self.db.save_checkpoint(
            "execution_interrupted",
            {"task_id": task_id, "execution_id": execution_id, "reason": reason},
            mission_id=self.mission_id,
            task_id=task_id,
            execution_id=execution_id,
        )
        self._try_state(OrchState.EXECUTION_INTERRUPTED, "result retrieval failed", str(reason)[:500])
        self._try_state(OrchState.RECONCILIATION_REQUIRED, "must reconcile before retry")
        return {"ok": False, "reason": reason, "reconcile": True}

    def _persist_result(self, task_id: str, execution_id: str, polled: Dict[str, Any]) -> None:
        self.db.update_execution(
            execution_id,
            execution_status="completed",
            completion_status=polled.get("completion_status", "completed"),
            execution_output=polled.get("execution_output") or "",
            changed_files=polled.get("changed_files") or [],
            test_results=polled.get("test_results") or {},
            verification_evidence={**{"workspace": self.workspace}, **(polled.get("verification_evidence") or {})},
            completed_at=self._clock(),
        )
        self.db.audit_orch("result_persisted", task_id, execution_id)

    # ------------------------------------------------------------------
    # delivery
    # ------------------------------------------------------------------

    def build_delivery_content(self, task: Dict[str, Any], execution: Dict[str, Any]) -> str:
        tests = execution.get("test_results") or {}
        files = execution.get("changed_files") or []
        lines = [
            f"WP-423 controller result for task {task['task_id']}",
            f"Mission: {self.mission_id}",
            f"Outcome: {execution.get('completion_status') or execution.get('execution_status')}",
            "",
            "OpenCode output:",
            execution.get("execution_output") or "(none)",
            "",
            f"Changed files ({len(files)}): " + (", ".join(files) if files else "(none reported)"),
            f"Tests: {tests if tests else '(none reported)'}",
        ]
        return "\n".join(lines)

    def deliver_result(self, execution_id: str) -> Dict[str, Any]:
        execution = self.db.get_execution(execution_id)
        if not execution:
            return {"ok": False, "reason": "execution_missing"}
        if execution.get("execution_status") != "completed":
            return {"ok": False, "reason": "result_not_ready"}

        task = self.db.get_dev_task(execution["task_id"])
        if not task:
            return {"ok": False, "reason": "task_missing"}

        project_id, conversation_id = self._mission_identity()
        conversation = {
            "project_id": project_id,
            "project_url": self.project_url,
            "conversation_id": conversation_id,
        }

        content = self.build_delivery_content(task, execution)
        delivery_id = f"deliv-{uuid.uuid4().hex[:16]}"
        record = contracts.delivery(
            delivery_id=delivery_id,
            originating_execution_id=execution_id,
            target_project_id=project_id,
            target_conversation_id=conversation_id,
            response_content=content,
        )
        created = self.db.insert_delivery(record)
        if not created:
            existing = self.db.get_delivery_for_execution(execution_id)
            if existing and existing["delivery_status"] != "delivered":
                # Retry the pending/failed/uncertain delivery; never resend an
                # already-delivered message and never repeat the execution.
                return self._attempt_delivery(existing["delivery_id"], conversation)
            return {"ok": True, "duplicate": True, "delivery": existing}

        # The result is already persisted above; delivery can now fail safely.
        self._try_state(OrchState.CHATGPT_DELIVERY_PENDING, "delivery record persisted")
        return self._attempt_delivery(delivery_id, conversation)

    def _attempt_delivery(self, delivery_id: str, conversation: Dict[str, Any]) -> Dict[str, Any]:
        delivery = self.db.get_delivery(delivery_id)
        if not delivery:
            return {"ok": False, "reason": "delivery_missing"}
        if delivery["delivery_status"] == "delivered":
            return {"ok": True, "already_delivered": True, "delivery": delivery}

        # Normalise degraded states back to the delivery state so a retry never
        # silently leaves the mission stuck in DELIVERY_FAILED after success.
        if self.state() in (
            OrchState.DELIVERY_FAILED,
            OrchState.HUMAN_REVIEW_REQUIRED,
            OrchState.RECONCILIATION_REQUIRED,
            OrchState.WAITING_FOR_CHATGPT,
            OrchState.AUTHENTICATION_REQUIRED,
        ):
            self._try_state(OrchState.CHATGPT_DELIVERY_PENDING, "delivery resume/retry")

        if delivery["delivery_status"] == "uncertain":
            # Never blindly resend: require verification first.
            verified = self.chatgpt.verify_delivery({"content_prefix": delivery["response_content"][:120]})
            if verified.get("verified"):
                self.db.update_delivery(
                    delivery_id, delivery_status="delivered", confirmation_evidence=verified.get("evidence", {})
                )
                self._try_state(OrchState.CHATGPT_DELIVERED, "uncertain delivery verified")
                self._try_state(OrchState.CHATGPT_REVIEW_PENDING, "awaiting chatgpt review")
                return {"ok": True, "reconciled": True, "delivery": self.db.get_delivery(delivery_id)}
            self._try_state(OrchState.RECONCILIATION_REQUIRED, "uncertain delivery unverified")
            return {"ok": False, "reason": "delivery_uncertain_unverified"}

        gate = self._gate_provider(self.provider_chatgpt)
        if gate:
            self._try_state(OrchState.WAITING_FOR_CHATGPT, "chatgpt cooling down")
            return {"ok": False, "reason": "provider_cooldown", **gate}

        attempts = int(delivery["attempts"])
        if attempts >= self.delivery_retry_policy.max_attempts:
            self._try_state(OrchState.HUMAN_REVIEW_REQUIRED, "delivery retry budget exhausted")
            return {"ok": False, "reason": "retry_budget_exhausted", "attempts": attempts}

        attempts += 1
        self.db.update_delivery(delivery_id, delivery_status="attempting", attempts=attempts)
        attempt = self.chatgpt.deliver_message(conversation, delivery["response_content"], dedupe_key=delivery_id)

        status = attempt.get("status")
        if attempt.get("ok") and status == "delivered":
            evidence = dict(attempt.get("evidence") or {})
            evidence["attempts"] = attempts
            self.db.update_delivery(delivery_id, delivery_status="delivered", confirmation_evidence=evidence)
            self.db.set_provider_state(
                self.provider_chatgpt, available=True, cooldown_until=None, consecutive_failures=0
            )
            self.db.audit_orch("delivery_confirmed", delivery_id, f"attempts={attempts}")
            self._try_state(OrchState.CHATGPT_DELIVERED, "delivery verified")
            self._try_state(OrchState.CHATGPT_REVIEW_PENDING, "awaiting chatgpt review")
            return {"ok": True, "delivery": self.db.get_delivery(delivery_id), "attempts": attempts}

        reason = attempt.get("reason", "unknown")
        evidence = {"attempt": attempts, "reason": reason, "detail": str(attempt.get("detail") or "")[:300]}

        if status == "uncertain":
            self.db.update_delivery(delivery_id, delivery_status="uncertain", confirmation_evidence=evidence)
            self._try_state(OrchState.RECONCILIATION_REQUIRED, "delivery uncertain", reason)
            return {"ok": False, "reason": reason, "status": "uncertain", "reconcile": True}

        if reason in ("chatgpt_rate_limited",):
            delay = self.delivery_retry_policy.delay_for(attempts, retry_after=attempt.get("retry_after"))
            self.db.set_provider_state(
                self.provider_chatgpt,
                available=False,
                cooldown_until=self.cooldowns.until(delay),
                consecutive_failures=1,
                last_error=reason,
            )
            self.db.update_delivery(delivery_id, delivery_status="failed", confirmation_evidence=evidence)
            self._try_state(OrchState.DELIVERY_FAILED, "delivery rate limited", reason)
            return {"ok": False, "reason": reason, "cooldown_seconds": delay}

        if reason == "chatgpt_authentication_required":
            self.db.update_delivery(delivery_id, delivery_status="failed", confirmation_evidence=evidence)
            self._try_state(OrchState.AUTHENTICATION_REQUIRED, "chatgpt auth expired", reason)
            return {"ok": False, "reason": reason, "requires_operator": True}

        self.db.update_delivery(delivery_id, delivery_status="failed", confirmation_evidence=evidence)
        if attempts >= self.delivery_retry_policy.max_attempts:
            self._try_state(OrchState.HUMAN_REVIEW_REQUIRED, "delivery failed, budget exhausted", reason)
        else:
            self._try_state(OrchState.DELIVERY_FAILED, "delivery failed, retryable", reason)
        return {"ok": False, "reason": reason, "attempts": attempts, "retryable": attempts < self.delivery_retry_policy.max_attempts}

    def record_delivery_ack(self, delivery_id: str, evidence: Dict[str, Any]) -> Dict[str, Any]:
        delivery = self.db.get_delivery(delivery_id)
        if not delivery:
            return {"ok": False, "reason": "delivery_not_found"}
        if delivery["delivery_status"] == "delivered":
            return {"ok": True, "already_delivered": True}
        self.db.update_delivery(delivery_id, delivery_status="delivered", confirmation_evidence=evidence or {})
        self.db.audit_orch("delivery_ack_recorded", delivery_id, json.dumps(evidence or {})[:300])
        if self.state() == OrchState.CHATGPT_DELIVERY_PENDING:
            self._try_state(OrchState.CHATGPT_DELIVERED, "operator acknowledgement")
            self._try_state(OrchState.CHATGPT_REVIEW_PENDING, "awaiting chatgpt review")
        elif self.state() in (OrchState.RECONCILIATION_REQUIRED, OrchState.DELIVERY_FAILED):
            self._try_state(OrchState.HUMAN_REVIEW_REQUIRED, "ack recorded from degraded state")
        return {"ok": True, "delivery_id": delivery_id, "status": "delivered"}

    # ------------------------------------------------------------------
    # cycle / recovery
    # ------------------------------------------------------------------

    def resume_pending(self) -> Optional[Dict[str, Any]]:
        """Advance already-approved work without waiting for a new message.

        This is what makes the approval gate operational: after an operator
        approves a task, the next worker cycle executes it and delivers the
        result. A task that already has an execution row is never resubmitted —
        that case belongs to :meth:`recover`.
        """
        tasks = self.db.list_dev_tasks(mission_id=self.mission_id, limit=20)
        for task in reversed(tasks):  # oldest first
            if task["task_status"] != "ready":
                continue
            if self.db.get_execution_for_task(task["task_id"]):
                continue
            submitted = self.submit_and_execute(task["task_id"])
            if not submitted.get("ok"):
                return {**submitted, "resumed_task": task["task_id"]}
            if submitted.get("waiting"):
                return {
                    "ok": True,
                    "reason": "waiting_for_opencode",
                    "task_id": task["task_id"],
                    "state": self.state().value,
                }
            execution = submitted.get("execution") or {}
            if execution.get("execution_status") != "completed":
                return {
                    "ok": True,
                    "reason": "result_not_ready",
                    "task_id": task["task_id"],
                    "state": self.state().value,
                }
            delivered = self.deliver_result(execution["execution_id"])
            return {
                "ok": bool(delivered.get("ok")),
                "reason": "delivered" if delivered.get("ok") else delivered.get("reason"),
                "task_id": task["task_id"],
                "execution_id": execution.get("execution_id"),
                "state": self.state().value,
                "delivery": delivered,
                "resumed": True,
            }
        return None

    def run_cycle(self) -> Dict[str, Any]:
        """One pass: resume approved work -> read -> ingest -> task -> execute -> deliver."""
        if self.is_paused():
            return {"ok": False, "reason": "paused", "state": self.state().value}

        state = self.state()
        if is_terminal(state):
            return {"ok": False, "reason": "mission_terminal", "state": state.value}
        if state in (OrchState.CHATGPT_REVIEW_PENDING, OrchState.WAITING_FOR_CHATGPT, OrchState.HUMAN_REVIEW_REQUIRED):
            self._try_state(OrchState.READY, "operator/agent resumed the loop")

        if self.state() in (
            OrchState.RECONCILIATION_REQUIRED,
            OrchState.EXECUTION_INTERRUPTED,
            OrchState.QUOTA_EXHAUSTED,
            OrchState.AUTHENTICATION_REQUIRED,
        ):
            return {"ok": False, "reason": "recovery_required", "state": self.state().value}

        resumed = self.resume_pending()
        if resumed is not None:
            return resumed

        read = self.chatgpt.read_latest_messages(self.project_url)
        if not read.get("ok"):
            return self._handle_chatgpt_failure(read)

        messages = read.get("messages") or []
        if not messages:
            self._try_state(OrchState.WAITING_FOR_CHATGPT, "no new message")
            return {"ok": True, "reason": "no_message", "state": self.state().value}

        message = messages[-1]
        self._try_state(OrchState.CHATGPT_MESSAGE_DETECTED, message["message_id"][:40])

        ingested = self.ingest_message(message)
        if not ingested.get("ok"):
            self._try_state(OrchState.FAILED, "invalid inbound message")
            return ingested
        self._try_state(OrchState.MESSAGE_PERSISTED, "message persisted")

        if ingested.get("duplicate"):
            self._try_state(OrchState.READY, "duplicate message ignored")
            return {"ok": True, "reason": "duplicate_message", "message_id": message["message_id"]}

        created = self.create_task(message)
        if not created.get("ok"):
            self.db.mark_inbound_processed(message["message_id"])
            return created

        task_id = created["task_id"]
        if created.get("requires_approval"):
            self.db.mark_inbound_processed(message["message_id"])
            return {
                "ok": True,
                "reason": "awaiting_approval",
                "task_id": task_id,
                "state": self.state().value,
                "governance": created.get("governance"),
            }

        submitted = self.submit_and_execute(task_id)
        if not submitted.get("ok"):
            return submitted

        if submitted.get("waiting"):
            return {"ok": True, "reason": "waiting_for_opencode", "task_id": task_id, "state": self.state().value}

        execution = submitted.get("execution") or {}
        delivered = self.deliver_result(execution.get("execution_id", ""))
        self.db.mark_inbound_processed(message["message_id"])
        return {
            "ok": bool(delivered.get("ok")),
            "reason": "delivered" if delivered.get("ok") else delivered.get("reason"),
            "task_id": task_id,
            "execution_id": execution.get("execution_id"),
            "state": self.state().value,
            "delivery": delivered,
        }

    def _handle_chatgpt_failure(self, read: Dict[str, Any]) -> Dict[str, Any]:
        reason = read.get("reason", "unknown")
        if reason == "chatgpt_authentication_required":
            self._try_state(OrchState.AUTHENTICATION_REQUIRED, "chatgpt auth", reason)
            return {"ok": False, "reason": reason, "requires_operator": True}
        if reason == "chatgpt_rate_limited":
            delay = self.retry_policy.delay_for(1, retry_after=read.get("retry_after"))
            self.db.set_provider_state(
                self.provider_chatgpt,
                available=False,
                cooldown_until=self.cooldowns.until(delay),
                consecutive_failures=1,
                last_error=reason,
            )
            self._try_state(OrchState.QUOTA_EXHAUSTED, "chatgpt rate limited", reason)
            return {"ok": False, "reason": reason, "cooldown_seconds": delay}
        if reason == "chatgpt_cdp_disconnected":
            self._try_state(OrchState.WAITING_FOR_CHATGPT, "chatgpt transport disconnected", reason)
            return {"ok": False, "reason": reason, "reconnect_required": True}
        if reason == "chatgpt_project_unavailable":
            self._try_state(OrchState.HUMAN_REVIEW_REQUIRED, "project unavailable", reason)
            return {"ok": False, "reason": reason, "requires_operator": True}
        if reason == "chatgpt_ambiguous_response":
            self._try_state(OrchState.HUMAN_REVIEW_REQUIRED, "ambiguous response", reason)
            return {"ok": False, "reason": reason, "requires_operator": True}
        self._try_state(OrchState.WAITING_FOR_CHATGPT, "chatgpt read failed", reason)
        return {"ok": False, "reason": reason}

    def run(self, max_cycles: int = 1) -> List[Dict[str, Any]]:
        cycles = max(1, min(int(max_cycles), MAX_CYCLES_HARD_LIMIT))
        results = []
        for _ in range(cycles):
            try:
                result = self.run_cycle()
            except InvalidTransition:
                raise
            except Exception as exc:  # defensive: a cycle must not kill the worker
                result = {"ok": False, "reason": "cycle_exception", "error": f"{type(exc).__name__}: {exc}"}
            results.append(result)
            if not result.get("ok") and result.get("reason") not in ("no_message",):
                break
            if result.get("reason") in ("duplicate_message",):
                break
        return results

    def recover(self) -> Dict[str, Any]:
        """Reconcile persisted state after a restart.

        Guarantees: never resubmit to OpenCode, never resend a delivered message,
        and never lose a persisted result.
        """
        state = self.state()
        actions: List[str] = []

        if self.is_paused():
            self.last_recovery = {"state": state.value, "actions": ["paused"], "requires_operator": False}
            return self.last_recovery

        mission_tasks = self.db.list_dev_tasks(mission_id=self.mission_id, limit=5)
        latest_task = mission_tasks[0] if mission_tasks else None
        execution = self.db.get_execution_for_task(latest_task["task_id"]) if latest_task else None
        has_result = bool(execution and execution.get("execution_status") == "completed")
        delivery = self.db.get_delivery_for_execution(execution["execution_id"]) if execution else None

        target = recovery_target(state, has_result=has_result, has_session=bool(execution and execution.get("opencode_session_id")))

        if state in (
            OrchState.OPENCODE_SUBMISSION,
            OrchState.OPENCODE_EXECUTION,
            OrchState.WAITING_FOR_OPENCODE,
            OrchState.RECONCILIATION_REQUIRED,
            OrchState.EXECUTION_INTERRUPTED,
        ):
            reconciled = self.executor.reconcile(execution) if execution else {"ok": True, "found": False}
            self.db.save_checkpoint(
                "restart_reconcile",
                {"previous_state": state.value, "reconcile": reconciled},
                mission_id=self.mission_id,
                task_id=latest_task["task_id"] if latest_task else None,
                execution_id=execution["execution_id"] if execution else None,
            )
            actions.append("reconciled_execution")
            if reconciled.get("ok") and reconciled.get("found"):
                if execution.get("opencode_session_id"):
                    collected = self._collect_result(latest_task["task_id"], execution["execution_id"])
                    actions.append(f"collected_result:{collected.get('ok')}")
                    if collected.get("ok") and not collected.get("waiting"):
                        target = OrchState.RESULT_PERSISTED
                        has_result = True
                else:
                    target = OrchState.RECONCILIATION_REQUIRED
            else:
                target = OrchState.RECONCILIATION_REQUIRED
                actions.append("no_session_found")

        if target != state and can_transition(state, target):
            self._set_state(target, "recovery")

        # A persisted result always moves forward to delivery, never backwards.
        # Covers the case where the restart happened after RESULT_PERSISTED but
        # before the delivery row was created (state is already
        # CHATGPT_DELIVERY_PENDING) — the result must still be delivered.
        delivery_states = (
            OrchState.RECONCILIATION_REQUIRED,
            OrchState.RESULT_PERSISTED,
            OrchState.CHATGPT_DELIVERY_PENDING,
            OrchState.DELIVERY_FAILED,
            OrchState.WAITING_FOR_CHATGPT,
        )
        if has_result and execution and self.state() in delivery_states:
            current = self.state()
            if current != OrchState.CHATGPT_DELIVERY_PENDING and can_transition(
                current, OrchState.CHATGPT_DELIVERY_PENDING
            ):
                self._set_state(OrchState.CHATGPT_DELIVERY_PENDING, "recovery: result already persisted")
                actions.append("delivery_resumed")
            delivery = self.db.get_delivery_for_execution(execution["execution_id"])
            if delivery is None:
                delivered = self.deliver_result(execution["execution_id"])
                actions.append(f"delivery_created:{delivered.get('ok')}")
            elif delivery["delivery_status"] in ("pending", "failed", "attempting", "uncertain"):
                conversation = {
                    "project_id": delivery["target_project_id"],
                    "project_url": self.project_url,
                    "conversation_id": delivery["target_conversation_id"],
                }
                delivered = self._attempt_delivery(delivery["delivery_id"], conversation)
                actions.append(f"delivery_retried:{delivered.get('ok')}")
            elif delivery["delivery_status"] == "delivered":
                self._try_state(OrchState.CHATGPT_DELIVERED, "recovery: already delivered")
                self._try_state(OrchState.CHATGPT_REVIEW_PENDING, "recovery: awaiting review")
                actions.append("delivery_already_confirmed")

        claimed = self.db.get_provider_state(self.provider_opencode) or {}
        if claimed.get("cooldown_until") and self.cooldowns.is_open(claimed.get("cooldown_until")):
            self.db.set_provider_state(
                self.provider_opencode, available=True, cooldown_until=None, consecutive_failures=0
            )
            actions.append("opencode_cooldown_cleared")

        self.last_recovery = {
            "ok": True,
            "previous_state": state.value,
            "state": self.state().value,
            "actions": actions,
            "requires_operator": self.state()
            in (OrchState.HUMAN_REVIEW_REQUIRED, OrchState.AUTHENTICATION_REQUIRED, OrchState.RECONCILIATION_REQUIRED),
        }
        self.db.save_checkpoint("recovery_complete", self.last_recovery, mission_id=self.mission_id)
        return self.last_recovery

    def pause(self, reason: str = "operator") -> Dict[str, Any]:
        state = self.state()
        self.db.set_mission_paused(self.mission_id, True, OrchState.PAUSED.value)
        self.db.audit_orch("mission_paused", self.mission_id, reason)
        return {"ok": True, "state": OrchState.PAUSED.value, "previous_state": state.value}

    def resume(self) -> Dict[str, Any]:
        self.db.set_mission_paused(self.mission_id, False, OrchState.READY.value)
        self.db.audit_orch("mission_resumed", self.mission_id, "")
        return {"ok": True, "state": OrchState.READY.value}

    # ------------------------------------------------------------------
    # observability
    # ------------------------------------------------------------------

    def status_report(self) -> Dict[str, Any]:
        mission = self.db.get_mission(self.mission_id) or {}
        state = self.state()
        inbox = self.db.list_inbound_messages(limit=1)
        tasks = self.db.list_dev_tasks(mission_id=self.mission_id, limit=5)
        pending_task = next(
            (t for t in tasks if t["task_status"] in ("awaiting_approval", "ready", "running")), None
        )
        latest_task = tasks[0] if tasks else None
        execution = self.db.get_execution_for_task(latest_task["task_id"]) if latest_task else None
        delivery = self.db.get_delivery_for_execution(execution["execution_id"]) if execution else None
        providers = {p["provider"]: p for p in self.db.list_provider_state()}
        checkpoint = self.db.latest_checkpoint(self.mission_id)

        return {
            "mission": {
                "id": self.mission_id,
                "title": mission.get("title", self.mission_title),
                "state": state.value,
                "paused": bool(mission.get("paused")),
                "target_repository": mission.get("target_repository", self.workspace),
                "target_branch": mission.get("target_branch", self.target_branch),
            },
            "current_state": state.value,
            "required_action": REQUIRED_ACTION.get(state),
            "latest_inbound_message": _slim_message(inbox[0]) if inbox else None,
            "pending_task": _slim_task(pending_task) if pending_task else None,
            "latest_task": _slim_task(latest_task) if latest_task else None,
            "active_execution": _slim_execution(execution) if execution else None,
            "last_confirmed_result": _slim_result(execution) if execution and execution.get("execution_status") == "completed" else None,
            "pending_delivery": _slim_delivery(delivery) if delivery else None,
            "providers": {
                name: {
                    "available": bool(p.get("available")),
                    "cooldown_remaining": self.cooldowns.remaining(p.get("cooldown_until")),
                    "consecutive_failures": int(p.get("consecutive_failures") or 0),
                    "last_error": p.get("last_error") or "",
                }
                for name, p in providers.items()
            },
            "inbox": self.db.inbox_counts(),
            "recovery_reason": (checkpoint or {}).get("reason"),
            "last_recovery": self.last_recovery or None,
            "required_human_action": REQUIRED_ACTION.get(state),
            "generated_at": self._clock(),
        }

    # ------------------------------------------------------------------
    # prompt
    # ------------------------------------------------------------------

    def _build_prompt(self, task: Dict[str, Any]) -> str:
        return (
            "You are operating in the configured DEV repository only.\n"
            "Do not access PROD, credentials, .env secrets, or launch trading sessions.\n"
            "Preserve existing dirty/untracked files. Do not commit or push.\n"
            "Produce a report under reports/execution/ when applicable.\n\n"
            f"TASK ID: {task['task_id']}\n"
            f"TASK:\n{task['task_description']}\n"
        )


# --- helpers -------------------------------------------------------------


def _hash(text: str) -> str:
    import hashlib

    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def _title_from(text: str) -> str:
    first = (text or "").strip().splitlines()[0] if (text or "").strip() else "untitled task"
    return first[:120]


def _raise_risk(current: str, candidate: str) -> str:
    order = {"low": 0, "medium": 1, "high": 2, "critical": 3}
    return candidate if order.get(candidate, 0) > order.get(current, 0) else current


def _slim_message(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "message_id": row.get("message_id"),
        "conversation_id": row.get("conversation_id"),
        "received_at": row.get("received_at"),
        "message_timestamp": row.get("message_timestamp"),
        "identity_source": row.get("message_identity_source"),
        "processed": bool(row.get("processed")),
        "duplicate_count": int(row.get("duplicate_count") or 0),
        "preview": (row.get("message_content") or "")[:200],
    }


def _slim_task(row: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not row:
        return None
    return {
        "task_id": row.get("task_id"),
        "status": row.get("task_status"),
        "risk": row.get("risk_classification"),
        "title": row.get("task_title"),
        "originating_message_id": row.get("originating_message_id"),
        "approval_requirements": row.get("approval_requirements") or [],
    }


def _slim_execution(row: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not row:
        return None
    return {
        "execution_id": row.get("execution_id"),
        "task_id": row.get("task_id"),
        "execution_status": row.get("execution_status"),
        "completion_status": row.get("completion_status"),
        "opencode_session_id": row.get("opencode_session_id"),
        "changed_files": row.get("changed_files") or [],
        "submitted_at": row.get("submitted_at"),
    }


def _slim_result(row: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not row:
        return None
    return {
        "execution_id": row.get("execution_id"),
        "completion_status": row.get("completion_status"),
        "test_results": row.get("test_results") or {},
        "changed_files": row.get("changed_files") or [],
        "output_preview": (row.get("execution_output") or "")[:500],
    }


def _slim_delivery(row: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not row:
        return None
    return {
        "delivery_id": row.get("delivery_id"),
        "status": row.get("delivery_status"),
        "attempts": int(row.get("attempts") or 0),
        "target_conversation_id": row.get("target_conversation_id"),
    }
