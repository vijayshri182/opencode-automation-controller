"""WP-431B: ChatGPT project registry and read-only reader â focused tests.

Uses deterministic doubles (MockBrowserAdapter). No live browser, no network.
"""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest

from opencode_bridge.browser_automation import MockBrowserAdapter
from opencode_bridge.chatgpt_interface import PALMISTRY_PROJECT_ID, PALMISTRY_PROJECT_URL
from opencode_bridge.chatgpt_project_reader import (
    ChatGPTProjectRegistry,
    ChatGPTProjectReader,
    validate_project_key,
    validate_project_url,
    derive_project_id,
)
from opencode_bridge.db import BridgeDB


def make_registry(tmp_path):
    db = BridgeDB(tmp_path / "orch.db")
    return ChatGPTProjectRegistry(db), db


def make_browser():
    b = MockBrowserAdapter()
    return b

def make_adapter(browser=None):
    from opencode_bridge.chatgpt_interface import PlaywrightChatGPTAdapter
    return PlaywrightChatGPTAdapter(browser or MockBrowserAdapter())


# --- validation ---------------------------------------------------------


def test_validate_project_key():
    assert validate_project_key("palmistry") is True
    assert validate_project_key("my-project") is True
    assert validate_project_key("") is False
    assert validate_project_key("x" * 65) is False
    assert validate_project_key("bad key!") is False


def test_validate_project_url():
    assert validate_project_url(PALMISTRY_PROJECT_URL) is True
    assert validate_project_url("https://chatgpt.com/g/g-p-abc123/project") is True
    assert validate_project_url("https://example.com") is False
    assert validate_project_url("") is False
    assert validate_project_url("http://chatgpt.com/g/g-p-abc/project") is False


def test_derive_project_id():
    assert derive_project_id(PALMISTRY_PROJECT_URL) == PALMISTRY_PROJECT_ID
    assert derive_project_id("https://chatgpt.com/g/g-p-abc123/project") == "g-p-abc123"
    assert derive_project_id("invalid") == ""


# --- registry -----------------------------------------------------------


def test_default_project_registered(tmp_path):
    reg, db = make_registry(tmp_path)
    projects = reg.list_projects()
    assert len(projects) == 1
    assert projects[0]["project_key"] == "palmistry"
    assert projects[0]["display_name"] == "Palmistry Project"
    assert projects[0]["project_url"] == PALMISTRY_PROJECT_URL
    assert projects[0]["enabled"] == 1
    assert projects[0]["read_only"] == 1


def test_active_project_default(tmp_path):
    reg, db = make_registry(tmp_path)
    assert reg.get_active_project_key() == "palmistry"


def test_register_multiple_projects(tmp_path):
    reg, db = make_registry(tmp_path)
    reg.register_project("test-proj", "Test Project", "https://chatgpt.com/g/g-p-test123/project")
    projects = reg.list_projects()
    assert len(projects) == 2
    keys = [p["project_key"] for p in projects]
    assert "palmistry" in keys
    assert "test-proj" in keys


def test_set_active_project(tmp_path):
    reg, db = make_registry(tmp_path)
    reg.register_project("test-proj", "Test Project", "https://chatgpt.com/g/g-p-test123/project")
    reg.set_active_project("test-proj")
    assert reg.get_active_project_key() == "test-proj"


def test_set_active_disabled_project_fails(tmp_path):
    reg, db = make_registry(tmp_path)
    reg.register_project("disabled-proj", "Disabled", "https://chatgpt.com/g/g-p-disabled/project", enabled=False)
    with pytest.raises(ValueError):
        reg.set_active_project("disabled-proj")


def test_set_active_unregistered_project_fails(tmp_path):
    reg, db = make_registry(tmp_path)
    with pytest.raises(ValueError):
        reg.set_active_project("nonexistent")


def test_polling_disabled_by_default(tmp_path):
    reg, db = make_registry(tmp_path)
    assert reg.get_polling_enabled() is False


