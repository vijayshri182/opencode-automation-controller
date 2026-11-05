import sys, tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from opencode_bridge.browser_automation import MockBrowserAdapter, PlaywrightChatGPTController


class DynamicMock(MockBrowserAdapter):
    def __init__(self, convs):
        super().__init__()
        self._convs = convs
        self.opened_urls = []
        self.clicked = []

    def discover_project_conversations(self, project_url):
        self.opened_urls.append(project_url)
        return [dict(c) for c in self._convs]

    def select_latest_project_conversation(self, project_url, excluded_titles=None):
        self.opened_urls.append(project_url)
        excluded = set(excluded_titles or [])
        eligible = [c for c in self._convs if c["title"] not in excluded]
        if not self._convs:
            return {"title": "", "conversation_id": "", "clicked": False, "reason": "no_conversations"}
        if not eligible:
            return {"title": "", "conversation_id": "", "clicked": False, "reason": "no_eligible"}
        chosen = eligible[0]
        self.clicked.append(chosen["title"])
        self._url = "https://chatgpt.com/c/mock-" + chosen["title"]
        return {"title": chosen["title"], "conversation_id": chosen["conversation_id"],
                "clicked": True, "reason": "newest_eligible", "candidates": [c["title"] for c in self._convs]}

    def get_page_text(self):
        return self._page_text if hasattr(self, "_page_text") else ""

    def conversation_health(self):
        return {"browser_connected": True, "authenticated": True, "conversation_loaded": True,
                "readable": True, "writeable": True}


def test_opens_exact_project_url():
    convs = [{"title": "Project Test", "conversation_id": "id1", "href": "/c/id1", "index": 0}]
    b = DynamicMock(convs)
    b.start()
    with tempfile.TemporaryDirectory() as d:
        class Dummy: pass
        orch = PlaywrightChatGPTController(browser=b, task_controller=Dummy(), state_path=Path(d)/"s.json")
        orch.discover_and_read_latest_message("https://chatgpt.com/g/g-p-6ae87c1e48b08191a2cd33139c40639f/project")
        assert b.opened_urls and b.opened_urls[0] == "https://chatgpt.com/g/g-p-6ae87c1e48b08191a2cd33139c40639f/project"


def test_selects_newest_eligible():
    convs = [
        {"title": "Test received", "conversation_id": "id-tr", "href": "/c/id-tr", "index": 0},
        {"title": "Project Test", "conversation_id": "id-pt", "href": "/c/id-pt", "index": 1},
    ]
    b = DynamicMock(convs)
    b.start()
    with tempfile.TemporaryDirectory() as d:
        class Dummy: pass
        orch = PlaywrightChatGPTController(browser=b, task_controller=Dummy(), state_path=Path(d)/"s.json")
        r = orch.discover_and_read_latest_message("https://chatgpt.com/g/g-p-6ae87c1e48b08191a2cd33139c40639f/project")
        assert r["ok"] is True
        assert r["title"] == "Test received"


def test_selects_project_test_when_newest():
    convs = [
        {"title": "Project Test", "conversation_id": "id-pt", "href": "/c/id-pt", "index": 0},
        {"title": "Type Here Responses", "conversation_id": "id-thr", "href": "/c/id-thr", "index": 1},
    ]
    b = DynamicMock(convs)
    b.start()
    with tempfile.TemporaryDirectory() as d:
        class Dummy: pass
        orch = PlaywrightChatGPTController(browser=b, task_controller=Dummy(), state_path=Path(d)/"s.json")
        r = orch.discover_and_read_latest_message("https://chatgpt.com/g/g-p-6ae87c1e48b08191a2cd33139c40639f/project")
        assert r["title"] == "Project Test"


def test_excludes_opencode_automation_testing():
    convs = [
        {"title": "OpenCode Automation Testing", "conversation_id": "id-oat", "href": "/c/id-oat", "index": 0},
        {"title": "Project Test", "conversation_id": "id-pt", "href": "/c/id-pt", "index": 1},
    ]
    b = DynamicMock(convs)
    b.start()
    with tempfile.TemporaryDirectory() as d:
        class Dummy: pass
        orch = PlaywrightChatGPTController(browser=b, task_controller=Dummy(), state_path=Path(d)/"s.json")
        r = orch.discover_and_read_latest_message("https://chatgpt.com/g/g-p-6ae87c1e48b08191a2cd33139c40639f/project")
        assert r["title"] == "Project Test"


def test_reads_latest_user_message():
    convs = [{"title": "Project Test", "conversation_id": "id-pt", "href": "/c/id-pt", "index": 0}]
    b = DynamicMock(convs)
    b.start()
    b._page_text = "You said:\nfirst msg\nChatGPT said:\nhi\nYou said:\nsecond msg\nChatGPT said:\nok\n"
    with tempfile.TemporaryDirectory() as d:
        class Dummy: pass
        orch = PlaywrightChatGPTController(browser=b, task_controller=Dummy(), state_path=Path(d)/"s.json")
        r = orch.discover_and_read_latest_message("https://chatgpt.com/g/g-p-6ae87c1e48b08191a2cd33139c40639f/project")
        assert r["latest_user_message"] == "second msg"


def test_no_conversations_pauses():
    b = DynamicMock([])
    b.start()
    with tempfile.TemporaryDirectory() as d:
        class Dummy: pass
        orch = PlaywrightChatGPTController(browser=b, task_controller=Dummy(), state_path=Path(d)/"s.json")
        r = orch.discover_and_read_latest_message("https://chatgpt.com/g/g-p-6ae87c1e48b08191a2cd33139c40639f/project")
        assert r["ok"] is False


def test_persists_selected_state():
    convs = [{"title": "Project Test", "conversation_id": "id-pt", "href": "/c/id-pt", "index": 0}]
    b = DynamicMock(convs)
    b.start()
    b._page_text = "You said:\nhello\nChatGPT said:\nhi\n"
    with tempfile.TemporaryDirectory() as d:
        class Dummy: pass
        orch = PlaywrightChatGPTController(browser=b, task_controller=Dummy(), state_path=Path(d)/"s.json")
        orch.discover_and_read_latest_message("https://chatgpt.com/g/g-p-6ae87c1e48b08191a2cd33139c40639f/project")
        orch2 = PlaywrightChatGPTController(browser=b, task_controller=Dummy(), state_path=Path(d)/"s.json")
        assert orch2.state.conversation_title == "Project Test"
        assert orch2.state.conversation_id == "id-pt"
        assert orch2.state.latest_user_message == "hello"


def test_no_direct_conversation_url_in_discovery():
    # ensure discover uses project_url, not /c/ URL, for the goto
    convs = [{"title": "Project Test", "conversation_id": "id-pt", "href": "/c/id-pt", "index": 0}]
    b = DynamicMock(convs)
    b.start()
    with tempfile.TemporaryDirectory() as d:
        class Dummy: pass
        orch = PlaywrightChatGPTController(browser=b, task_controller=Dummy(), state_path=Path(d)/"s.json")
        orch.discover_and_read_latest_message("https://chatgpt.com/g/g-p-6ae87c1e48b08191a2cd33139c40639f/project")
        assert all("/c/" not in u or "project" in u for u in b.opened_urls)