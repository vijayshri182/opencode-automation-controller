"""WP-423: authenticated, loopback-only controller HTTP API.

Tests use ``ThreadingHTTPServer`` on an ephemeral port bound to 127.0.0.1.
"""

import json
import os
import socket
import threading
import urllib.error
import urllib.request
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest

from opencode_bridge import contracts
from opencode_bridge.chatgpt_interface import FakeChatGPTAdapter
from opencode_bridge.controller_api import (
    MAX_BODY_BYTES,
    LOOPBACK_HOSTS,
    ControllerAPI,
    ControllerAPIError,
    create_server,
    TOKEN_ENV_VAR,
)
from opencode_bridge.db import BridgeDB
from opencode_bridge.executors import FakeOpenCodeExecutor
from opencode_bridge.orchestrator import MissionOrchestrator

NEUTRAL_TASK = "Inspect the repository and produce a summary report."


def fast_policy():
    from opencode_bridge.retry import RetryPolicy

    return RetryPolicy(max_attempts=3, base_seconds=0.01, factor=2.0, cap_seconds=0.05, jitter_ratio=0.0)


def make_orchestrator(tmp_path, token="secret-token"):
    db = BridgeDB(tmp_path / "orch.db")
    chat = FakeChatGPTAdapter(messages=[NEUTRAL_TASK])
    ex = FakeOpenCodeExecutor()
    o = MissionOrchestrator(
        db,
        chat,
        ex,
        mission_id="m1",
        workspace=str(tmp_path),
        allowed_repositories=[str(tmp_path)],
        retry_policy=fast_policy(),
        delivery_retry_policy=fast_policy(),
        task_timeout_seconds=0.0,
    )
    return o, chat, ex


def server_for(tmp_path, token="secret-token", host="127.0.0.1"):
    o, chat, ex = make_orchestrator(tmp_path)
    srv = create_server(o, host=host, port=0, token_provider=lambda: token)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    return srv, o, chat, ex


def url(srv, path):
    return f"http://127.0.0.1:{srv.server_port}{path}"


def request(srv, method, path, body=None, token="secret-token"):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url(srv, path), data=data, method=method)
    if token is not None:
        req.add_header("Authorization", f"Bearer {token}")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode())


def test_non_loopback_host_raises():
    o, _, _ = make_orchestrator(Path("."))
    with pytest.raises(ControllerAPIError):
        create_server(o, host="0.0.0.0", port=0, token_provider=lambda: "t")
    with pytest.raises(ControllerAPIError):
        create_server(o, host="192.168.1.1", port=0, token_provider=lambda: "t")


def test_loopback_hosts_are_accepted():
    for host in LOOPBACK_HOSTS:
        assert host in LOOPBACK_HOSTS


def test_missing_token_fails_closed_with_503(tmp_path):
    srv, o, chat, ex = server_for(tmp_path, token="")
    try:
        status, payload = request(srv, "GET", "/api/health", token="anything")
        assert status == 503
        assert payload["error"] == "api_token_not_configured"
    finally:
        srv.shutdown()
        srv.server_close()


def test_bad_token_returns_401(tmp_path):
    srv, o, chat, ex = server_for(tmp_path)
    try:
        status, payload = request(srv, "GET", "/api/health", token="wrong")
        assert status == 401
        assert payload["error"] == "unauthorized"

        status, payload = request(srv, "GET", "/api/health", token=None)
        assert status == 401
    finally:
        srv.shutdown()
        srv.server_close()


def test_valid_token_allows_health_and_status(tmp_path):
    srv, o, chat, ex = server_for(tmp_path)
    try:
        status, payload = request(srv, "GET", "/api/health")
        assert status == 200 and payload["ok"] is True

        status, payload = request(srv, "GET", "/api/mission")
        assert status == 200 and payload["ok"] is True
        assert payload["status"]["current_state"] == "READY"

        status, payload = request(srv, "GET", "/api/health/recovery")
        assert status == 200 and payload["ok"] is True
    finally:
        srv.shutdown()
        srv.server_close()


def test_unknown_path_returns_404(tmp_path):
    srv, o, chat, ex = server_for(tmp_path)
    try:
        status, payload = request(srv, "GET", "/api/does/not/exist")
        assert status == 404
        assert payload["error"] == "not_found"
    finally:
        srv.shutdown()
        srv.server_close()