def test_enable_polling(tmp_path):
    reg, db = make_registry(tmp_path)
    reg.set_polling_enabled(True)
    assert reg.get_polling_enabled() is True
    reg.set_polling_enabled(False)
    assert reg.get_polling_enabled() is False


def test_update_read_state(tmp_path):
    reg, db = make_registry(tmp_path)
    reg.update_read_state(last_read_at=1234.0, last_error="test error")
    state = reg.get_state()
    assert state["last_read_at"] == 1234.0
    assert state["last_error"] == "test error"


def test_register_invalid_project_key_fails(tmp_path):
    reg, db = make_registry(tmp_path)
    with pytest.raises(ValueError):
        reg.register_project("", "Name", "https://chatgpt.com/g/g-p-abc/project")
    with pytest.raises(ValueError):
        reg.register_project("bad key!", "Name", "https://chatgpt.com/g/g-p-abc/project")


def test_register_invalid_url_fails(tmp_path):
    reg, db = make_registry(tmp_path)
    with pytest.raises(ValueError):
        reg.register_project("key", "Name", "https://example.com")
    with pytest.raises(ValueError):
        reg.register_project("key", "Name", "")


# --- observations -------------------------------------------------------


def test_record_observation(tmp_path):
    reg, db = make_registry(tmp_path)
    result = reg.record_observation(
        project_key="palmistry", conversation_id="conv-1",
        conversation_title="Test Conv", message_id="msg-1",
        role="user", content="Hello world",
    )
    assert result["duplicate"] is False
    assert result["edited"] is False
    assert "observation_id" in result


def test_duplicate_observation_detected(tmp_path):
    reg, db = make_registry(tmp_path)
    reg.record_observation("palmistry", "conv-1", "Test", "msg-1", "user", "Hello")
    result = reg.record_observation("palmistry", "conv-1", "Test", "msg-1", "user", "Hello")
    assert result["duplicate"] is True


def test_edited_message_detected(tmp_path):
    reg, db = make_registry(tmp_path)
    reg.record_observation("palmistry", "conv-1", "Test", "msg-1", "user", "Hello")
    result = reg.record_observation("palmistry", "conv-1", "Test", "msg-1", "user", "Hello edited")
    assert result["duplicate"] is True
    assert result["edited"] is True
    assert result["edit_of"] is not None


def test_get_observations(tmp_path):
    reg, db = make_registry(tmp_path)
    reg.record_observation("palmistry", "conv-1", "Test", "msg-1", "user", "Hello")
    reg.record_observation("palmistry", "conv-1", "Test", "msg-2", "assistant", "Hi there")
    obs = reg.get_observations(project_key="palmistry")
    assert len(obs) == 2
    roles = [o["role"] for o in obs]
    assert "user" in roles
    assert "assistant" in roles


def test_get_observations_filter_by_role(tmp_path):
    reg, db = make_registry(tmp_path)
    reg.record_observation("palmistry", "conv-1", "Test", "msg-1", "user", "Hello")
    reg.record_observation("palmistry", "conv-1", "Test", "msg-2", "assistant", "Hi")
    user_obs = reg.get_observations(project_key="palmistry", role="user")
    assert len(user_obs) == 1
    assert user_obs[0]["role"] == "user"


def test_get_latest_observation(tmp_path):
    reg, db = make_registry(tmp_path)
    reg.record_observation("palmistry", "conv-1", "Test", "msg-1", "user", "First")
    reg.record_observation("palmistry", "conv-1", "Test", "msg-2", "user", "Second")
    latest = reg.get_latest_observation("palmistry")
    assert latest is not None
    assert latest["content"] == "Second"


def test_get_new_user_messages(tmp_path):
    reg, db = make_registry(tmp_path)
    reg.record_observation("palmistry", "conv-1", "Test", "msg-1", "user", "Hello")
    reg.record_observation("palmistry", "conv-1", "Test", "msg-2", "assistant", "Hi")
    reader = ChatGPTProjectReader(None, reg, "palmistry")
    result = reader.get_new_user_messages()
    assert result["ok"] is True
    assert result["count"] == 1
    assert result["messages"][0]["role"] == "user"


