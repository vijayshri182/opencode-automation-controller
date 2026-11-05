"""WP-421A: attach to the existing Edge/CDP browser, never launch one."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from opencode_bridge.edge_attach import (
    PALMISTRY_PROJECT_ID,
    PALMISTRY_PROJECT_URL,
    attach_existing_edge,
    classify_tab,
)


class LaunchForbidden(AssertionError):
    pass


class FakePage:
    def __init__(self, url, title="", text="", links=0):
        self._url = url
        self._title = title
        self._text = text
        self._links = links
        self.navigations = []
        self.closed = False

    @property
    def url(self):
        return self._url

    def title(self):
        return self._title

    def goto(self, url, **kwargs):
        self.navigations.append(url)
        self._url = url
        self._links = self._links or 1
        return None

    def inner_text(self, selector):
        return self._text

    def content(self):
        return self._text

    def query_selector_all(self, selector):
        return [object() for _ in range(self._links)]

    def close(self):
        self.closed = True


class FakeContext:
    def __init__(self, pages):
        self.pages = pages


class FakeBrowser:
    def __init__(self, contexts):
        self.contexts = contexts

    def close(self):
        raise LaunchForbidden("browser.close() must not be called on a borrowed browser")


class FakeChromium:
    def __init__(self, contexts=None, connect_error=None):
        self._contexts = contexts or []
        self._connect_error = connect_error
        self.connect_calls = []
        self.launch_calls = []
        self.new_page_calls = []
        self.new_context_calls = []

    def connect_over_cdp(self, url, **kwargs):
        self.connect_calls.append(url)
        if self._connect_error:
            raise self._connect_error
        return FakeBrowser(self._contexts)

    # --- hard guards: any launch path is a test failure ---
    def launch(self, *args, **kwargs):
        self.launch_calls.append((args, kwargs))
        raise LaunchForbidden("chromium.launch() must never be used by the attach path")

    def launch_persistent_context(self, *args, **kwargs):
        self.launch_calls.append((args, kwargs))
        raise LaunchForbidden("launch_persistent_context() must never be used by the attach path")

    def new_page(self, *args, **kwargs):
        self.new_page_calls.append((args, kwargs))
        raise LaunchForbidden("a new page/tab must not be created by the attach path")


class FakePlaywright:
    def __init__(self, chromium):
        self.chromium = chromium
        self.stopped = 0

    def stop(self):
        self.stopped += 1


PROJECT_TEXT = "Palmistry Project\nRecent chats\nNew chat\n"
CHAT_TEXT = "ChatGPT\nWhat can I help with?\n"


def make_pw(contexts=None, connect_error=None):
    chromium = FakeChromium(contexts=contexts, connect_error=connect_error)
    return FakePlaywright(chromium), chromium


def test_classify_tab_ranks():
    assert classify_tab(PALMISTRY_PROJECT_URL)["rank"] == 0
    assert classify_tab(PALMISTRY_PROJECT_URL)["kind"] == "project"
    conv = f"https://chatgpt.com/g/g-p-{PALMISTRY_PROJECT_ID.split('g-p-')[-1]}-palmistry-project/c/abc"
    assert classify_tab(conv)["rank"] == 0
    assert classify_tab(conv)["kind"] == "project_conversation"
    assert classify_tab("https://chatgpt.com/")["rank"] == 1
    assert classify_tab("https://example.com/")["eligible"] is False


def test_attaches_instead_of_launching():
    project = FakePage(PALMISTRY_PROJECT_URL, "Palmistry Project", PROJECT_TEXT, links=3)
    pw, chromium = make_pw([FakeContext([project])])

    r = attach_existing_edge(cdp_url="http://127.0.0.1:9224", playwright=pw)

    assert r["ok"] is True
    assert chromium.connect_calls == ["http://127.0.0.1:9224"]
    assert chromium.launch_calls == []
    assert chromium.new_page_calls == []
    assert r["launched_new_browser"] is False
    assert r["attached_to_existing_browser"] is True
    assert r["reason"] == "reused_project_tab"


def test_reuses_existing_project_tab_without_navigation():
    project = FakePage(PALMISTRY_PROJECT_URL, "Palmistry Project", PROJECT_TEXT, links=5)
    other = FakePage("https://example.com/", "Example", "x")
    pw, _ = make_pw([FakeContext([other, project])])

    r = attach_existing_edge(playwright=pw)

    assert r["ok"] is True
    assert r["selected"]["url"] == PALMISTRY_PROJECT_URL
    assert r["navigated"] is False
    assert project.navigations == []
    assert r["project_verified"] is True
    assert r["conversation_list_rendered"] is True


def test_chatgpt_tab_is_reused_and_navigated_when_needed():
    home = FakePage("https://chatgpt.com/", "ChatGPT", CHAT_TEXT, links=0)
    pw, chromium = make_pw([FakeContext([home])])

    r = attach_existing_edge(playwright=pw)

    assert r["ok"] is True
    assert home.navigations == [PALMISTRY_PROJECT_URL]
    assert r["navigated"] is True
    assert r["navigation_url"] == PALMISTRY_PROJECT_URL
    assert chromium.launch_calls == []
    assert r["reason"] == "navigated_existing_chatgpt_tab"


def test_project_tab_preferred_over_plain_chatgpt_tab():
    home = FakePage("https://chatgpt.com/", "ChatGPT", CHAT_TEXT)
    project = FakePage(PALMISTRY_PROJECT_URL, "Palmistry Project", PROJECT_TEXT, links=4)
    pw, _ = make_pw([FakeContext([home]), FakeContext([project])])

    r = attach_existing_edge(playwright=pw)

    assert r["selected"]["url"] == PALMISTRY_PROJECT_URL
    assert home.navigations == []


def test_multiple_tabs_handled_deterministically():
    def build():
        return [
            FakePage("https://chatgpt.com/?a", "ChatGPT A", CHAT_TEXT),
            FakePage("https://chatgpt.com/?b", "ChatGPT B", CHAT_TEXT),
        ]

    a1, b1 = build()
    r1 = attach_existing_edge(playwright=make_pw([FakeContext([a1, b1])])[0])

    a2, b2 = build()
    r2 = attach_existing_edge(playwright=make_pw([FakeContext([a2, b2])])[0])

    assert r1["selected"]["url"] == r2["selected"]["url"] == "https://chatgpt.com/?a"
    assert r1["selected"]["context_index"] == 0
    assert r1["selected"]["page_index"] == 0
    assert b1.navigations == [] and b2.navigations == []


def test_no_suitable_tab_is_blocked_not_replaced():
    other = FakePage("https://example.com/", "Example", "nothing")
    pw, chromium = make_pw([FakeContext([other])])

    r = attach_existing_edge(playwright=pw)

    assert r["ok"] is False
    assert r["reason"] == "no_suitable_tab"
    assert "no ChatGPT tab" in r["error"]
    assert other.navigations == []
    assert chromium.new_page_calls == []
    assert chromium.launch_calls == []


def test_cdp_failure_reports_exact_error_without_fallback_launch():
    pw, chromium = make_pw(connect_error=RuntimeError("connect ECONNREFUSED 127.0.0.1:9224"))

    r = attach_existing_edge(cdp_url="http://127.0.0.1:9224", playwright=pw)

    assert r["ok"] is False
    assert r["reason"] == "cdp_connect_failed"
    assert "ECONNREFUSED 127.0.0.1:9224" in r["error"]
    assert chromium.launch_calls == []
    assert chromium.new_page_calls == []
    assert r["launched_new_browser"] is False


def test_unverified_project_blocks():
    # A reused ChatGPT tab whose navigation did not actually land on the project.
    stuck = FakePage("https://chatgpt.com/", "ChatGPT", CHAT_TEXT)
    stuck.goto = lambda url, **kwargs: None  # navigation silently does nothing
    pw, _ = make_pw([FakeContext([stuck])])

    r = attach_existing_edge(playwright=pw)

    assert r["ok"] is False
    assert r["reason"] == "project_not_verified"
    assert r["navigated"] is True


def test_signed_out_tab_is_blocked():
    signed_out = FakePage(
        PALMISTRY_PROJECT_URL, "ChatGPT", "Log in\nSign up\nGet started", links=0
    )
    pw, _ = make_pw([FakeContext([signed_out])])

    r = attach_existing_edge(playwright=pw)

    assert r["ok"] is False
    assert r["reason"] == "not_authenticated"


def test_navigation_failure_is_blocked():
    home = FakePage("https://chatgpt.com/", "ChatGPT", CHAT_TEXT)

    def boom(url, **kwargs):
        raise RuntimeError("net::ERR_ABORTED")

    home.goto = boom
    pw, _ = make_pw([FakeContext([home])])

    r = attach_existing_edge(playwright=pw)

    assert r["ok"] is False
    assert r["reason"] == "navigation_failed"
    assert "ERR_ABORTED" in r["error"]


# --- adapter integration -------------------------------------------------


def test_playwright_adapter_attach_existing_sets_page_and_disconnects_only(monkeypatch):
    from unittest.mock import patch

    from opencode_bridge.browser_automation import PlaywrightEdgeAdapter

    project = FakePage(PALMISTRY_PROJECT_URL, "Palmistry Project", PROJECT_TEXT, links=2)
    pw, chromium = make_pw([FakeContext([project])])

    # Real (owned) path: the adapter starts Playwright itself and must stop it
    # on detach without closing the borrowed tab.
    with patch("playwright.sync_api.sync_playwright") as mock_sync:
        mock_sync.return_value.start.return_value = pw
        adapter = PlaywrightEdgeAdapter(profile_dir="unused")
        info = adapter.attach_existing(cdp_url="http://127.0.0.1:9224")

        assert info["ok"] is True
        assert adapter._page is project
        assert adapter.current_url() == PALMISTRY_PROJECT_URL
        assert adapter.last_attach_info["launched_new_browser"] is False
        assert "page" not in adapter.last_attach_info

        adapter.stop()

    assert pw.stopped == 1
    assert project.closed is False  # never close the user's tab
    assert chromium.launch_calls == []
    assert chromium.new_page_calls == []


def test_playwright_adapter_attach_failure_reports_blocked(monkeypatch):
    from opencode_bridge import edge_attach
    from opencode_bridge.browser_automation import PlaywrightEdgeAdapter

    pw, chromium = make_pw(connect_error=RuntimeError("connect ECONNREFUSED 127.0.0.1:9224"))
    real = edge_attach.attach_existing_edge

    def fake_attach(**kwargs):
        return real(playwright=pw, **{k: v for k, v in kwargs.items() if k in ("cdp_url", "project_url")})

    monkeypatch.setattr(edge_attach, "attach_existing_edge", fake_attach)

    adapter = PlaywrightEdgeAdapter(profile_dir="unused")
    info = adapter.attach_existing()

    assert info["ok"] is False
    assert adapter.last_attach_info["reason"] == "cdp_connect_failed"
    assert adapter._page is None
    assert chromium.launch_calls == []


def test_cdp_adapter_attach_only_never_calls_launcher_start(monkeypatch):
    from opencode_bridge import edge_attach
    from opencode_bridge.managed_edge import CdpEdgeAdapter, ManagedEdgeLauncher

    project = FakePage(PALMISTRY_PROJECT_URL, "Palmistry Project", PROJECT_TEXT, links=2)
    project.context = FakeContext([project])
    pw, chromium = make_pw([FakeContext([project])])
    real = edge_attach.attach_existing_edge

    monkeypatch.setattr(
        edge_attach,
        "attach_existing_edge",
        lambda **kwargs: real(playwright=pw, **{k: v for k, v in kwargs.items() if k in ("cdp_url", "project_url")}),
    )

    launcher = ManagedEdgeLauncher(profile_dir="unused", port=9224)

    def forbidden_start():
        raise AssertionError("ManagedEdgeLauncher.start() must not be called in attach-only mode")

    monkeypatch.setattr(launcher, "start", forbidden_start)

    adapter = CdpEdgeAdapter(launcher=launcher, attach_only=True)
    assert adapter.start() is True
    assert adapter.current_url() == PALMISTRY_PROJECT_URL
    assert chromium.launch_calls == []


# --- WP-419 UI navigation regression ------------------------------------


class FakeNavPage:
    """Minimal page that only supports visible clicks (no route navigation)."""

    def __init__(self):
        self.clicks = []
        self.navigations = []

    def query_selector(self, selector):
        if "Projects" in selector:
            return None
        for name in ("Palmistry", "Project Test"):
            if name in selector:
                return FakeLocator(name, self)
        return None

    def query_selector_all(self, selector):
        return []

    def goto(self, url, **kwargs):
        self.navigations.append(url)

    def inner_text(self, selector):
        return ""

    def content(self):
        return ""

    @property
    def url(self):
        return PALMISTRY_PROJECT_URL


class FakeLocator:
    def __init__(self, label, page):
        self.label = label
        self.page = page

    def click(self):
        self.page.clicks.append(self.label)

    def get_attribute(self, name):
        return ""


def test_wp419_ui_navigation_preserved_and_no_direct_conversation_url(monkeypatch):
    from opencode_bridge.browser_automation import PlaywrightEdgeAdapter

    monkeypatch.setattr("time.sleep", lambda *_a, **_k: None)
    page = FakeNavPage()
    adapter = PlaywrightEdgeAdapter(profile_dir="unused")
    adapter._page = page

    assert adapter.select_project_conversation_by_ui("Palmistry", "Project Test") is True
    assert page.clicks == ["Palmistry", "Project Test"]
    assert page.navigations == []  # never navigates to /c/<id> directly


def test_cdp_adapter_attach_only_raises_when_cdp_missing(monkeypatch):
    from opencode_bridge import edge_attach
    from opencode_bridge.managed_edge import CdpEdgeAdapter, ManagedEdgeError, ManagedEdgeLauncher

    pw, _ = make_pw(connect_error=RuntimeError("connect ECONNREFUSED 127.0.0.1:9224"))
    real = edge_attach.attach_existing_edge
    monkeypatch.setattr(
        edge_attach,
        "attach_existing_edge",
        lambda **kwargs: real(playwright=pw, **{k: v for k, v in kwargs.items() if k in ("cdp_url", "project_url")}),
    )

    launcher = ManagedEdgeLauncher(profile_dir="unused", port=9224)
    monkeypatch.setattr(launcher, "start", lambda: pytest.fail("launcher.start() must not run"))
    adapter = CdpEdgeAdapter(launcher=launcher, attach_only=True)

    with pytest.raises(ManagedEdgeError) as exc:
        adapter.start()
    assert "cdp_connect_failed" in str(exc.value)
