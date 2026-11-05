"""WP-430: MCP server adapter exposing the existing controller services.

ChatGPT (or any MCP client) connects via Streamable HTTP (JSON-RPC 2.0) and
invokes narrowly scoped tools that delegate to the existing
:class:`MissionOrchestrator` and :class:`BridgeDB`. No business logic is
duplicated; the MCP layer is a thin transport + schema + auth adapter.

Transport: stdlib ``http.server`` (no fastapi/uvicorn available in this venv).
Endpoint: ``POST /mcp`` (JSON-RPC 2.0). Loopback by default; fail-closed auth.

Tools:
  Read-only:  controller_health, get_task_status, get_execution_result,
              get_controller_capabilities
  Intake:     submit_chatgpt_task
  Approval:   approve_chatgpt_task
"""

import json
import logging
import os
import time
import uuid
from typing import Any, Dict, List, Optional

from .controller_api import MAX_BODY_BYTES, LOOPBACK_HOSTS, ControllerAPIError, create_server as _unused
from .controller_api import controller_api_token, LOOPBACK_BIND, DEFAULT_PORT

logger = logging.getLogger("opencode_bridge.mcp_server")

MCP_ENDPOINT = "/mcp"
MCP_PROTOCOL_VERSION = "2025-03-26"

# Tool schemas (JSON Schema, subset). These are the MCP tool definitions.
TOOL_DEFINITIONS: List[Dict[str, Any]] = [
    {
        "name": "controller_health",
        "description": "Read-only health check of the controller and its OpenCode provider.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "list_chatgpt_projects",
        "description": "List configured ChatGPT Projects (read-only).",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "get_chatgpt_project",
        "description": "Get details of a specific ChatGPT Project by key.",
        "inputSchema": {
            "type": "object",
            "properties": {"project_key": {"type": "string", "minLength": 1, "maxLength": 64}},
            "required": ["project_key"],
            "additionalProperties": False,
        },
    },
    {
        "name": "set_active_chatgpt_project",
        "description": "Set the active ChatGPT Project for observation (explicit, auditable).",
        "inputSchema": {
            "type": "object",
            "properties": {"project_key": {"type": "string", "minLength": 1, "maxLength": 64}},
            "required": ["project_key"],
            "additionalProperties": False,
        },
    },
    {
        "name": "discover_chatgpt_conversation",
        "description": "Discover the latest eligible conversation in the active ChatGPT Project (read-only).",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "read_chatgpt_messages",
        "description": "Read and persist messages from the active ChatGPT Project's latest conversation (read-only).",
        "inputSchema": {
            "type": "object",
            "properties": {"max_messages": {"type": "integer", "minimum": 1, "maximum": 50}},
            "additionalProperties": False,
        },
    },
    {
        "name": "get_chatgpt_observations",
        "description": "Retrieve persisted ChatGPT message observations (read-only).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_key": {"type": "string", "maxLength": 64},
                "conversation_id": {"type": "string", "maxLength": 128},
                "role": {"type": "string", "enum": ["user", "assistant"]},
                "limit": {"type": "integer", "minimum": 1, "maximum": 100},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "get_chatgpt_reader_state",
        "description": "Get the ChatGPT project reader state (last read, errors, polling status).",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "get_chatgpt_observer_status",
        "description": "Get the continuous observer status (read-only).",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "start_chatgpt_observer",
        "description": "Start the continuous read-only observer (explicit opt-in).",
        "inputSchema": {
            "type": "object",
            "properties": {"interval_seconds": {"type": "integer", "minimum": 5, "maximum": 3600}},
            "additionalProperties": False,
        },
    },
    {
        "name": "stop_chatgpt_observer",
        "description": "Stop the continuous read-only observer.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "acknowledge_chatgpt_message",
        "description": "Acknowledge a persisted ChatGPT observation (explicit operator action).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "observation_id": {"type": "string", "minLength": 1, "maxLength": 128},
                "acknowledged_by": {"type": "string", "minLength": 1, "maxLength": 120},
            },
            "required": ["observation_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "get_unread_chatgpt_messages",
        "description": "Get unread user messages from the active ChatGPT Project (read-only).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_key": {"type": "string", "maxLength": 64},
                "limit": {"type": "integer", "minimum": 1, "maximum": 100},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "get_chatgpt_message_history",
        "description": "Get edit history for a specific ChatGPT message (read-only).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "message_id": {"type": "string", "minLength": 1, "maxLength": 256},
                "project_key": {"type": "string", "maxLength": 64},
            },
            "required": ["message_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "get_controller_capabilities",
        "description": "Return the controller's capabilities and supported operations.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "get_task_status",
        "description": "Get the status of a task by task_id.",
        "inputSchema": {
            "type": "object",
            "properties": {"task_id": {"type": "string", "minLength": 1, "maxLength": 128}},
            "required": ["task_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "get_execution_result",
        "description": "Get the persisted execution result by execution_id or task_id.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "execution_id": {"type": "string", "minLength": 1, "maxLength": 128},
                "task_id": {"type": "string", "minLength": 1, "maxLength": 128},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "submit_chatgpt_task",
        "description": "Submit a task from ChatGPT. Persists task identity before execution. Requires approval for write tasks.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "message_id": {"type": "string", "minLength": 1, "maxLength": 256},
                "project_id": {"type": "string", "minLength": 1, "maxLength": 128},
                "conversation_id": {"type": "string", "minLength": 1, "maxLength": 128},
                "message_content": {"type": "string", "minLength": 1, "maxLength": 16000},
                "correlation_id": {"type": "string", "minLength": 1, "maxLength": 256},
                "repository": {"type": "string", "minLength": 1, "maxLength": 512},
                "branch": {"type": "string", "minLength": 1, "maxLength": 128},
            },
            "required": ["message_id", "project_id", "conversation_id", "message_content", "correlation_id", "repository", "branch"],
            "additionalProperties": False,
        },
    },
    {
        "name": "submit_research_task",
        "description": "Submit a read-only research task. No ChatGPT conversation identity required.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "minLength": 1, "maxLength": 40000},
                "idempotency_key": {"type": "string", "minLength": 1, "maxLength": 200},
                "timeout_seconds": {"type": "number", "minimum": 1, "maximum": 600},
                "max_results": {"type": "integer", "minimum": 1, "maximum": 50},
            },
            "required": ["prompt", "idempotency_key"],
            "additionalProperties": False,
        },
    },
    {
        "name": "get_research_task_status",
        "description": "Get status of a research task.",
        "inputSchema": {
            "type": "object",
            "properties": {"research_id": {"type": "string", "minLength": 1, "maxLength": 200}},
            "required": ["research_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "get_research_task_result",
        "description": "Get result of a completed research task.",
        "inputSchema": {
            "type": "object",
            "properties": {"research_id": {"type": "string", "minLength": 1, "maxLength": 200}},
            "required": ["research_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "approve_chatgpt_task",
        "description": "Approve a pending task. Requires explicit human authorization separate from submission.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "minLength": 1, "maxLength": 128},
                "approved_by": {"type": "string", "minLength": 1, "maxLength": 120},
                "reason": {"type": "string", "maxLength": 500},
            },
            "required": ["task_id", "approved_by"],
            "additionalProperties": False,
        },
    },
]


class MCPServer:
    """Thin MCP adapter over the existing MissionOrchestrator.

    ``orchestrator`` is the existing :class:`MissionOrchestrator` instance.
    ``token_provider`` is injectable for tests.
    """

    def __init__(self, orchestrator, token_provider=None, project_registry=None, project_reader=None,
                 observer=None, research_executor=None):
        self.orchestrator = orchestrator
        self._token_provider = token_provider or controller_api_token
        self.project_registry = project_registry
        self.project_reader = project_reader
        self.observer = observer
        self.research_executor = research_executor

    def _auth_ok(self, headers: dict) -> bool:
        expected = self._token_provider() or ""
        if not expected:
            return False
        auth = headers.get("authorization", "") or headers.get("Authorization", "")
        prefix = "Bearer "
        supplied = auth[len(prefix):] if auth.startswith(prefix) else ""
        import hmac
        return bool(supplied) and hmac.compare_digest(supplied, expected)

    # -- JSON-RPC dispatch ---------------------------------------------

    def handle_rpc(self, method: str, params: Any, req_id: Any) -> Dict[str, Any]:
        """Handle a single JSON-RPC 2.0 request. Returns a response dict."""
        try:
            if method == "initialize":
                return self._ok(req_id, {
                    "protocolVersion": MCP_PROTOCOL_VERSION,
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "opencode-controller", "version": "1.0.0"},
                })
            if method == "notifications/initialized":
                return None  # notification, no response
            if method == "tools/list":
                return self._ok(req_id, {"tools": TOOL_DEFINITIONS})
            if method == "tools/call":
                if not isinstance(params, dict):
                    return self._err(req_id, -32602, "params must be an object")
                name = params.get("name")
                args = params.get("arguments") or {}
                if not isinstance(args, dict):
                    return self._err(req_id, -32602, "arguments must be an object")
                result = self._call_tool(name, args)
                return self._ok(req_id, {
                    "content": [{"type": "text", "text": json.dumps(result, default=str)}],
                    "isError": not result.get("ok", True) if isinstance(result, dict) else False,
                })
            return self._err(req_id, -32601, f"method not found: {method}")
        except Exception as exc:
            logger.error("mcp handler error: %s", type(exc).__name__)
            return self._err(req_id, -32603, "internal error")

    def _call_tool(self, name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        o = self.orchestrator
        if name == "controller_health":
            try:
                report = o.status_report()
                return {"ok": True, "status": report}
            except Exception as exc:
                return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

        if name == "get_controller_capabilities":
            return {
                "ok": True,
                "capabilities": {
                    "tools": [t["name"] for t in TOOL_DEFINITIONS],
                    "execution": "opencode_api",
                    "persistence": "sqlite",
                    "governance": True,
                    "approval_required_for_writes": True,
                },
            }

        if name == "get_task_status":
            task_id = args.get("task_id", "")
            if not task_id:
                return {"ok": False, "reason": "task_id required"}
            task = o.db.get_dev_task(task_id)
            if not task:
                return {"ok": False, "reason": "task_not_found"}
            execution = o.db.get_execution_for_task(task_id)
            return {
                "ok": True,
                "task_id": task_id,
                "task_status": task.get("task_status"),
                "execution_id": execution.get("execution_id") if execution else None,
                "execution_status": execution.get("execution_status") if execution else None,
                "state": o.state().value,
            }

        if name == "get_execution_result":
            execution_id = args.get("execution_id")
            task_id = args.get("task_id")
            execution = None
            if execution_id:
                execution = o.db.get_execution(execution_id)
            elif task_id:
                execution = o.db.get_execution_for_task(task_id)
            if not execution:
                return {"ok": False, "reason": "execution_not_found"}
            return {
                "ok": True,
                "execution_id": execution.get("execution_id"),
                "task_id": execution.get("task_id"),
                "opencode_session_id": execution.get("opencode_session_id"),
                "execution_status": execution.get("execution_status"),
                "completion_status": execution.get("completion_status"),
                "execution_output": execution.get("execution_output"),
                "changed_files": execution.get("changed_files", []),
                "test_results": execution.get("test_results", {}),
                "verification_evidence": execution.get("verification_evidence", {}),
                "started_at": execution.get("started_at"),
                "completed_at": execution.get("completed_at"),
                "error": execution.get("error"),
            }

        if name == "submit_chatgpt_task":
            # Build an inbound message from the structured args (provenance required).
            from .contracts import inbound_message
            from .chatgpt_interface import PALMISTRY_PROJECT_ID

            message_id = args.get("message_id", "")
            project_id = args.get("project_id", "")
            conversation_id = args.get("conversation_id", "")
            message_content = args.get("message_content", "")
            correlation_id = args.get("correlation_id", "")
            repository = args.get("repository", "")
            branch = args.get("branch", "")

            if not all([message_id, project_id, conversation_id, message_content, correlation_id, repository, branch]):
                return {"ok": False, "reason": "missing_required_fields"}

            # Provenance: repository must be in allowed list.
            if o.allowed_repositories and repository not in o.allowed_repositories:
                return {"ok": False, "reason": "repository_not_allowed", "repository": repository}

            # Branch must match.
            from .config import EXPECTED_BRANCH
            if branch != EXPECTED_BRANCH and branch != o.target_branch:
                return {"ok": False, "reason": "branch_not_allowed", "branch": branch}

            payload = inbound_message(
                message_id=message_id,
                project_id=project_id,
                conversation_id=conversation_id,
                message_content=message_content,
                correlation_id=correlation_id,
                received_at=time.time(),
            )
            # Override target repository/branch in the mission context is not allowed;
            # the task targets the mission's configured workspace.
            ingest = o.ingest_message(payload)
            if not ingest.get("ok"):
                return {"ok": False, "reason": "ingest_failed", "details": ingest}

            create = o.create_task(payload)
            if not create.get("ok"):
                return {"ok": False, "reason": create.get("reason", "task_creation_failed"), "details": create}

            task_id = create["task_id"]
            task = o.db.get_dev_task(task_id)
            approval_required = task.get("task_status") == "awaiting_approval" or create.get("requires_approval", False)

            return {
                "ok": True,
                "task_id": task_id,
                "duplicate": create.get("duplicate", False),
                "approval_required": approval_required,
                "approval_reason": (task.get("approval_requirements") or [None])[0] if approval_required else None,
                "state": o.state().value,
                "task_status": task.get("task_status"),
            }

        if name == "approve_chatgpt_task":
            task_id = args.get("task_id", "")
            approved_by = args.get("approved_by", "")
            reason = args.get("reason", "")
            if not task_id or not approved_by:
                return {"ok": False, "reason": "task_id and approved_by required"}

            # Revalidate governance before approving.
            task = o.db.get_dev_task(task_id)
            if not task:
                return {"ok": False, "reason": "task_not_found"}
            if task.get("task_status") not in ("awaiting_approval", "validated"):
                return {"ok": False, "reason": "task_not_approvable", "task_status": task.get("task_status")}

            result = o.approve_task(task_id, approved_by=approved_by, reason=reason)
            return result

        # --- WP-431B: read-only ChatGPT project tools ---

        if name == "list_chatgpt_projects":
            if self.project_registry is None:
                return {"ok": False, "reason": "project_registry not configured"}
            projects = self.project_registry.list_projects()
            return {"ok": True, "projects": projects, "count": len(projects)}

        if name == "get_chatgpt_project":
            if self.project_registry is None:
                return {"ok": False, "reason": "project_registry not configured"}
            pk = args.get("project_key", "")
            if not pk:
                return {"ok": False, "reason": "project_key required"}
            proj = self.project_registry.get_project(pk)
            if not proj:
                return {"ok": False, "reason": "project_not_found"}
            return {"ok": True, "project": proj}

        if name == "set_active_chatgpt_project":
            if self.project_registry is None:
                return {"ok": False, "reason": "project_registry not configured"}
            pk = args.get("project_key", "")
            if not pk:
                return {"ok": False, "reason": "project_key required"}
            try:
                self.project_registry.set_active_project(pk)
                if self.project_reader is not None:
                    self.project_reader.project_key = pk
                return {"ok": True, "active_project_key": pk}
            except ValueError as exc:
                return {"ok": False, "reason": str(exc)}

        if name == "discover_chatgpt_conversation":
            if self.project_reader is None:
                return {"ok": False, "reason": "project_reader not configured"}
            return self.project_reader.discover_conversation()

        if name == "read_chatgpt_messages":
            if self.project_reader is None:
                return {"ok": False, "reason": "project_reader not configured"}
            max_msgs = args.get("max_messages", 10)
            return self.project_reader.read_messages(max_messages=max_msgs)

        if name == "get_chatgpt_observations":
            if self.project_registry is None:
                return {"ok": False, "reason": "project_registry not configured"}
            pk = args.get("project_key")
            cid = args.get("conversation_id")
            role = args.get("role")
            limit = args.get("limit", 50)
            obs = self.project_registry.get_observations(project_key=pk, conversation_id=cid, role=role, limit=limit)
            return {"ok": True, "observations": obs, "count": len(obs)}

        if name == "get_chatgpt_reader_state":
            if self.project_registry is None:
                return {"ok": False, "reason": "project_registry not configured"}
            state = self.project_registry.get_state()
            proj = None
            pk = self.project_registry.get_active_project_key()
            if pk:
                proj = self.project_registry.get_project(pk)
            return {"ok": True, "state": state, "active_project": proj}

        # --- WP-433: observer and acknowledgement tools ---

        if name == "get_chatgpt_observer_status":
            if self.project_registry is None:
                return {"ok": False, "reason": "project_registry not configured"}
            state = self.project_registry.get_observer_state()
            running = self.observer.is_running() if self.observer else False
            conn_info = self.observer.get_connection_info() if self.observer else {}
            return {"ok": True, "observer_state": state, "is_running": running, "connection": conn_info}

        if name == "start_chatgpt_observer":
            if self.observer is None:
                return {"ok": False, "reason": "observer not configured"}
            interval = args.get("interval_seconds")
            if interval is not None:
                self.observer.interval_seconds = max(5, int(interval))
            return self.observer.start()

        if name == "stop_chatgpt_observer":
            if self.observer is None:
                return {"ok": False, "reason": "observer not configured"}
            return self.observer.stop()

        if name == "acknowledge_chatgpt_message":
            if self.project_registry is None:
                return {"ok": False, "reason": "project_registry not configured"}
            obs_id = args.get("observation_id", "")
            if not obs_id:
                return {"ok": False, "reason": "observation_id required"}
            acked_by = args.get("acknowledged_by", "operator")
            ok = self.project_registry.acknowledge_observation(obs_id, acked_by)
            return {"ok": ok, "observation_id": obs_id, "acknowledged": ok}

        if name == "get_unread_chatgpt_messages":
            if self.project_registry is None:
                return {"ok": False, "reason": "project_registry not configured"}
            pk = args.get("project_key")
            limit = args.get("limit", 50)
            msgs = self.project_registry.get_unread_messages(project_key=pk, limit=limit)
            return {"ok": True, "messages": msgs, "count": len(msgs)}

        if name == "get_chatgpt_message_history":
            if self.project_registry is None:
                return {"ok": False, "reason": "project_registry not configured"}
            mid = args.get("message_id", "")
            if not mid:
                return {"ok": False, "reason": "message_id required"}
            pk = args.get("project_key")
            history = self.project_registry.get_message_history(mid, project_key=pk)
            return {"ok": True, "history": history, "count": len(history)}

        if name == "submit_research_task":
            import uuid
            from .contracts import research_task, validate_research_task
            prompt = args.get("prompt", "")
            idempotency_key = args.get("idempotency_key", "")
            timeout_seconds = args.get("timeout_seconds", 120.0)
            max_results = args.get("max_results", 10)
            if not prompt or not idempotency_key:
                return {"ok": False, "reason": "prompt and idempotency_key required"}
            existing = o.db.get_research_task_by_idempotency(idempotency_key)
            if existing:
                return {"ok": True, "research_id": existing["research_id"], "duplicate": True, "status": existing["status"]}
            research_id = "res-" + uuid.uuid4().hex[:12]
            task = research_task(
                research_id=research_id,
                idempotency_key=idempotency_key,
                prompt=prompt,
                read_only=True,
                timeout_seconds=float(timeout_seconds),
                max_results=int(max_results),
                created_at=time.time(),
                status="pending",
            )
            ok, errors = validate_research_task(task)
            if not ok:
                return {"ok": False, "reason": "invalid_task", "errors": errors}
            inserted = o.db.insert_research_task(task)
            if not inserted:
                existing = o.db.get_research_task_by_idempotency(idempotency_key)
                if existing:
                    return {"ok": True, "research_id": existing["research_id"], "duplicate": True, "status": existing["status"]}
                return {"ok": False, "reason": "insert_failed"}
            # Optional auto-execution (off by default; tests invoke the executor directly).
            if self.research_executor is not None and os.environ.get("RESEARCH_AUTO_EXECUTE", "").strip().lower() in ("1", "true", "yes"):
                import threading
                threading.Thread(
                    target=self.research_executor.execute, args=(research_id,), daemon=True,
                    name=f"research-{research_id}",
                ).start()
            return {"ok": True, "research_id": research_id, "duplicate": False, "status": "pending"}

        if name == "get_research_task_status":
            research_id = args.get("research_id", "")
            if not research_id:
                return {"ok": False, "reason": "research_id required"}
            t = o.db.get_research_task(research_id)
            if not t:
                return {"ok": False, "reason": "not_found"}
            return {"ok": True, "research_id": research_id, "status": t["status"],
                    "created_at": t["created_at"], "started_at": t["started_at"],
                    "completed_at": t["completed_at"], "error": t["error"]}

        if name == "get_research_task_result":
            research_id = args.get("research_id", "")
            if not research_id:
                return {"ok": False, "reason": "research_id required"}
            t = o.db.get_research_task(research_id)
            if not t:
                return {"ok": False, "reason": "not_found"}
            result = None
            if t.get("result_json"):
                try:
                    result = json.loads(t["result_json"])
                except Exception:
                    result = {"raw": t["result_json"]}
            return {"ok": True, "research_id": research_id, "status": t["status"],
                    "session_id": t["session_id"], "result": result, "error": t["error"]}

        return {"ok": False, "reason": f"unknown tool: {name}"}

    @staticmethod
    def _ok(req_id, result):
        return {"jsonrpc": "2.0", "id": req_id, "result": result}

    @staticmethod
    def _err(req_id, code, message):
        return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}