# --- reader (mocked) ----------------------------------------------------


def test_reader_discover_conversation():
    browser = make_browser()
    # Mock discover_latest_conversation to return a result
    browser.select_latest_project_conversation = lambda url, excluded=None: {
        "title": "Test Conv", "conversation_id": "conv-123", "clicked": True,
        "reason": "newest_eligible", "candidates": ["Test Conv"],
    }
    browser.discover_project_conversations = lambda url: [
        {"title": "Test Conv", "conversation_id": "conv-123", "href": "/c/conv-123", "index": 0},
    ]
    browser.conversation_health = lambda: {
        "browser_connected": True, "authenticated": True,
        "conversation_loaded": True, "readable": True, "writeable": True,
    }
    reg, db = make_registry(Path(tempfile.mkdtemp()))
    reader = ChatGPTProjectReader(browser, reg, "palmistry")
    result = reader.discover_conversation()
    assert result["ok"] is True
    assert result["conversation_id"] == "conv-123"


def test_reader_discover_project_mismatch():
    browser = make_browser()
    browser.select_latest_project_conversation = lambda url, excluded=None: {
        "title": "Test Conv", "conversation_id": "conv-123", "clicked": True,
        "reason": "newest_eligible", "candidates": ["Test Conv"],
    }
    browser.discover_project_conversations = lambda url: [
        {"title": "Test Conv", "conversation_id": "conv-123", "href": "/c/conv-123", "index": 0},
    ]
    browser.conversation_health = lambda: {
        "browser_connected": True, "authenticated": True,
        "conversation_loaded": True, "readable": True, "writeable": True,
    }
    # Override discover_project to return wrong project_id
    original_discover = browser.discover_project_conversations
    browser.discover_project_conversations = lambda url: []
    reg, db = make_registry(Path(tempfile.mkdtemp()))
    reader = ChatGPTProjectReader(browser, reg, "palmistry")
    # discover_latest_conversation calls discover_project first
    # Override the adapter's discover_project to return a mismatched project_id
    reader.adapter.discover_project = lambda url: {
        "ok": True, "project_id": "g-p-wrong", "project_url": url,
        "conversation_count": 1, "conversations": [],
    }
    result = reader.discover_conversation()
    assert result["ok"] is False
    assert result["reason"] == "project_identity_mismatch"


def test_reader_read_messages_persists():
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
    reg, db = make_registry(Path(tempfile.mkdtemp()))
    reader = ChatGPTProjectReader(browser, reg, "palmistry")
    result = reader.read_messages(max_messages=5)
    assert result["ok"] is True
    assert result["message_count"] >= 1
    assert result["user_message_count"] >= 1
    # Verify persisted
    obs = reg.get_observations(project_key="palmistry")
    assert len(obs) >= 1


def test_reader_read_messages_ambiguous():
    browser = make_browser()
    browser.select_latest_project_conversation = lambda url, excluded=None: {
        "title": "Test Conv", "conversation_id": "conv-123", "clicked": True,
        "reason": "newest_eligible", "candidates": ["Test Conv"],
    }
    browser.discover_project_conversations = lambda url: [
        {"title": "Test Conv", "conversation_id": "conv-123", "href": "/c/conv-123", "index": 0},
    ]
    browser.get_page_text = lambda: "ChatGPT said: only assistant reply"
    browser.conversation_health = lambda: {
        "browser_connected": True, "authenticated": True,
        "conversation_loaded": True, "readable": True, "writeable": True,
    }
    reg, db = make_registry(Path(tempfile.mkdtemp()))
    reader = ChatGPTProjectReader(browser, reg, "palmistry")
    result = reader.read_messages(max_messages=5)
    # Should either succeed with no messages or fail gracefully
    assert isinstance(result, dict)
    assert "ok" in result


