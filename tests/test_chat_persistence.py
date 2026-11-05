import sys, tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from opencode_bridge.browser_automation import MockBrowserAdapter, PlaywrightChatGPTController


def test_record_chat_exchange_persists():
    with tempfile.TemporaryDirectory() as d:
        db = Path(d) / "bridge.db"
        # TaskController not needed for this focused check; pass a dummy
        class DummyCtrl:
            pass
        orch, browser, ctrl = None, None, None
        from opencode_bridge.browser_automation import PlaywrightChatGPTController
        browser = MockBrowserAdapter()
        browser.start()
        orch = PlaywrightChatGPTController(browser=browser, task_controller=DummyCtrl(), state_path=Path(d)/"state.json")
        marker = "WP420_CHATGPT_ROUNDTRIP_TEST_20261102"
        resp = "WP420_CHATGPT_ROUNDTRIP_TEST_20261102\n\nReceived successfully."
        orch.record_chat_exchange(marker, resp)
        assert orch.has_submitted_marker(marker) is True
        # reload from disk
        orch2 = PlaywrightChatGPTController(browser=browser, task_controller=DummyCtrl(), state_path=Path(d)/"state.json")
        assert orch2.state.last_submitted_marker == marker
        assert orch2.state.last_assistant_response == resp
        assert orch2.has_submitted_marker("OTHER") is False


def test_extract_last_assistant_text_fallback():
    # Mock adapter returns fixed text; ensure controller path doesn't crash
    with tempfile.TemporaryDirectory() as d:
        browser = MockBrowserAdapter()
        browser.start()
        browser.set_assistant_text("WP420_CHATGPT_ROUNDTRIP_TEST_20261102\n\nReceived successfully.")
        assert "WP420_CHATGPT_ROUNDTRIP_TEST_20261102" in browser.extract_last_assistant_text()