"""WP-423: authenticated, loopback-only controller HTTP API.

Deliberately built on the standard library (``http.server``) because this
project's virtual environment does **not** install fastapi/uvicorn. The existing
``mcp_server.py`` (fastapi) is intentionally left untouched and unimportable —
it is a pre-existing condition, not a regression introduced here.

Security posture
----------------
* Binds loopback only; a non-loopback host raises.
* Fails **closed**: if ``CONTROLLER_API_TOKEN`` is unset the API answers ``503``
  instead of serving unauthenticated task execution.
* Bearer token compared with :func:`hmac.compare_digest` (no timing leak).
* Request bodies are bounded (``MAX_BODY_BYTES``) and rejected with ``413``.
* JSON is parsed and schema-validated by the orchestrator's contract layer.
* No credential, cookie, ``Authorization`` header or body content is ever logged;
  the access log records method, path, status and byte count only.
* No tunneling, no public bind, no wildcard CORS.

There is intentionally no ``/submit`` style "run anything" endpoint: the only
way work enters the system is a schema-valid ChatGPT inbox message, which is
then subject to governance and approval.
"""

import hmac
import json
import logging
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable, Dict, Optional, Tuple
from urllib.parse import urlparse

logger = logging.getLogger("opencode_bridge.controller_api")

#: Hard body limit (bytes). Larger payloads get ``413``.
MAX_BODY_BYTES = 64 * 1024

#: Only these hosts may be bound.
LOOPBACK_HOSTS = ("127.0.0.1", "localhost", "::1")

TOKEN_ENV_VAR = "CONTROLLER_API_TOKEN"

LOOPBACK_BIND = "127.0.0.1"
DEFAULT_PORT = 8798


class ControllerAPIError(Exception):
    pass


def controller_api_token() -> str:
    """Read the bearer token from the environment (never persisted, never logged)."""
    return os.environ.get(TOKEN_ENV_VAR, "") or ""


def _json_bytes(payload: Dict[str, Any]) -> bytes:
    return json.dumps(payload, default=str, ensure_ascii=False).encode("utf-8")


