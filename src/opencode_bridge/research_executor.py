"""Secure, bounded research execution pipeline for the OpenCode Automation Controller.

Reuses existing research contracts, DB methods, OpenCodeAdapter and config helpers.
Executes ONLY against the dedicated isolated research OpenCode instance (research_mode=True).
Never falls back to the unrestricted development instance.
"""
import json
import logging
import threading
import time
from typing import Any, Callable, Dict, List, Optional

from .config import (
    opencode_research_agent,
    opencode_research_base_url,
    opencode_research_model_id,
    opencode_research_model_provider,
    opencode_research_tools,
    opencode_research_workspace,
    opencode_timeout,
    opencode_username,
    opencode_password,
)
from .contracts import research_result, validate_research_result
from .db import BridgeDB
from .opencode_adapter import OpenCodeAdapter, OpenCodeError

logger = logging.getLogger("opencode_bridge.research_executor")

TERMINAL_STATUSES = {"completed", "failed", "cancelled", "timeout"}
REDACT_KEYS = {"token", "secret", "password", "authorization", "api_key", "apikey", "key", "credential"}
MAX_FIELD_CHARS = 4096
MAX_EVIDENCE_ITEMS = 50


def _collect_secrets(value, depth: int = 0) -> set:
    out: set = set()
    if depth > 6:
        return out
    if isinstance(value, dict):
        for k, v in value.items():
            kl = str(k).lower()
            if any(rk in kl for rk in REDACT_KEYS):
                if isinstance(v, str) and v.strip():
                    out.add(v)
            else:
                out |= _collect_secrets(v, depth + 1)
    elif isinstance(value, (list, tuple)):
        for x in value:
            out |= _collect_secrets(x, depth + 1)
    return out


def _redact_value(value: Any, secrets: Optional[set] = None, depth: int = 0) -> Any:
    if secrets is None:
        secrets = _collect_secrets(value)
    if depth > 6:
        return "[TRUNCATED]"
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            kl = str(k).lower()
            if any(rk in kl for rk in REDACT_KEYS):
                out[k] = "[REDACTED]"
            else:
                out[k] = _redact_value(v, secrets, depth + 1)
        return out
    if isinstance(value, (list, tuple)):
        return [_redact_value(x, secrets, depth + 1) for x in value[:MAX_EVIDENCE_ITEMS]]
    if isinstance(value, str):
        s = value
        for sec in secrets:
            if sec:
                s = s.replace(sec, "[REDACTED]")
        if len(s) > MAX_FIELD_CHARS:
            return s[:MAX_FIELD_CHARS] + "...[truncated]"
        return s
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return str(value)[:MAX_FIELD_CHARS]


def _truncate(s: Optional[str], limit: int = MAX_FIELD_CHARS) -> Optional[str]:
    if s is None:
        return None
    if len(s) <= limit:
        return s
    return s[:limit] + "...[truncated]"