def test_reader_get_state():
    reg, db = make_registry(Path(tempfile.mkdtemp()))
    reader = ChatGPTProjectReader(None, reg, "palmistry")
    state = reader.get_state()
    assert state["ok"] is True
    assert state["project_key"] == "palmistry"
    assert state["project"] is not None
    assert state["project"]["display_name"] == "Palmistry Project"


def test_reader_no_active_project():
    reg, db = make_registry(Path(tempfile.mkdtemp()))
    # Remove active project
    reg.set_active_project.__wrapped__ if hasattr(reg.set_active_project, '__wrapped__') else None
    # Directly clear active project
    with db._lock:
        with __import__("contextlib").closing(db._connect()) as conn:
            conn.execute("UPDATE chatgpt_project_state SET active_project_key=NULL WHERE id=1")
            conn.commit()
    reader = ChatGPTProjectReader(None, reg, None)
    reader.project_key = None
    with pytest.raises(ValueError):
        reader._project()


def test_reader_latest_snapshot():
    reg, db = make_registry(Path(tempfile.mkdtemp()))
    reg.record_observation("palmistry", "conv-1", "Test", "msg-1", "user", "Hello")
    reader = ChatGPTProjectReader(None, reg, "palmistry")
    snap = reader.get_latest_snapshot()
    assert snap["ok"] is True
    assert snap["observation"]["content"] == "Hello"


def test_reader_latest_snapshot_empty():
    reg, db = make_registry(Path(tempfile.mkdtemp()))
    reader = ChatGPTProjectReader(None, reg, "palmistry")
    snap = reader.get_latest_snapshot()
    assert snap["ok"] is False
    assert snap["reason"] == "no_observations"


def test_exclusion_rules_configurable(tmp_path):
    reg, db = make_registry(tmp_path)
    reg.register_project("custom-proj", "Custom", "https://chatgpt.com/g/g-p-custom123/project",
                         excluded_titles=["Custom Exclusion", "Another"])
    proj = reg.get_project("custom-proj")
    excluded = __import__("json").loads(proj["excluded_titles_json"])
    assert "Custom Exclusion" in excluded
    assert "Another" in excluded
    assert "OpenCode Automation Testing" not in excluded


def test_palmistry_exclusion_retained(tmp_path):
    reg, db = make_registry(tmp_path)
    proj = reg.get_project("palmistry")
    excluded = __import__("json").loads(proj["excluded_titles_json"])
    assert "OpenCode Automation Testing" in excluded


# --- mcp integration ----------------------------------------------------


def test_mcp_list_projects():
    import tempfile
    from pathlib import Path
    from opencode_bridge.mcp_server import MCPServer
    db = BridgeDB(Path(tempfile.mkdtemp()) / "orch.db")
    reg = ChatGPTProjectRegistry(db)
    from opencode_bridge.chatgpt_interface import FakeChatGPTAdapter
    from opencode_bridge.db import BridgeDB as BDB
    from opencode_bridge.executors import FakeOpenCodeExecutor
    from opencode_bridge.orchestrator import MissionOrchestrator
    from opencode_bridge.retry import RetryPolicy
    chat = FakeChatGPTAdapter(messages=[])
    ex = FakeOpenCodeExecutor()
    o = MissionOrchestrator(db, chat, ex, mission_id="m1", workspace=str(Path(tempfile.mkdtemp())),
                            allowed_repositories=[], retry_policy=RetryPolicy(max_attempts=1, base_seconds=0.01),
                            delivery_retry_policy=RetryPolicy(max_attempts=1, base_seconds=0.01), task_timeout_seconds=0.0)
    browser = make_browser()
    reader = ChatGPTProjectReader(browser, reg, "palmistry")
    mcp = MCPServer(o, token_provider=lambda: "secret", project_registry=reg, project_reader=reader)
    resp = mcp.handle_rpc("tools/call", {"name": "list_chatgpt_projects", "arguments": {}}, 1)
    result = __import__("json").loads(resp["result"]["content"][0]["text"])
    assert result["ok"] is True
    assert result["count"] == 1
    assert result["projects"][0]["project_key"] == "palmistry"


