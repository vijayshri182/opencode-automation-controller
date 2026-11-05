"""WP-433: Continuous ChatGPT conversation observer â focused tests.

Uses deterministic doubles (MockBrowserAdapter). No live browser, no network.
"""

import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest

from opencode_bridge.browser_automation import MockBrowserAdapter
from opencode_bridge.chatgpt_interface import PALMISTRY_PROJECT_ID, PALMISTRY_PROJECT_URL
from opencode_bridge.chatgpt_project_reader import (
    ChatGPTProjectRegistry,
    ChatGPTProjectReader,
)
from opencode_bridge.chatgpt_observer import ChatGPTObserver
from opencode_bridge.db import BridgeDB
from opencode_bridge.mcp_server import MCPServer


def make_registry(tmp_path):
    db = BridgeDB(tmp_path / "orch.db")
    return ChatGPTProjectRegistry(db), db


def make_browser():
    return MockBrowserAdapter()


def make_observer(tmp_path):
    reg, db = make_registry(tmp_path)
    browser = make_browser()
    browser.select_latest_project_conversation = lambda url, excluded=None: {
        "title": "Test Conv", "conversation_id": "conv-123", "clicked": True,
        "reason": "newest_eligible", "candidates": ["Test Conv"],
    }
    browser.discover_project_conversations = lambda url: [
        {"title": "Test Conv", "conversation_id": "conv-123", "href": "/c/conv-123", "index": 0},
    ]
    browser.get_page_text = lambda: "You said: Hello world\nChatGPT said: Hi\n"
    browser.conversation_health = lambda: {
        "browser_connected": True, "authenticated": True,
        "conversation_loaded": True, "readable": True, "writeable": True,
    }
    from opencode_bridge.chatgpt_interface import PlaywrightChatGPTAdapter
    adapter = PlaywrightChatGPTAdapter(browser)
    reader = ChatGPTProjectReader(adapter, reg, "palmistry")
    observer = ChatGPTObserver(reader, reg, interval_seconds=5)
    return observer, reg, db, reader, browser


# --- observer lifecycle -------------------------------------------------


def test_observer_disabled_by_default(tmp_path):
    observer, reg, db, reader, browser = make_observer(tmp_path)
    assert observer.status == "STOPPED"
    assert reg.get_observer_state()["status"] == "STOPPED"


def test_observer_start_stop(tmp_path):
    observer, reg, db, reader, browser = make_observer(tmp_path)
    result = observer.start()
    assert result["ok"] is True
    assert result["status"] == "RUNNING"
    assert observer.is_running() is True
    assert reg.get_observer_state()["status"] == "RUNNING"

    result = observer.stop()
    assert result["ok"] is True
    assert result["status"] == "STOPPED"
    assert observer.is_running() is False
    assert reg.get_observer_state()["status"] == "STOPPED"


def test_observer_double_start_rejected(tmp_path):
    observer, reg, db, reader, browser = make_observer(tmp_path)
    observer.start()
    result = observer.start()
    assert result["ok"] is False
    assert result["reason"] == "already_running"
    observer.stop()


def test_observer_stop_when_not_running(tmp_path):
    observer, reg, db, reader, browser = make_observer(tmp_path)
    result = observer.stop()
    assert result["ok"] is True
    assert result["was_running"] is False


def test_observer_polling_persists_messages(tmp_path):
    observer, reg, db, reader, browser = make_observer(tmp_path)
    observer.start()
    # Wait for at least one poll
    import time
    time.sleep(7)
    observer.stop()
    obs = reg.get_observations(project_key="palmistry")
    assert len(obs) >= 1
    state = reg.get_observer_state()
    assert state["poll_count"] >= 1
    assert state["last_poll_at"] is not None


def test_observer_no_duplicate_on_repeat_poll(tmp_path):
    observer, reg, db, reader, browser = make_observer(tmp_path)
    observer.start()
    import time
    time.sleep(7)
    observer.stop()
    obs1 = reg.get_observations(project_key="palmistry")
    count1 = len(obs1)
    # Start again and poll
    observer.start()
    time.sleep(7)
    observer.stop()
    obs2 = reg.get_observations(project_key="palmistry")
    assert len(obs2) == count1  # no new duplicates