class ResearchExecutor:
    """Executes a persisted research task against the isolated research OpenCode instance."""

    def __init__(self, db: BridgeDB, adapter_factory: Optional[Callable[[], OpenCodeAdapter]] = None,
                 poll_interval: float = 2.0, model_provider: Optional[str] = None,
                 model_id: Optional[str] = None):
        self.db = db
        self.adapter_factory = adapter_factory
        self.poll_interval = max(0.5, float(poll_interval))
        self.model_provider = model_provider or opencode_research_model_provider()
        self.model_id = model_id or opencode_research_model_id()
        self._in_progress: set = set()
        self._lock = threading.Lock()
        self._cancelled: set = set()

    def _default_adapter_factory(self) -> OpenCodeAdapter:
        base = opencode_research_base_url()
        if not base:
            raise OpenCodeError("research base url not configured (OPENCODE_RESEARCH_BASE_URL)")
        return OpenCodeAdapter(
            base_url=base,
            username=opencode_username(),
            password=opencode_password(),
            agent=opencode_research_agent(),
            tools=opencode_research_tools(),
            research_mode=True,
        )

    def _get_factory(self) -> Callable[[], OpenCodeAdapter]:
        return self.adapter_factory or self._default_adapter_factory

    def _is_cancelled(self, research_id: str) -> bool:
        if research_id in self._cancelled:
            return True
        try:
            row = self.db.get_research_task(research_id)
            if row and row.get("cancel_requested"):
                return True
        except Exception:
            pass
        return False

    def cancel(self, research_id: str) -> bool:
        self._cancelled.add(research_id)
        try:
            return self.db.cancel_research_task(research_id)
        except Exception:
            return False

    def execute(self, research_id: str) -> Dict[str, Any]:
        task = self.db.get_research_task(research_id)
        if not task:
            return {"ok": False, "reason": "not_found", "research_id": research_id}

        status = task.get("status")
        # Idempotency: already completed -> return cached result.
        if status == "completed" and task.get("result_json"):
            try:
                cached = json.loads(task["result_json"])
            except Exception:
                cached = {"raw": task["result_json"]}
            return {"ok": True, "research_id": research_id, "status": "completed",
                    "cached": True, "result": cached, "session_id": task.get("session_id")}

        # Cancelled -> do not re-run.
        if status == "cancelled" or task.get("cancel_requested"):
            return {"ok": False, "research_id": research_id, "status": "cancelled",
                    "reason": "task cancelled"}

        # Already running (and not cancelled) -> refuse duplicate concurrent execution.
        with self._lock:
            if research_id in self._in_progress:
                return {"ok": False, "research_id": research_id, "status": "running",
                        "reason": "already_running"}
            self._in_progress.add(research_id)
        try:
            return self._run(task)
        finally:
            with self._lock:
                self._in_progress.discard(research_id)

    def _run(self, task: Dict[str, Any]) -> Dict[str, Any]:
        research_id = task["research_id"]
        prompt = task["prompt"]
        timeout_seconds = float(task.get("timeout_seconds") or 120.0)
        deadline = time.time() + timeout_seconds
        started_at = time.time()

        try:
            self.db.update_research_task(research_id, status="running", started_at=started_at)
        except Exception as exc:
            return {"ok": False, "research_id": research_id, "status": "failed",
                    "error": f"persistence_failed: {type(exc).__name__}: {exc}"}

        session_id = None
        adapter = None
        try:
            adapter = self._get_factory()()
            # Isolation check: must be research_mode.
            if not getattr(adapter, "research_mode", False):
                raise OpenCodeError("adapter is not in research_mode; refusing to run")

            workspace = opencode_research_workspace()
            agent = opencode_research_agent()
            tools = opencode_research_tools()

            session = adapter.create_session(title=f"research-{research_id}", directory=workspace, agent=agent)
            session_id = session.get("id") if isinstance(session, dict) else None
            if not session_id:
                raise OpenCodeError("failed to create OpenCode session")

            adapter.send_prompt_async(
                session_id, prompt,
                model={"providerID": self.model_provider, "modelID": self.model_id},
                directory=workspace, agent=agent, tools=tools,
            )

            # Poll for completion.
            final_text = ""
            last_msgs: List[Dict[str, Any]] = []
            provider_error: Optional[str] = None
            timed_out = False
            cancelled = False
            got_assistant = False
            while time.time() < deadline:
                if self._is_cancelled(research_id):
                    cancelled = True
                    break
                time.sleep(self.poll_interval)
                try:
                    last_msgs = adapter.get_messages(session_id, limit=100, directory=workspace)
                except OpenCodeError as exc:
                    provider_error = f"{type(exc).__name__}: {exc}"
                    break
                except Exception as exc:
                    provider_error = f"{type(exc).__name__}: {exc}"
                    break
                for m in last_msgs:
                    info = m.get("info") if isinstance(m, dict) else None
                    if isinstance(info, dict) and info.get("role") == "assistant":
                        got_assistant = True
                ft = OpenCodeAdapter.extract_final_assistant(last_msgs) or ""
                if ft.strip():
                    final_text = ft.strip()
                    break
            else:
                timed_out = True

            if cancelled:
                completed_at = time.time()
                self.db.update_research_task(
                    research_id, status="cancelled", session_id=session_id,
                    completed_at=completed_at, error="cancelled by request",
                )
                return {"ok": False, "research_id": research_id, "status": "cancelled",
                        "session_id": session_id, "error": "cancelled by request"}

            # Check assistant error field.
            if not provider_error:
                for m in last_msgs:
                    info = m.get("info") if isinstance(m, dict) else None
                    if isinstance(info, dict) and info.get("role") == "assistant" and info.get("error"):
                        provider_error = str(info.get("error"))

            # Determine selected model from assistant messages.
            selected_provider = None
            selected_model = None
            for m in last_msgs:
                info = m.get("info") if isinstance(m, dict) else None
                if isinstance(info, dict) and info.get("role") == "assistant":
                    selected_provider = info.get("providerID") or selected_provider
                    selected_model = info.get("modelID") or selected_model

            tool_calls = self._extract_tool_calls(last_msgs)

            completed_at = time.time()
            duration = completed_at - started_at

            if provider_error:
                err = provider_error[:1000]
                self.db.update_research_task(
                    research_id, status="failed", session_id=session_id,
                    completed_at=completed_at, error=err,
                )
                return {"ok": False, "research_id": research_id, "status": "failed",
                        "session_id": session_id, "error": err,
                        "duration_seconds": round(duration, 3)}

            if not got_assistant and timed_out:
                err = "timeout: no assistant output within deadline"
                self.db.update_research_task(
                    research_id, status="timeout", session_id=session_id,
                    completed_at=completed_at, error=err,
                )
                return {"ok": False, "research_id": research_id, "status": "timeout",
                        "session_id": session_id, "error": err,
                        "duration_seconds": round(duration, 3)}

            if not final_text.strip():
                err = "empty assistant output (possible provider quota or model failure)"
                self.db.update_research_task(
                    research_id, status="failed", session_id=session_id,
                    completed_at=completed_at, error=err,
                )
                return {"ok": False, "research_id": research_id, "status": "failed",
                        "session_id": session_id, "error": err,
                        "duration_seconds": round(duration, 3)}

            # Build structured result.
            evidence = []
            for tc in tool_calls:
                evidence.append({
                    "type": "SEARCH_SNIPPET" if tc.get("tool") == "websearch" else "FULL_PAGE",
                    "tool": tc.get("tool"),
                    "call_id": tc.get("call_id"),
                    "status": tc.get("status"),
                    "input": _redact_value(tc.get("input")),
                    "output": _redact_value(tc.get("output")),
                    "error": _redact_value(tc.get("error")),
                })
            result = research_result(
                research_id=research_id,
                status="completed",
                completed_at=completed_at,
                output=_truncate(final_text),
                error=None,
                session_id=session_id,
                evidence=evidence[:MAX_EVIDENCE_ITEMS],
            )
            # Add execution metadata not in the base contract (extra fields allowed).
            result["started_at"] = started_at
            result["duration_seconds"] = round(duration, 3)
            result["requested_provider"] = self.model_provider
            result["requested_model"] = self.model_id
            result["selected_provider"] = selected_provider
            result["selected_model"] = selected_model
            result["agent"] = opencode_research_agent()
            result["tool_names"] = [tc.get("tool") for tc in tool_calls]
            result["tool_count"] = len(tool_calls)

            ok, errors = validate_research_result(result)
            if not ok:
                err = "invalid structured result: " + "; ".join(errors)
                self.db.update_research_task(
                    research_id, status="failed", session_id=session_id,
                    completed_at=completed_at, error=err,
                )
                return {"ok": False, "research_id": research_id, "status": "failed",
                        "session_id": session_id, "error": err,
                        "duration_seconds": round(duration, 3)}

            # Persist (idempotent: only update if not already completed).
            row = self.db.get_research_task(research_id)
            if row and row.get("status") == "completed" and row.get("result_json"):
                try:
                    cached = json.loads(row["result_json"])
                except Exception:
                    cached = {"raw": row["result_json"]}
                return {"ok": True, "research_id": research_id, "status": "completed",
                        "cached": True, "result": cached, "session_id": row.get("session_id")}
            self.db.update_research_task(
                research_id, status="completed", session_id=session_id,
                completed_at=completed_at, result_json=json.dumps(result, default=str),
            )
            return {"ok": True, "research_id": research_id, "status": "completed",
                    "session_id": session_id, "result": result,
                    "duration_seconds": round(duration, 3)}

        except OpenCodeError as exc:
            completed_at = time.time()
            err = f"{type(exc).__name__}: {exc}"[:1000]
            try:
                self.db.update_research_task(
                    research_id, status="failed", session_id=session_id,
                    completed_at=completed_at, error=err,
                )
            except Exception:
                pass
            return {"ok": False, "research_id": research_id, "status": "failed",
                    "session_id": session_id, "error": err}
        except Exception as exc:
            completed_at = time.time()
            err = f"{type(exc).__name__}: {exc}"[:1000]
            try:
                self.db.update_research_task(
                    research_id, status="failed", session_id=session_id,
                    completed_at=completed_at, error=err,
                )
            except Exception:
                pass
            return {"ok": False, "research_id": research_id, "status": "failed",
                    "session_id": session_id, "error": err}

    def _extract_tool_calls(self, msgs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for m in msgs or []:
            for p in (m.get("parts") or []):
                if not isinstance(p, dict) or p.get("type") != "tool":
                    continue
                state = p.get("state") or {}
                out.append({
                    "tool": p.get("tool"),
                    "call_id": p.get("callID"),
                    "status": state.get("status"),
                    "title": state.get("title"),
                    "input": _redact_value(state.get("input")),
                    "output": _redact_value(state.get("output")),
                    "error": _redact_value(state.get("error")),
                })
        return out