def test_mcp_get_project():
    import tempfile, json
    from pathlib import Path
    from opencode_bridge.mcp_server import MCPServer
    db = BridgeDB(Path(tempfile.mkdtemp()) / "orch.db")
    reg = ChatGPTProjectRegistry(db)
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
    reader = ChatGPTProjectReader(browser, reg, "palmistry")
    mcp = MCPServer(o, token_provider=lambda: "secret", project_registry=reg, project_reader=reader)
    resp = mcp.handle_rpc("tools/call", {"name": "get_chatgpt_project", "arguments": {"project_key": "palmistry"}}, 1)
    result = json.loads(resp["result"]["content"][0]["text"])
    assert result["ok"] is True
    assert result["project"]["display_name"] == "Palmistry Project"


def test_mcp_get_project_not_found():
    import tempfile, json
    from pathlib import Path
    from opencode_bridge.mcp_server import MCPServer
    db = BridgeDB(Path(tempfile.mkdtemp()) / "orch.db")
    reg = ChatGPTProjectRegistry(db)
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
    reader = ChatGPTProjectReader(browser, reg, "palmistry")
    mcp = MCPServer(o, token_provider=lambda: "secret", project_registry=reg, project_reader=reader)
    resp = mcp.handle_rpc("tools/call", {"name": "get_chatgpt_project", "arguments": {"project_key": "nonexistent"}}, 1)
    result = json.loads(resp["result"]["content"][0]["text"])
    assert result["ok"] is False
    assert result["reason"] == "project_not_found"


def test_mcp_set_active_project():
    import tempfile, json
    from pathlib import Path
    from opencode_bridge.mcp_server import MCPServer
    db = BridgeDB(Path(tempfile.mkdtemp()) / "orch.db")
    reg = ChatGPTProjectRegistry(db)
    reg.register_project("test-proj", "Test", "https://chatgpt.com/g/g-p-test123/project")
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
    reader = ChatGPTProjectReader(browser, reg, "palmistry")
    mcp = MCPServer(o, token_provider=lambda: "secret", project_registry=reg, project_reader=reader)
    resp = mcp.handle_rpc("tools/call", {"name": "set_active_chatgpt_project", "arguments": {"project_key": "test-proj"}}, 1)
    result = json.loads(resp["result"]["content"][0]["text"])
    assert result["ok"] is True
    assert reg.get_active_project_key() == "test-proj"
    assert reader.project_key == "test-proj"


def test_mcp_get_observations():
    import tempfile, json
    from pathlib import Path
    from opencode_bridge.mcp_server import MCPServer
    db = BridgeDB(Path(tempfile.mkdtemp()) / "orch.db")
    reg = ChatGPTProjectRegistry(db)
    reg.record_observation("palmistry", "conv-1", "Test", "msg-1", "user", "Hello")
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
    reader = ChatGPTProjectReader(browser, reg, "palmistry")
    mcp = MCPServer(o, token_provider=lambda: "secret", project_registry=reg, project_reader=reader)
    resp = mcp.handle_rpc("tools/call", {"name": "get_chatgpt_observations", "arguments": {"project_key": "palmistry"}}, 1)
    result = json.loads(resp["result"]["content"][0]["text"])
    assert result["ok"] is True
    assert result["count"] == 1


def test_mcp_get_reader_state():
    import tempfile, json
    from pathlib import Path
    from opencode_bridge.mcp_server import MCPServer
    db = BridgeDB(Path(tempfile.mkdtemp()) / "orch.db")
    reg = ChatGPTProjectRegistry(db)
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
    reader = ChatGPTProjectReader(browser, reg, "palmistry")
    mcp = MCPServer(o, token_provider=lambda: "secret", project_registry=reg, project_reader=reader)
    resp = mcp.handle_rpc("tools/call", {"name": "get_chatgpt_reader_state", "arguments": {}}, 1)
    result = json.loads(resp["result"]["content"][0]["text"])
    assert result["ok"] is True
    assert result["active_project"]["project_key"] == "palmistry"