def test_observer_start_blocked_no_project(tmp_path):
    reg, db = make_registry(tmp_path)
    # Clear active project
    with db._lock:
        with __import__("contextlib").closing(db._connect()) as conn:
            conn.execute("UPDATE chatgpt_project_state SET active_project_key=NULL WHERE id=1")
            conn.commit()
    browser = make_browser()
    from opencode_bridge.chatgpt_interface import PlaywrightChatGPTAdapter
    adapter = PlaywrightChatGPTAdapter(browser)
    reader = ChatGPTProjectReader(adapter, reg, None)
    reader.project_key = None
    observer = ChatGPTObserver(reader, reg, interval_seconds=5)
    result = observer.start()
    assert result["ok"] is False


# --- acknowledgement ----------------------------------------------------


def test_acknowledge_observation():
    reg, db = make_registry(Path(tempfile.mkdtemp()))
    result = reg.record_observation("palmistry", "conv-1", "Test", "msg-1", "user", "Hello")
    obs = reg.get_observations(project_key="palmistry")[0]
    acked = reg.acknowledge_observation(obs["observation_id"], "operator")
    assert acked is True
    unread = reg.get_unread_messages("palmistry")
    assert len(unread) == 0


def test_unread_messages():
    reg, db = make_registry(Path(tempfile.mkdtemp()))
    reg.record_observation("palmistry", "conv-1", "Test", "msg-1", "user", "Hello")
    reg.record_observation("palmistry", "conv-1", "Test", "msg-2", "assistant", "Hi")
    unread = reg.get_unread_messages("palmistry")
    assert len(unread) == 1
    assert unread[0]["role"] == "user"


def test_message_history():
    reg, db = make_registry(Path(tempfile.mkdtemp()))
    reg.record_observation("palmistry", "conv-1", "Test", "msg-1", "user", "Hello")
    reg.record_observation("palmistry", "conv-1", "Test", "msg-1", "user", "Hello edited")
    history = reg.get_message_history("msg-1", "palmistry")
    assert len(history) == 2


def test_observer_state_persisted(tmp_path):
    observer, reg, db, reader, browser = make_observer(tmp_path)
    observer.start()
    import time
    time.sleep(6)
    observer.stop()
    # Verify state persisted
    state = reg.get_observer_state()
    assert state["status"] == "STOPPED"
    assert state["poll_count"] >= 1
    assert state["last_poll_at"] is not None


# --- mcp integration ----------------------------------------------------


def test_mcp_observer_status():
    import tempfile
    from pathlib import Path
    from opencode_bridge.mcp_server import MCPServer
    db = BridgeDB(Path(tempfile.mkdtemp()) / "orch.db")
    from opencode_bridge.chatgpt_interface import FakeChatGPTAdapter
    from opencode_bridge.executors import FakeOpenCodeExecutor
    from opencode_bridge.orchestrator import MissionOrchestrator
    from opencode_bridge.retry import RetryPolicy
    from opencode_bridge.db import BridgeDB as BDB
    reg = ChatGPTProjectRegistry(db)
    browser = make_browser()
    from opencode_bridge.chatgpt_interface import PlaywrightChatGPTAdapter
    adapter = PlaywrightChatGPTAdapter(browser)
    reader = ChatGPTProjectReader(adapter, reg, "palmistry")
    chat = FakeChatGPTAdapter(messages=[])
    ex = FakeOpenCodeExecutor()
    o = MissionOrchestrator(db, chat, ex, mission_id="m1", workspace=str(Path(tempfile.mkdtemp())),
                            allowed_repositories=[], retry_policy=RetryPolicy(max_attempts=1, base_seconds=0.01),
                            delivery_retry_policy=RetryPolicy(max_attempts=1, base_seconds=0.01), task_timeout_seconds=0.0)
    observer = ChatGPTObserver(reader, reg, interval_seconds=10)
    mcp = MCPServer(o, token_provider=lambda: "secret", project_registry=reg, project_reader=reader, observer=observer)
    resp = mcp.handle_rpc("tools/call", {"name": "get_chatgpt_observer_status", "arguments": {}}, 1)
    import json
    result = json.loads(resp["result"]["content"][0]["text"])
    assert result["ok"] is True
    assert result["observer_state"]["status"] == "STOPPED"
    assert result["is_running"] is False