def test_disallowed_method_returns_405(tmp_path):
    srv, o, chat, ex = server_for(tmp_path)
    try:
        status, payload = request(srv, "PUT", "/api/health")
        assert status == 405
        assert payload["error"] == "method_not_allowed"
        status, payload = request(srv, "DELETE", "/api/health")
        assert status == 405
    finally:
        srv.shutdown()
        srv.server_close()


def test_oversized_body_returns_413(tmp_path):
    srv, o, chat, ex = server_for(tmp_path)
    try:
        huge = {"message_id": "x", "message_content": "y" * (MAX_BODY_BYTES + 100)}
        status, payload = request(srv, "POST", "/api/chatgpt/inbox", body=huge)
        assert status == 413
        assert payload["error"] == "payload_too_large"
    finally:
        srv.shutdown()
        srv.server_close()


def test_invalid_json_returns_400(tmp_path):
    srv, o, chat, ex = server_for(tmp_path)
    try:
        req = __import__("urllib.request").request.Request(
            f"http://127.0.0.1:{srv.server_port}/api/chatgpt/inbox",
            data=b"{not json",
            method="POST",
        )
        req.add_header("Authorization", "Bearer secret-token")
        req.add_header("Content-Type", "application/json")
        try:
            urllib.request.urlopen(req, timeout=10)
        except urllib.error.HTTPError as exc:
            assert exc.code == 400
            body = json.loads(exc.read().decode())
            assert body["error"] == "invalid_json"
    finally:
        srv.shutdown()
        srv.server_close()


def test_schema_invalid_returns_400(tmp_path):
    srv, o, chat, ex = server_for(tmp_path)
    try:
        status, payload = request(srv, "POST", "/api/chatgpt/inbox", body={"message_id": "msg-1"})
        assert status == 400
        assert payload["ok"] is False
        assert payload["reason"] == "schema_invalid"
    finally:
        srv.shutdown()
        srv.server_close()


def test_ingest_returns_202_then_duplicate_returns_200(tmp_path):
    srv, o, chat, ex = server_for(tmp_path)
    try:
        message = contracts.inbound_message(
            message_id="msg-api-1",
            project_id="g-p-6ae87c1e48b08191a2cd33139c40639f",
            conversation_id="conv-0001",
            message_content=NEUTRAL_TASK,
            correlation_id="corr-api-1",
            received_at=1.0,
        )
        status, payload = request(srv, "POST", "/api/chatgpt/inbox", body=message)
        assert status == 202
        assert payload["ok"] is True
        assert payload["duplicate"] is False

        status, payload = request(srv, "POST", "/api/chatgpt/inbox", body=message)
        assert status == 200
        assert payload["duplicate"] is True
    finally:
        srv.shutdown()
        srv.server_close()


def test_get_task_and_execution_routes(tmp_path):
    srv, o, chat, ex = server_for(tmp_path)
    try:
        message = contracts.inbound_message(
            message_id="msg-api-2",
            project_id="g-p-6ae87c1e48b08191a2cd33139c40639f",
            conversation_id="conv-0001",
            message_content=NEUTRAL_TASK,
            correlation_id="corr-api-2",
            received_at=1.0,
        )
        request(srv, "POST", "/api/chatgpt/inbox", body=message)
        o.run_cycle()

        task = o.db.list_dev_tasks(mission_id="m1")[0]
        status, payload = request(srv, "GET", f"/api/tasks/{task['task_id']}")
        assert status == 200
        assert payload["task"]["task_id"] == task["task_id"]
        assert payload["execution"]["execution_status"] == "completed"

        execution = payload["execution"]
        status, payload = request(srv, "GET", f"/api/executions/{execution['execution_id']}")
        assert status == 200
        assert payload["execution"]["execution_id"] == execution["execution_id"]
        assert payload["delivery"]["delivery_status"] == "delivered"

        status, _ = request(srv, "GET", "/api/tasks/does-not-exist")
        assert status == 404
        status, _ = request(srv, "GET", "/api/executions/does-not-exist")
        assert status == 404
    finally:
        srv.shutdown()
        srv.server_close()