class ControllerAPI:
    """Small routing layer over a :class:`MissionOrchestrator`.

    ``token_provider`` is injectable so tests never have to mutate the process
    environment.
    """

    def __init__(self, orchestrator, token_provider: Optional[Callable[[], str]] = None):
        self.orchestrator = orchestrator
        self._token_provider = token_provider or controller_api_token

    # -- routing -------------------------------------------------------

    def route(self, method: str, path: str) -> Optional[str]:
        """Return the logical route name for (method, path), or ``None``."""
        parsed = urlparse(path)
        parts = [p for p in parsed.path.split("/") if p]
        if not parts or parts[0] != "api":
            return None
        rest = parts[1:]
        key = (method.upper(), tuple(rest))
        table = {
            ("POST", ("chatgpt", "inbox")): "inbox_ingest",
            ("GET", ("inbox", "status")): "inbox_status",
            ("GET", ("health", "recovery")): "health_recovery",
            ("GET", ("health",)): "health",
            ("POST", ("mission", "pause")): "mission_pause",
            ("POST", ("mission", "resume")): "mission_resume",
            ("GET", ("mission",)): "mission_status",
        }
        if key in table:
            return table[key]
        # parametrised routes: /api/missions/{id}, /api/tasks/{id},
        # /api/tasks/{id}/approve, /api/executions/{id},
        # /api/deliveries/{id}/ack
        if len(rest) == 2 and rest[0] == "missions":
            return "mission_get"
        if len(rest) == 2 and rest[0] == "tasks":
            return "task_get"
        if len(rest) == 3 and rest[0] == "tasks" and rest[2] == "approve":
            return "task_approve"
        if len(rest) == 2 and rest[0] == "executions":
            return "execution_get"
        if len(rest) == 3 and rest[0] == "deliveries" and rest[2] == "ack":
            return "delivery_ack"
        return None

    @staticmethod
    def _path_parts(path: str):
        return [p for p in urlparse(path).path.split("/") if p]

    # -- handlers ------------------------------------------------------

    def _orchestrator_for(self, mission_id: str):
        """This milestone runs one mission per orchestrator instance."""
        return self.orchestrator

    def handle(self, method: str, path: str, body: bytes) -> Tuple[int, Dict[str, Any]]:
        route = self.route(method, path)
        if route is None:
            return 404, {"ok": False, "error": "not_found", "path": urlparse(path).path}

        parts = self._path_parts(path)
        try:
            if route == "inbox_ingest":
                return self._handle_inbox(body)
            if route == "inbox_status":
                return 200, {"ok": True, "inbox": self.orchestrator.db.inbox_counts()}
            if route == "health":
                return 200, {"ok": True, "service": "controller_api", "time": time.time()}
            if route == "health_recovery":
                report = self.orchestrator.status_report()
                return 200, {
                    "ok": True,
                    "last_recovery": report.get("last_recovery"),
                    "recovery_reason": report.get("recovery_reason"),
                    "providers": report.get("providers"),
                    "required_action": report.get("required_action"),
                }
            if route == "mission_pause":
                return 200, {"ok": True, **self.orchestrator.pause(_reason_from(body))}
            if route == "mission_resume":
                return 200, {"ok": True, **self.orchestrator.resume()}
            if route == "mission_status":
                return 200, {"ok": True, "status": self.orchestrator.status_report()}
            if route == "mission_get":
                mission_id = parts[-1]
                mission = self.orchestrator.db.get_mission(mission_id)
                if not mission:
                    return 404, {"ok": False, "error": "mission_not_found"}
                return 200, {"ok": True, "mission": mission,
                             "tasks": self.orchestrator.db.list_dev_tasks(mission_id=mission_id, limit=10)}
            if route == "task_get":
                task = self.orchestrator.db.get_dev_task(parts[-1])
                if not task:
                    return 404, {"ok": False, "error": "task_not_found"}
                execution = self.orchestrator.db.get_execution_for_task(task["task_id"])
                return 200, {"ok": True, "task": task, "execution": execution}
            if route == "task_approve":
                payload = _maybe_json(body)
                approved_by = str(payload.get("approved_by") or "operator")[:120]
                reason = str(payload.get("reason") or "")[:500]
                result = self.orchestrator.approve_task(parts[-2], approved_by=approved_by, reason=reason)
                return (200 if result.get("ok") else 409), result
            if route == "execution_get":
                execution = self.orchestrator.db.get_execution(parts[-1])
                if not execution:
                    return 404, {"ok": False, "error": "execution_not_found"}
                delivery = self.orchestrator.db.get_delivery_for_execution(execution["execution_id"])
                return 200, {"ok": True, "execution": execution, "delivery": delivery}
            if route == "delivery_ack":
                payload = _maybe_json(body)
                evidence = payload.get("evidence")
                if evidence is not None and not isinstance(evidence, dict):
                    return 400, {"ok": False, "error": "evidence_must_be_object"}
                result = self.orchestrator.record_delivery_ack(parts[-2], evidence or {})
                return (200 if result.get("ok") else 404), result
        except Exception as exc:  # never leak a stack trace or secret to the wire
            logger.error("controller api handler error for %s %s: %s", method, urlparse(path).path, type(exc).__name__)
            return 500, {"ok": False, "error": "internal_error", "type": type(exc).__name__}

        return 404, {"ok": False, "error": "not_found"}

    def _handle_inbox(self, body: bytes) -> Tuple[int, Dict[str, Any]]:
        try:
            payload = json.loads(body.decode("utf-8") or "{}")
        except (UnicodeDecodeError, json.JSONDecodeError):
            return 400, {"ok": False, "error": "invalid_json"}
        if not isinstance(payload, dict):
            return 400, {"ok": False, "error": "payload_must_be_object"}

        # Transport-level metadata the controller legitimately owns. Message
        # identity and content are never invented here.
        payload.setdefault("received_at", time.time())
        if not payload.get("correlation_id"):
            payload["correlation_id"] = f"api-{int(time.time() * 1000)}"

        result = self.orchestrator.ingest_message(payload)
        if not result.get("ok"):
            status = 400 if result.get("reason") == "schema_invalid" else 409
            return status, result
        if result.get("duplicate"):
            return 200, result
        return 202, result