def test_mcp_start_stop_observer():
    import tempfile, json
    from pathlib import Path
    from opencode_bridge.mcp_server import MCPServer
    db = BridgeDB(Path(tempfile.mkdtemp()) / "orch.db")
    reg = ChatGPTProjectRegistry(db)
    browser = make_browser()
    browser.select_latest_project_conversation = lambda url, excluded=None: {
        "title": "Test Conv", "conversation_id": "conv-123", "clicked": True,
        "reason": "newest_eligible", "candidates": ["Test Conv"],
    }
    browser.discover_project_conversations = lambda url: [
        {"title": "Test Conv", "conversation_id": "conv-123", "href": "/c/conv-123", "index": 0},
    ]
    browser.get_page_text = lambda: "You said: Hello\n"
    browser.conversation_health = lambda: {
        "browser_connected": True, "authenticated": True,
        "conversation_loaded": True, "readable": True, "writeable": True,
    }
    from opencode_bridge.chatgpt_interface import PlaywrightChatGPTAdapter
    adapter = PlaywrightChatGPTAdapter(browser)
    reader = ChatGPTProjectReader(adapter, reg, "palmistry")
    from opencode_bridge.chatgpt_interface import FakeChatGPTAdapter
    from opencode_bridge.executors import FakeOpenCodeExecutor
    from opencode_bridge.orchestrator import MissionOrchestrator
    from opencode_bridge.retry import RetryPolicy
    chat = FakeChatGPTAdapter(messages=[])
    ex = FakeOpenCodeExecutor()
    o = MissionOrchestrator(db, chat, ex, mission_id="m1", workspace=str(Path(tempfile.mkdtemp())),
                            allowed_repositories=[], retry_policy=RetryPolicy(max_attempts=1, base_seconds=0.01),
                            delivery_retry_policy=RetryPolicy(max_attempts=1, base_seconds=0.01), task_timeout_seconds=0.0)
    observer = ChatGPTObserver(reader, reg, interval_seconds=10)
    mcp = MCPServer(o, token_provider=lambda: "secret", project_registry=reg, project_reader=reader, observer=observer)

    # Start
    resp = mcp.handle_rpc("tools/call", {"name": "start_chatgpt_observer", "arguments": {"interval_seconds": 10}}, 1)
    result = json.loads(resp["result"]["content"][0]["text"])
    assert result["ok"] is True
    assert result["status"] == "RUNNING"

    # Stop
    resp = mcp.handle_rpc("tools/call", {"name": "stop_chatgpt_observer", "arguments": {}}, 2)
    result = json.loads(resp["result"]["content"][0]["text"])
    assert result["ok"] is True
    assert result["status"] == "STOPPED"


def test_mcp_acknowledge_message():
    import tempfile, json
    from pathlib import Path
    from opencode_bridge.mcp_server import MCPServer
    db = BridgeDB(Path(tempfile.mkdtemp()) / "orch.db")
    reg = ChatGPTProjectRegistry(db)
    obs = reg.record_observation("palmistry", "conv-1", "Test", "msg-1", "user", "Hello")
    obs_list = reg.get_observations(project_key="palmistry")
    obs_id = obs_list[0]["observation_id"]
    from opencode_bridge.chatgpt_interface import FakeChatGPTAdapter
    from opencode_bridge.executors import FakeOpenCodeExecutor
    from opencode_bridge.orchestrator import MissionOrchestrator
    from opencode_bridge.retry import RetryPolicy
    chat = FakeChatGPTAdapter(messages=[])
    ex = FakeOpenCodeExecutor()
    o = MissionOrchestrator(db, chat, ex, mission_id="m1", workspace=str(Path(tempfile.mkdtemp())),
                            allowed_repositories=[], retry_policy=RetryPolicy(max_attempts=1, base_seconds=0.01),
                            delivery_retry_policy=RetryPolicy(max_attempts=1, base_seconds=0.01), task_timeout_seconds=0.0)
    browser = make_browser()
    from opencode_bridge.chatgpt_interface import PlaywrightChatGPTAdapter
    adapter = PlaywrightChatGPTAdapter(browser)
    reader = ChatGPTProjectReader(adapter, reg, "palmistry")
    mcp = MCPServer(o, token_provider=lambda: "secret", project_registry=reg, project_reader=reader)
    resp = mcp.handle_rpc("tools/call", {"name": "acknowledge_chatgpt_message", "arguments": {"observation_id": obs_id, "acknowledged_by": "operator"}}, 1)
    result = json.loads(resp["result"]["content"][0]["text"])
    assert result["ok"] is True
    assert result["acknowledged"] is True