class MCPServerHTTP:
    """HTTP wrapper around MCPServer for Streamable HTTP transport."""

    def __init__(self, mcp_server: MCPServer, host: str = "127.0.0.1", port: int = 8799):
        if host not in ("127.0.0.1", "localhost", "::1"):
            raise ControllerAPIError(f"host must be loopback; got {host!r}")
        self.mcp = mcp_server
        self.host = host
        self.port = port

    def create_http_server(self):
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        mcp = self.mcp

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, fmt, *args):
                logger.info("mcp %s %s", getattr(self, "command", "-"), getattr(self, "path", "-"))

            def _send(self, status, payload):
                data = json.dumps(payload, default=str).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(data)

            def do_POST(self):
                if self.path != MCP_ENDPOINT:
                    # Drain body before 404 to avoid connection reset under load.
                    try:
                        length = int(self.headers.get("Content-Length", "0") or "0")
                        if 0 < length <= MAX_BODY_BYTES:
                            self.rfile.read(length)
                    except Exception:
                        pass
                    self._send(404, {"error": "not_found"})
                    return
                # Auth
                if not mcp._auth_ok({k: v for k, v in self.headers.items()}):
                    self._send(401, {"error": "unauthorized"})
                    return
                # Read body
                length = int(self.headers.get("Content-Length", "0") or "0")
                if length > MAX_BODY_BYTES:
                    to_drain = min(length, MAX_BODY_BYTES + 4096)
                    remaining = to_drain
                    while remaining > 0:
                        chunk = self.rfile.read(min(65536, remaining))
                        if not chunk:
                            break
                        remaining -= len(chunk)
                    self.close_connection = True
                    self._send(413, {"error": "payload_too_large"})
                    return
                body = self.rfile.read(length) if length else b""
                try:
                    req = json.loads(body.decode("utf-8") or "{}")
                except (json.JSONDecodeError, UnicodeDecodeError):
                    self._send(400, {"error": "invalid_json"})
                    return
                if not isinstance(req, dict):
                    self._send(400, {"error": "invalid_request"})
                    return

                # Handle single request or batch
                if isinstance(req, list):
                    responses = []
                    for r in req:
                        resp = self._handle_one(r)
                        if resp is not None:
                            responses.append(resp)
                    if responses:
                        self._send(200, responses)
                    else:
                        self._send(204, {})
                    return
                resp = self._handle_one(req)
                if resp is None:
                    self._send(204, {})
                else:
                    self._send(200, resp)

            def _handle_one(self, req):
                if not isinstance(req, dict):
                    return {"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "invalid request"}}
                jsonrpc = req.get("jsonrpc")
                method = req.get("method")
                params = req.get("params")
                req_id = req.get("id")
                if jsonrpc != "2.0" or not method:
                    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32600, "message": "invalid request"}}
                # Notification (no id) -> no response
                if req_id is None and method.startswith("notifications/"):
                    mcp.handle_rpc(method, params, None)
                    return None
                return mcp.handle_rpc(method, params, req_id)

            def do_GET(self):
                if self.path == "/health":
                    self._send(200, {"ok": True, "service": "mcp_server"})
                else:
                    self._send(404, {"error": "not_found"})

        server = ThreadingHTTPServer((self.host, self.port), Handler)
        server.daemon_threads = True
        return server