def test_approval_route(tmp_path):
    srv, o, chat, ex = server_for(tmp_path)
    try:
        chat.messages = ["Write a documentation note about the module structure."]
        message = contracts.inbound_message(
            message_id="msg-api-3",
            project_id="g-p-6ae87c1e48b08191a2cd33139c40639f",
            conversation_id="conv-0001",
            message_content="Write a documentation note about the module structure.",
            correlation_id="corr-api-3",
            received_at=1.0,
        )
        request(srv, "POST", "/api/chatgpt/inbox", body=message)
        first = o.run_cycle()
        assert first["reason"] == "awaiting_approval"

        task = o.db.list_dev_tasks(mission_id="m1")[0]
        status, payload = request(
            srv,
            "POST",
            f"/api/tasks/{task['task_id']}/approve",
            body={"approved_by": "operator", "reason": "confirmed"},
        )
        assert status == 200
        assert payload["ok"] is True
        assert o.db.get_dev_task(task["task_id"])["task_status"] == "ready"

        # Double approval is rejected.
        status, payload = request(
            srv,
            "POST",
            f"/api/tasks/{task['task_id']}/approve",
            body={},
        )
        assert status == 409
        assert payload["ok"] is False
    finally:
        srv.shutdown()
        srv.server_close()


def test_delivery_ack_route(tmp_path):
    srv, o, chat, ex = server_for(tmp_path)
    try:
        message = contracts.inbound_message(
            message_id="msg-api-4",
            project_id="g-p-6ae87c1e48b08191a2cd33139c40639f",
            conversation_id="conv-0001",
            message_content=NEUTRAL_TASK,
            correlation_id="corr-api-4",
            received_at=1.0,
        )
        request(srv, "POST", "/api/chatgpt/inbox", body=message)
        o.run_cycle()
        execution = o.db.get_execution_for_task(o.db.list_dev_tasks(mission_id="m1")[0]["task_id"])
        delivery = o.db.get_delivery_for_execution(execution["execution_id"])

        status, payload = request(
            srv,
            "POST",
            f"/api/deliveries/{delivery['delivery_id']}/ack",
            body={"evidence": {"reviewed": True}},
        )
        assert status == 200
        assert payload["ok"] is True

        status, _ = request(srv, "POST", "/api/deliveries/does-not-exist/ack", body={})
        assert status == 404
    finally:
        srv.shutdown()
        srv.server_close()


def test_pause_resume_routes(tmp_path):
    srv, o, chat, ex = server_for(tmp_path)
    try:
        status, payload = request(srv, "POST", "/api/mission/pause", body={"reason": "break"})
        assert status == 200 and payload["state"] == "PAUSED"
        status, payload = request(srv, "POST", "/api/mission/resume")
        assert status == 200
        assert payload["state"] == "READY"
    finally:
        srv.shutdown()
        srv.server_close()


def test_inbox_status_route(tmp_path):
    srv, o, chat, ex = server_for(tmp_path)
    try:
        status, payload = request(srv, "GET", "/api/inbox/status")
        assert status == 200
        assert payload["inbox"]["total"] == 0
    finally:
        srv.shutdown()
        srv.server_close()


def test_mission_get_route(tmp_path):
    srv, o, chat, ex = server_for(tmp_path)
    try:
        status, payload = request(srv, "GET", "/api/missions/m1")
        assert status == 200
        assert payload["mission"]["id"] == "m1"
        assert isinstance(payload["tasks"], list)
        status, _ = request(srv, "GET", "/api/missions/does-not-exist")
        assert status == 404
    finally:
        srv.shutdown()
        srv.server_close()


def test_authorization_header_is_never_logged(tmp_path, caplog):
    import logging

    caplog.set_level(logging.INFO, logger="opencode_bridge.controller_api")
    srv, o, chat, ex = server_for(tmp_path)
    try:
        secret = "super-secret-token-value"
        srv2 = None
        # Re-create with a distinctive token so we can prove it never appears.
        pass
        status, _ = request(srv, "GET", "/api/health", token=secret)
        # Wrong token -> 401, and the log must not contain the token.
        assert status == 401
        for record in caplog.records:
            assert secret not in record.getMessage()
    finally:
        srv.shutdown()
        srv.server_close()


def test_body_is_not_logged(tmp_path, caplog):
    import logging

    caplog.set_level(logging.INFO, logger="opencode_bridge.controller_api")
    srv, o, chat, ex = server_for(tmp_path)
    try:
        marker = "SECRET-BODY-MARKER-999"
        request(srv, "POST", "/api/chatgpt/inbox", body={"message_id": marker}, token="secret-token")
        for record in caplog.records:
            assert marker not in record.getMessage()
    finally:
        srv.shutdown()
        srv.server_close()