def _maybe_json(body: bytes) -> Dict[str, Any]:
    if not body:
        return {}
    try:
        parsed = json.loads(body.decode("utf-8") or "{}")
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _reason_from(body: bytes) -> str:
    payload = _maybe_json(body)
    return str(payload.get("reason") or "operator")[:300]


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "ControllerAPI/1.0"

    # Injected by the server factory.
    api: ControllerAPI = None  # type: ignore
    token_provider: Callable[[], str] = staticmethod(controller_api_token)

    # -- logging: never emit headers, tokens or bodies -----------------

    def log_message(self, fmt, *args):  # noqa: D401 - BaseHTTPRequestHandler API
        logger.info(
            "controller_api %s %s -> %s (%s bytes)",
            getattr(self, "command", "-"),
            urlparse(getattr(self, "path", "")).path or "-",
            getattr(self, "_last_status", "-"),
            getattr(self, "_last_bytes", 0),
        )

    # -- helpers -------------------------------------------------------

    def _send(self, status: int, payload: Dict[str, Any]) -> None:
        data = _json_bytes(payload)
        self._last_status = status
        self._last_bytes = len(data)
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        try:
            self.wfile.write(data)
        except Exception:
            pass

    def _auth(self) -> bool:
        expected = self.token_provider() or ""
        if not expected:
            # Fail closed: no token configured means no service.
            self._send(503, {"ok": False, "error": "api_token_not_configured"})
            return False
        header = self.headers.get("authorization", "") or ""
        prefix = "Bearer "
        supplied = header[len(prefix):] if header.startswith(prefix) else ""
        if not supplied or not hmac.compare_digest(supplied, expected):
            self._send(401, {"ok": False, "error": "unauthorized"})
            return False
        return True

    def _read_body(self) -> Optional[bytes]:
        raw_length = self.headers.get("content-length", "0") or "0"
        try:
            length = int(raw_length)
        except ValueError:
            self._send(400, {"ok": False, "error": "invalid_content_length"})
            return None
        if length < 0:
            self._send(400, {"ok": False, "error": "invalid_content_length"})
            return None
        if length > MAX_BODY_BYTES:
            # Drain a bounded prefix so the client's send completes and the
            # 413 is delivered cleanly instead of being lost to a RST under load.
            to_drain = min(length, MAX_BODY_BYTES + 4096)
            remaining = to_drain
            while remaining > 0:
                chunk = self.rfile.read(min(65536, remaining))
                if not chunk:
                    break
                remaining -= len(chunk)
            self.close_connection = True
            self._send(413, {"ok": False, "error": "payload_too_large", "max_bytes": MAX_BODY_BYTES})
            return None
        if length == 0:
            return b""
        return self.rfile.read(length)

    def _dispatch(self, method: str) -> None:
        if not self._auth():
            return
        body = self._read_body()
        if body is None:
            return
        status, payload = self.api.handle(method, self.path, body)
        self._send(status, payload)

    def do_GET(self):  # noqa: N802 - BaseHTTPRequestHandler API
        self._dispatch("GET")

    def do_POST(self):  # noqa: N802 - BaseHTTPRequestHandler API
        self._dispatch("POST")

    def do_PUT(self):  # noqa: N802
        self._send(405, {"ok": False, "error": "method_not_allowed"})

    def do_DELETE(self):  # noqa: N802
        self._send(405, {"ok": False, "error": "method_not_allowed"})


def create_server(
    orchestrator,
    host: str = LOOPBACK_BIND,
    port: int = DEFAULT_PORT,
    token_provider: Optional[Callable[[], str]] = None,
) -> ThreadingHTTPServer:
    """Build (but do not start) a loopback-bound controller API server."""
    if host not in LOOPBACK_HOSTS:
        raise ControllerAPIError(f"host must be loopback ({', '.join(LOOPBACK_HOSTS)}); got {host!r}")

    api = ControllerAPI(orchestrator, token_provider=token_provider)
    provider = token_provider or controller_api_token

    handler = type(
        "BoundControllerHandler",
        (_Handler,),
        {"api": api, "token_provider": staticmethod(provider)},
    )
    server = ThreadingHTTPServer((host, port), handler)
    server.daemon_threads = True
    return server


def serve_forever(server: ThreadingHTTPServer) -> threading.Thread:
    """Run the server in a daemon thread (caller owns shutdown)."""
    thread = threading.Thread(target=server.serve_forever, name="controller-api", daemon=True)
    thread.start()
    return thread
