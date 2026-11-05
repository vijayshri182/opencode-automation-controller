"""WP-424: Playwright ChatGPT communication adapter â focused tests.

All tests use deterministic doubles (MockBrowserAdapter / FakeChatGPTAdapter).
No browser is launched, no CDP endpoint is contacted, no network call is made.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest

from opencode_bridge.browser_automation import MockBrowserAdapter
from opencode_bridge.chatgpt_interface import (
    CHATGPT_AUTH_REQUIRED,
    CHATGPT_CONVERSATION_UNAVAILABLE,
    CHATGPT_DISCONNECTED,
    CHATGPT_PROJECT_UNAVAILABLE,
    DEFAULT_EXCLUDED_TITLES,
    PALMISTRY_PROJECT_ID,
    PALMISTRY_PROJECT_URL,
    PlaywrightChatGPTAdapter,
    build_inbound_message,
    derive_message_id,
)


def browser_with(**overrides):
    b = MockBrowserAdapter()
    for k, v in overrides.items():
        setattr(b, k, v)
    return b


def adapter(browser=None, controller=None):
    return PlaywrightChatGPTAdapter(browser or MockBrowserAdapter(), controller=controller)


# --- CDP / attachment ---------------------------------------------------


def test_cdp_status_reports_mock_without_launching():
    a = adapter()
    status = a.cdp_status()
    assert status["ok"] is True
    assert status.get("mock") is True


def test_cdp_status_reports_attached_info_when_present():
    b = MockBrowserAdapter()
    b.last_attach_info = {"ok": False, "error": "cdp_connect_failed"}
    b._attached = False
    a = adapter(b)
    status = a.cdp_status()
    assert status["ok"] is False
    assert status["reason"] == "cdp_connect_failed"


def test_cdp_status_reports_attached_true():
    b = MockBrowserAdapter()
    b._attached = True
    a = adapter(b)
    status = a.cdp_status()
    assert status["ok"] is True
    assert status.get("attached") is True


def test_disconnected_browser_returns_clear_blocked_result():
    b = browser_with(_auth=False)
    b.conversation_health = lambda: {
        "browser_connected": False,
        "authenticated": False,
        "conversation_loaded": False,
        "readable": False,
        "writeable": False,
    }
    a = adapter(b)
    result = a.discover_project(PALMISTRY_PROJECT_URL)
    assert result["ok"] is False
    assert result["reason"] == CHATGPT_DISCONNECTED


# --- project discovery --------------------------------------------------


def test_discover_project_uses_fixed_url_and_returns_project_id():
    a = adapter()
    result = a.discover_project(PALMISTRY_PROJECT_URL)
    assert result["ok"] is True
    assert result["project_id"] == PALMISTRY_PROJECT_ID
    assert result["project_url"] == PALMISTRY_PROJECT_URL
    assert result["conversation_count"] >= 1


def test_discover_project_never_navigates_to_stored_c_url():
    b = MockBrowserAdapter()
    calls = []
    orig = b.navigate

    def tracked(url):
        calls.append(url)
        return orig(url)

    b.navigate = tracked
    a = adapter(b)
    a.discover_project(PALMISTRY_PROJECT_URL)
    for url in calls:
        assert "/c/" not in url or "project" in url


def test_discover_project_auth_failure_returns_auth_required():
    b = MockBrowserAdapter()
    b.conversation_health = lambda: {
        "browser_connected": True,
        "authenticated": False,
        "conversation_loaded": True,
        "readable": True,
        "writeable": True,
    }
    a = adapter(b)
    result = a.discover_project(PALMISTRY_PROJECT_URL)
    assert result["ok"] is False
    assert result["reason"] == CHATGPT_AUTH_REQUIRED


def test_discover_project_no_conversations_returns_unavailable():
    b = MockBrowserAdapter()
    b.discover_project_conversations = lambda url: []
    a = adapter(b)
    result = a.discover_project(PALMISTRY_PROJECT_URL)
    assert result["ok"] is False
    assert result["reason"] == CHATGPT_PROJECT_UNAVAILABLE


# --- conversation discovery --------------------------------------------


def test_discover_latest_conversation_excludes_testing_title():
    a = adapter()
    result = a.discover_latest_conversation(PALMISTRY_PROJECT_URL)
    assert result["ok"] is True
    assert result["conversation_id"] != "6ae87cee-50a4-83e8-a0e6-eba390f83a7a"
    assert result["title"] == "Project Test"


def test_discover_latest_conversation_returns_project_id():
    a = adapter()
    result = a.discover_latest_conversation(PALMISTRY_PROJECT_URL)
    assert result["project_id"] == PALMISTRY_PROJECT_ID


def test_discover_latest_conversation_no_eligible_returns_blocked():
    b = MockBrowserAdapter()
    b.select_latest_project_conversation = lambda url, excluded=None: {
        "title": "", "conversation_id": "", "clicked": False, "reason": "no_eligible"
    }
    a = adapter(b)
    result = a.discover_latest_conversation(PALMISTRY_PROJECT_URL)
    assert result["ok"] is False
    assert result["reason"] == CHATGPT_CONVERSATION_UNAVAILABLE


def test_discover_latest_conversation_missing_cid_returns_blocked():
    b = MockBrowserAdapter()
    b.select_latest_project_conversation = lambda url, excluded=None: {
        "title": "x", "conversation_id": "", "clicked": True, "reason": "newest_eligible"
    }
    a = adapter(b)
    result = a.discover_latest_conversation(PALMISTRY_PROJECT_URL)
    assert result["ok"] is False
    assert result["reason"] == CHATGPT_CONVERSATION_UNAVAILABLE


def test_discover_latest_conversation_propagates_project_failure():
    b = MockBrowserAdapter()
    b.conversation_health = lambda: {
        "browser_connected": True,
        "authenticated": False,
        "conversation_loaded": True,
        "readable": True,
        "writeable": True,
    }
    a = adapter(b)
    result = a.discover_latest_conversation(PALMISTRY_PROJECT_URL)
    assert result["ok"] is False
    assert result["reason"] == CHATGPT_AUTH_REQUIRED


# --- incoming message extraction ----------------------------------------


def test_read_latest_messages_derives_message_id():
    b = MockBrowserAdapter()
    b.set_assistant_text("You said: Inspect the repository and produce a summary report.")
    a = adapter(b)
    result = a.read_latest_messages(PALMISTRY_PROJECT_URL)
    assert result["ok"] is True
    assert len(result["messages"]) == 1
    msg = result["messages"][0]
    assert msg["message_identity_source"] == "derived_content_hash"
    assert msg["message_id"].startswith("derived-")
    assert msg["project_id"] == PALMISTRY_PROJECT_ID
    assert msg["message_content"] == "Inspect the repository and produce a summary report."


def test_derive_message_id_is_stable():
    a = derive_message_id(PALMISTRY_PROJECT_ID, "conv-1", "hello")
    b = derive_message_id(PALMISTRY_PROJECT_ID, "conv-1", "hello")
    assert a == b
    assert a != derive_message_id(PALMISTRY_PROJECT_ID, "conv-1", "hello!")


def test_build_inbound_message_never_invents_ui_id():
    m = build_inbound_message(
        project_id=PALMISTRY_PROJECT_ID,
        conversation_id="conv-1",
        content="hi",
        correlation_id="c1",
    )
    assert m["message_id"].startswith("derived-")
    assert m["message_identity_source"] == "derived_content_hash"


def test_read_latest_messages_empty_returns_ok_with_no_messages():
    b = MockBrowserAdapter()
    b.get_page_text = lambda: ""
    # Override select to succeed but page text empty -> ambiguous
    a = adapter(b)
    result = a.read_latest_messages(PALMISTRY_PROJECT_URL)
    # Either ambiguous or ok with no messages; never crash
    assert isinstance(result, dict)
    assert "ok" in result


def test_read_latest_messages_distinguishes_user_blocks():
    b = MockBrowserAdapter()
    text = "You said: first\nChatGPT said: reply\nYou said: second\n"
    b.get_page_text = lambda: text
    # controller path not used; fallback parsing
    a = adapter(b)
    result = a.read_latest_messages(PALMISTRY_PROJECT_URL)
    # Fallback path extracts the LAST user block
    assert result["ok"] is True
    assert result["messages"][0]["message_content"] == "second"


def test_read_latest_messages_ambiguous_returns_blocked():
    b = MockBrowserAdapter()
    b.get_page_text = lambda: "ChatGPT said: only an assistant reply, no user block"
    a = adapter(b)
    result = a.read_latest_messages(PALMISTRY_PROJECT_URL)
    assert result["ok"] is False
    assert result["reason"] == "chatgpt_ambiguous_response"


def test_read_latest_messages_auth_failure_blocked():
    b = MockBrowserAdapter()
    b.conversation_health = lambda: {
        "browser_connected": True,
        "authenticated": False,
        "conversation_loaded": True,
        "readable": True,
        "writeable": True,
    }
    a = adapter(b)
    result = a.read_latest_messages(PALMISTRY_PROJECT_URL)
    assert result["ok"] is False
    assert result["reason"] == CHATGPT_AUTH_REQUIRED


def test_read_latest_messages_uses_controller_when_provided():
    class FakeController:
        def discover_and_read_latest_message(self, project_url, excluded_titles=None):
            return {
                "ok": True,
                "conversation_id": "conv-ctrl",
                "latest_user_message": "controller-provided message",
                "latest_user_message_at": "12:34",
            }

    a = adapter(MockBrowserAdapter(), controller=FakeController())
    result = a.read_latest_messages(PALMISTRY_PROJECT_URL)
    assert result["ok"] is True
    assert result["messages"][0]["message_content"] == "controller-provided message"
    assert result["messages"][0]["message_timestamp"] == "12:34"
    assert result["conversation_id"] == "conv-ctrl"


def test_read_latest_messages_controller_failure_returns_blocked():
    class FakeController:
        def discover_and_read_latest_message(self, project_url, excluded_titles=None):
            return {"ok": False, "reason": "selection failed"}

    a = adapter(MockBrowserAdapter(), controller=FakeController())
    result = a.read_latest_messages(PALMISTRY_PROJECT_URL)
    assert result["ok"] is False


def test_read_latest_messages_empty_content_blocked():
    b = MockBrowserAdapter()
    b.get_page_text = lambda: "You said:   "
    a = adapter(b)
    result = a.read_latest_messages(PALMISTRY_PROJECT_URL)
    assert result["ok"] is False
    assert result["reason"] == "chatgpt_ambiguous_response"


# --- delivery -----------------------------------------------------------


def test_deliver_message_success_returns_delivered():
    a = adapter()
    conv = {"project_id": PALMISTRY_PROJECT_ID, "conversation_id": "conv-1"}
    result = a.deliver_message(conv, "hello world", dedupe_key="d1")
    assert result["ok"] is True
    assert result["status"] == "delivered"
    assert result["dedupe_key"] == "d1"
    assert result["evidence"]["verified"] is True


def test_deliver_message_empty_content_rejected():
    a = adapter()
    conv = {"project_id": PALMISTRY_PROJECT_ID, "conversation_id": "conv-1"}
    result = a.deliver_message(conv, "   ", dedupe_key="d1")
    assert result["ok"] is False
    assert result["status"] == "failed"
    assert result["reason"] == "empty content"


def test_deliver_message_project_mismatch_blocked():
    b = MockBrowserAdapter()
    b.current_url = lambda: "https://chatgpt.com/g/g-p-OTHER/project"
    a = adapter(b)
    conv = {"project_id": PALMISTRY_PROJECT_ID, "conversation_id": "conv-1"}
    result = a.deliver_message(conv, "hello", dedupe_key="d1")
    assert result["ok"] is False
    assert result["status"] == "failed"
    assert result["reason"] == CHATGPT_PROJECT_UNAVAILABLE


def test_deliver_message_auth_failure_blocked():
    b = MockBrowserAdapter()
    b.conversation_health = lambda: {
        "browser_connected": True,
        "authenticated": False,
        "conversation_loaded": True,
        "readable": True,
        "writeable": True,
    }
    a = adapter(b)
    conv = {"project_id": PALMISTRY_PROJECT_ID, "conversation_id": "conv-1"}
    result = a.deliver_message(conv, "hello", dedupe_key="d1")
    assert result["ok"] is False
    assert result["reason"] == CHATGPT_AUTH_REQUIRED


def test_deliver_message_composer_not_ready_blocked():
    b = MockBrowserAdapter()
    b.conversation_health = lambda: {
        "browser_connected": True,
        "authenticated": True,
        "conversation_loaded": True,
        "readable": True,
        "writeable": False,
    }
    a = adapter(b)
    conv = {"project_id": PALMISTRY_PROJECT_ID, "conversation_id": "conv-1"}
    result = a.deliver_message(conv, "hello", dedupe_key="d1")
    assert result["ok"] is False
    assert result["reason"] == CHATGPT_DISCONNECTED


def test_deliver_message_submit_failure_returns_uncertain():
    b = MockBrowserAdapter()
    b.submit_message = lambda text: False
    a = adapter(b)
    conv = {"project_id": PALMISTRY_PROJECT_ID, "conversation_id": "conv-1"}
    result = a.deliver_message(conv, "hello", dedupe_key="d1")
    assert result["ok"] is False
    assert result["status"] == "uncertain"
    assert result["reason"] == "chatgpt_delivery_uncertain"


def test_deliver_message_submit_exception_returns_uncertain():
    b = MockBrowserAdapter()

    def boom(text):
        raise RuntimeError("boom")

    b.submit_message = boom
    a = adapter(b)
    conv = {"project_id": PALMISTRY_PROJECT_ID, "conversation_id": "conv-1"}
    result = a.deliver_message(conv, "hello", dedupe_key="d1")
    assert result["ok"] is False
    assert result["status"] == "uncertain"


def test_deliver_message_unverified_returns_uncertain():
    b = MockBrowserAdapter()
    b.verify_submitted = lambda text: False
    a = adapter(b)
    conv = {"project_id": PALMISTRY_PROJECT_ID, "conversation_id": "conv-1"}
    result = a.deliver_message(conv, "hello", dedupe_key="d1")
    assert result["ok"] is False
    assert result["status"] == "uncertain"


def test_deliver_message_never_navigates_to_c_url():
    b = MockBrowserAdapter()
    calls = []
    orig = b.navigate

    def tracked(url):
        calls.append(url)
        return orig(url)

    b.navigate = tracked
    a = adapter(b)
    conv = {"project_id": PALMISTRY_PROJECT_ID, "conversation_id": "conv-1"}
    a.deliver_message(conv, "hello", dedupe_key="d1")
    for url in calls:
        assert "/c/" not in url


# --- verify_delivery -----------------------------------------------------


def test_verify_delivery_verified():
    b = MockBrowserAdapter()
    b.verify_submitted = lambda text: True
    a = adapter(b)
    result = a.verify_delivery({"content_prefix": "hello"})
    assert result["verified"] is True


def test_verify_delivery_unverified():
    b = MockBrowserAdapter()
    b.verify_submitted = lambda text: False
    a = adapter(b)
    result = a.verify_delivery({"content_prefix": "hello"})
    assert result["verified"] is False


def test_verify_delivery_no_prefix_returns_unverified():
    a = adapter()
    result = a.verify_delivery({})
    assert result["verified"] is False
    assert result["ok"] is False


def test_verify_delivery_exception_returns_unverified():
    b = MockBrowserAdapter()

    def boom(text):
        raise RuntimeError("boom")

    b.verify_submitted = boom
    a = adapter(b)
    result = a.verify_delivery({"content_prefix": "hello"})
    assert result["verified"] is False


# --- project/conversation invariants ------------------------------------


def test_default_excluded_titles_includes_testing():
    assert "OpenCode Automation Testing" in DEFAULT_EXCLUDED_TITLES


def test_palmistry_constants_are_fixed():
    assert PALMISTRY_PROJECT_URL == "https://chatgpt.com/g/g-p-6ae87c1e48b08191a2cd33139c40639f/project"
    assert PALMISTRY_PROJECT_ID == "g-p-6ae87c1e48b08191a2cd33139c40639f"


def test_adapter_does_not_create_conversations():
    b = MockBrowserAdapter()
    called = {"create": 0}
    orig = b.create_project_chat

    def tracked(name):
        called["create"] += 1
        return orig(name)

    b.create_project_chat = tracked
    a = adapter(b)
    a.discover_project(PALMISTRY_PROJECT_URL)
    a.discover_latest_conversation(PALMISTRY_PROJECT_URL)
    a.read_latest_messages(PALMISTRY_PROJECT_URL)
    assert called["create"] == 0