def test_mcp_get_unread_messages():
    import tempfile, json
    from pathlib import Path
    from opencode_bridge.mcp_server import MCPServer
    db = BridgeDB(Path(tempfile.mkdtemp()) / "orch.db")
    reg = ChatGPTProjectRegistry(db)
    reg.record_observation("palmistry", "conv-1", "Test", "msg-1", "user", "Hello")
    reg.record_observation("palmistry", "conv-1", "Test", "msg-2", "assistant", "Hi")
    from opencode_bridge.chatgpt_interface import FakeChatGPTAdapter
    from opencode_bridge.executors import FakeOpenCodeExecutor
    from opencode_bridge.orchestrator import MissionOrchestrator
    from opencode_bridge.retry import RetryPolicy
    chat = FakeChatGPTAdapter(messages=[])
    ex = FakeOpenCodeExecutor()
    o = MissionOrchestrator(db, chat, ex, mission_id="m1", workspace=str(Path(tempfile.mkdtemp())),
                            allowed_repositories=[], retry_policy=RetryPolicy(max_attempts=1, base_seconds=0.01),
                            delivery_retry_policy=RetryPolicy(max_attempts=1, base_seconds=0.01), task_timeout_seconds=0.0)
    browser = make_browser()
    from opencode_bridge.chatgpt_interface import PlaywrightChatGPTAdapter
    adapter = PlaywrightChatGPTAdapter(browser)
    reader = ChatGPTProjectReader(adapter, reg, "palmistry")
    mcp = MCPServer(o, token_provider=lambda: "secret", project_registry=reg, project_reader=reader)
    resp = mcp.handle_rpc("tools/call", {"name": "get_unread_chatgpt_messages", "arguments": {"project_key": "palmistry"}}, 1)
    result = json.loads(resp["result"]["content"][0]["text"])
    assert result["ok"] is True
    assert result["count"] == 1


def test_mcp_get_message_history():
    import tempfile, json
    from pathlib import Path
    from opencode_bridge.mcp_server import MCPServer
    db = BridgeDB(Path(tempfile.mkdtemp()) / "orch.db")
    reg = ChatGPTProjectRegistry(db)
    reg.record_observation("palmistry", "conv-1", "Test", "msg-1", "user", "Hello")
    reg.record_observation("palmistry", "conv-1", "Test", "msg-1", "user", "Hello edited")
    from opencode_bridge.chatgpt_interface import FakeChatGPTAdapter
    from opencode_bridge.executors import FakeOpenCodeExecutor
    from opencode_bridge.orchestrator import MissionOrchestrator
    from opencode_bridge.retry import RetryPolicy
    chat = FakeChatGPTAdapter(messages=[])
    ex = FakeOpenCodeExecutor()
    o = MissionOrchestrator(db, chat, ex, mission_id="m1", workspace=str(Path(tempfile.mkdtemp())),
                            allowed_repositories=[], retry_policy=RetryPolicy(max_attempts=1, base_seconds=0.01),
                            delivery_retry_policy=RetryPolicy(max_attempts=1, base_seconds=0.01), task_timeout_seconds=0.0)
    browser = make_browser()
    from opencode_bridge.chatgpt_interface import PlaywrightChatGPTAdapter
    adapter = PlaywrightChatGPTAdapter(browser)
    reader = ChatGPTProjectReader(adapter, reg, "palmistry")
    mcp = MCPServer(o, token_provider=lambda: "secret", project_registry=reg, project_reader=reader)
    resp = mcp.handle_rpc("tools/call", {"name": "get_chatgpt_message_history", "arguments": {"message_id": "msg-1", "project_key": "palmistry"}}, 1)
    result = json.loads(resp["result"]["content"][0]["text"])
    assert result["ok"] is True
    assert result["count"] == 2
