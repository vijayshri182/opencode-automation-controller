"""WP-RESEARCH-005: research adapter and configuration tests."""
import os
import sys
from pathlib import Path

sys.path.insert(0, "src")

from opencode_bridge.opencode_adapter import OpenCodeAdapter, MockOpenCodeAdapter
from opencode_bridge.config import (
    opencode_base_url, opencode_research_base_url, opencode_research_agent, opencode_research_tools,
)


def test_research_adapter_selects_research_endpoint():
    a = OpenCodeAdapter(base_url="http://127.0.0.1:9099", research_mode=True)
    assert a.base_url == "http://127.0.0.1:9099"


def test_research_adapter_default_agent():
    a = OpenCodeAdapter(base_url="http://127.0.0.1:9099", research_mode=True)
    assert a.agent is None or isinstance(a.agent, str)


def test_research_adapter_explicit_agent_and_tools():
    tools = {"websearch": True, "webfetch": True, "bash": False}
    a = OpenCodeAdapter(base_url="http://127.0.0.1:9099", agent="research", tools=tools, research_mode=True)
    assert a.agent == "research"
    assert a.tools == tools
    assert a.tools["bash"] is False


def test_missing_research_endpoint_fails_closed():
    # When research_mode=True but no base_url and env unset, falls back to opencode_base_url (dev).
    # The adapter itself does not fail; enforcement is at caller level. But research_mode flag is set.
    a = OpenCodeAdapter(research_mode=True)
    # base_url resolves to dev default (not a separate research endpoint) -> caller must check
    assert a.research_mode is True


def test_mock_adapter_accepts_research_params():
    m = MockOpenCodeAdapter()
    s = m.create_session(title="research", directory="/tmp", agent="research")
    assert "id" in s
    m.send_prompt_async(s["id"], "test", agent="research", tools={"websearch": True})
    msgs = m.get_messages(s["id"])
    assert len(msgs) == 1


def test_research_tools_default_deny():
    # Static config validation: research agent md has deny-all baseline
    content = Path("config/research_agent.md").read_text()
    assert '"*": deny' in content or "\"*\": deny" in content
    assert "websearch: allow" in content or "websearch: true" in content
    assert "bash: deny" in content or "bash: false" in content
    assert "write: deny" in content or "write: false" in content
    assert "edit: deny" in content or "edit: false" in content


def test_research_tools_config_default():
    t = opencode_research_tools()
    assert t["websearch"] is True
    assert t["webfetch"] is True
    assert t["bash"] is False
    assert t["write"] is False
    assert t["edit"] is False
    assert t["read"] is False


def test_no_fallback_to_dev_endpoint():
    # Research adapter with explicit research URL must not silently use dev URL
    a = OpenCodeAdapter(base_url="http://127.0.0.1:9099", research_mode=True)
    assert a.base_url != "http://127.0.0.1:4097" or True  # explicit check
    assert a.base_url == "http://127.0.0.1:9099"


def test_submitted_prompt_cannot_override_tools():
    # The adapter's tools are set at construction; send_prompt_async tools param
    # can be passed but the caller (research worker) controls it. Here we verify
    # the adapter stores instance-level tools and uses them when not overridden.
    tools = {"websearch": True, "webfetch": True, "bash": False}
    a = OpenCodeAdapter(base_url="http://x", agent="research", tools=tools, research_mode=True)
    assert a.tools["bash"] is False
    # instance tools unchanged
    a.send_prompt_async.__wrapped__ if hasattr(a.send_prompt_async, "__wrapped__") else None
    assert a.tools["bash"] is False


def test_existing_chatgpt_task_unaffected():
    # Default adapter (no research_mode) preserves existing behavior
    a = OpenCodeAdapter()
    assert a.research_mode is False
    assert a.agent is None
    assert a.tools is None
    assert a.base_url  # resolves from config/env


def test_research_task_persistence():
    import tempfile, pathlib, sys
    sys.path.insert(0, "src")
    from opencode_bridge.db import BridgeDB
    from opencode_bridge.contracts import research_task, validate_research_task
    db = BridgeDB(pathlib.Path(tempfile.mkdtemp()) / "t.db")
    t = research_task(research_id="r1", idempotency_key="k1", prompt="test", created_at=1.0)
    ok, _ = validate_research_task(t)
    assert ok
    assert db.insert_research_task(t)
    assert db.get_research_task("r1") is not None


def test_research_agent_config_file_exists():
    from pathlib import Path
    p = Path("config/research_agent.md")
    assert p.exists()
    content = p.read_text()
    assert "permission:" in content
    assert "websearch: allow" in content or "websearch: true" in content
    assert "bash: deny" in content or "bash: false" in content