"""WP-422: single CDP port (9224), existing-profile preservation, attach-only."""

import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

SRC = Path(__file__).resolve().parent.parent / "src" / "opencode_bridge"


def read(name):
    return (SRC / name).read_text(encoding="utf-8-sig")


# --- port standardisation ------------------------------------------------


def test_single_configured_cdp_port_is_9224():
    from opencode_bridge import edge_attach, managed_edge

    assert managed_edge.DEFAULT_CDP_PORT == 9224
    assert edge_attach.CDP_URL == "http://127.0.0.1:9224"
    launcher = managed_edge.ManagedEdgeLauncher(profile_dir="unused")
    assert launcher.cdp_url() == "http://127.0.0.1:9224"


def test_no_hidden_9222_fallback_in_source():
    offenders = []
    for py in SRC.glob("*.py"):
        text = py.read_text(encoding="utf-8-sig")
        if "9222" in text:
            offenders.append(py.name)
    assert offenders == [], f"unexpected legacy port references: {offenders}"


# --- attach path can only attach ----------------------------------------


def test_attach_module_has_no_launch_or_termination_primitives():
    import ast

    tree = ast.parse(read("edge_attach.py"))
    banned_attrs = {"launch", "launch_persistent_context", "close", "terminate", "kill"}
    banned_imports = {"subprocess", "shutil", "os.system"}

    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            assert node.attr not in banned_attrs, f"edge_attach.py calls .{node.attr}"
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names = [a.name for a in node.names]
            mod = getattr(node, "module", "") or ""
            for n in names:
                full = f"{mod}.{n}".strip(".")
                assert n not in banned_imports, f"edge_attach.py imports {n}"
                assert full not in banned_imports, f"edge_attach.py imports {full}"
                assert n not in ("subprocess", "shutil"), f"edge_attach.py imports {n}"


def test_attach_only_adapter_has_no_launcher_start():
    text = read("managed_edge.py")
    # start() must hand off to launcher.start() only on the explicit launch path.
    assert "if self.attach_only:" in text
    assert "info = self.attach_existing()" in text


def test_existing_profile_paths_are_never_mutated_by_attach():
    text = read("edge_attach.py")
    for token in ("mkdir", "rmdir", "unlink", "copyfile", "copytree", "rename"):
        assert token not in text, f"edge_attach.py must not modify profile data ({token})"


# --- DevToolsActivePort / websocket route --------------------------------


def test_discover_ws_endpoint_reads_devtools_active_port():
    from opencode_bridge.edge_attach import discover_ws_endpoint

    with tempfile.TemporaryDirectory() as d:
        Path(d, "DevToolsActivePort").write_text(
            "54321\n/devtools/browser/abc-123\n", encoding="utf-8"
        )
        got = discover_ws_endpoint(d)

    assert got["ok"] is True
    assert got["port"] == 54321
    assert got["ws_endpoint"] == "ws://127.0.0.1:54321/devtools/browser/abc-123"


def test_discover_ws_endpoint_missing_file_is_blocked():
    from opencode_bridge.edge_attach import discover_ws_endpoint

    with tempfile.TemporaryDirectory() as d:
        got = discover_ws_endpoint(d)
    assert got["ok"] is False
    assert got["reason"] == "devtools_active_port_absent"


def test_discover_ws_endpoint_malformed_is_blocked():
    from opencode_bridge.edge_attach import discover_ws_endpoint

    with tempfile.TemporaryDirectory() as d:
        Path(d, "DevToolsActivePort").write_text("not-a-port\n", encoding="utf-8")
        got = discover_ws_endpoint(d)
    assert got["ok"] is False
    assert got["reason"] == "devtools_active_port_malformed"


class _Page:
    def __init__(self, url, text="Palmistry Project\n", links=1):
        self._url = url
        self._text = text
        self._links = links
        self.navigations = []

    @property
    def url(self):
        return self._url

    def title(self):
        return "Palmistry Project"

    def goto(self, url, **kw):
        self.navigations.append(url)
        self._url = url

    def inner_text(self, sel):
        return self._text

    def content(self):
        return self._text

    def query_selector_all(self, sel):
        return [object() for _ in range(self._links)]


class _Ctx:
    def __init__(self, pages):
        self.pages = pages


class _Browser:
    def __init__(self, contexts):
        self.contexts = contexts


class _Chromium:
    """connect_over_cdp works only for ws:// endpoints (toggle-enabled route)."""

    def __init__(self, browser, http_error=True):
        self._browser = browser
        self.calls = []
        self.launch_calls = []
        self._http_error = http_error

    def connect_over_cdp(self, endpoint, **kw):
        self.calls.append(endpoint)
        if self._http_error and not endpoint.startswith("ws://"):
            raise RuntimeError("connect ECONNREFUSED 127.0.0.1:9224")
        return self._browser

    def launch(self, *a, **k):
        self.launch_calls.append((a, k))
        raise AssertionError("must not launch")

    def launch_persistent_context(self, *a, **k):
        self.launch_calls.append((a, k))
        raise AssertionError("must not launch")


class _PW:
    def __init__(self, chromium):
        self.chromium = chromium
        self.stopped = 0

    def stop(self):
        self.stopped += 1


def test_attach_falls_back_to_devtools_active_port_websocket():
    from opencode_bridge.edge_attach import attach_existing_edge

    page = _Page("https://chatgpt.com/g/g-p-6ae87c1e48b08191a2cd33139c40639f/project")
    chromium = _Chromium(_Browser([_Ctx([page])]))
    pw = _PW(chromium)

    with tempfile.TemporaryDirectory() as d:
        Path(d, "DevToolsActivePort").write_text(
            "54321\n/devtools/browser/abc-123\n", encoding="utf-8"
        )
        r = attach_existing_edge(
            cdp_url="http://127.0.0.1:9224",
            playwright=pw,
            user_data_dir=d,
            wait_seconds=0.1,
        )

    assert r["ok"] is True
    assert r["discovery"] == "devtools_active_port"
    assert r["attempted_endpoints"] == [
        "http://127.0.0.1:9224",
        "ws://127.0.0.1:54321/devtools/browser/abc-123",
    ]
    assert chromium.launch_calls == []
    assert page.navigations == []  # project tab reused as-is


def test_attach_without_devtools_active_port_is_blocked_not_launched():
    from opencode_bridge.edge_attach import attach_existing_edge

    chromium = _Chromium(_Browser([]))
    pw = _PW(chromium)

    with tempfile.TemporaryDirectory() as d:
        r = attach_existing_edge(
            cdp_url="http://127.0.0.1:9224",
            playwright=pw,
            user_data_dir=d,
            wait_seconds=0.1,
        )

    assert r["ok"] is False
    assert r["reason"] == "cdp_connect_failed"
    assert "ECONNREFUSED 127.0.0.1:9224" in r["error"]
    assert r["devtools_active_port"]["reason"] == "devtools_active_port_absent"
    assert chromium.launch_calls == []


def test_ws_endpoint_skips_http_discovery():
    from opencode_bridge.edge_attach import attach_existing_edge

    page = _Page("https://chatgpt.com/g/g-p-6ae87c1e48b08191a2cd33139c40639f/project")
    chromium = _Chromium(_Browser([_Ctx([page])]))
    pw = _PW(chromium)

    r = attach_existing_edge(
        cdp_url="ws://127.0.0.1:54321/devtools/browser/abc-123",
        playwright=pw,
        wait_seconds=0.1,
    )

    assert r["ok"] is True
    assert r["discovery"] == "websocket"
    assert chromium.calls == ["ws://127.0.0.1:54321/devtools/browser/abc-123"]


# --- graceful disconnect -------------------------------------------------


def test_cdp_adapter_stop_disconnects_without_closing_borrowed_context():
    from unittest.mock import patch

    from opencode_bridge.managed_edge import CdpEdgeAdapter, ManagedEdgeLauncher

    page = _Page("https://chatgpt.com/g/g-p-6ae87c1e48b08191a2cd33139c40639f/project")
    page.context = _Ctx([page])
    browser = _Browser([_Ctx([page])])
    chromium = _Chromium(browser, http_error=False)
    pw = _PW(chromium)

    # Owned path: the adapter starts Playwright itself via connect_over_cdp.
    with patch("playwright.sync_api.sync_playwright") as mock_sync:
        mock_sync.return_value.start.return_value = pw
        adapter = CdpEdgeAdapter(launcher=ManagedEdgeLauncher(profile_dir="unused"), attach_only=True)
        info = adapter.attach_existing()
        assert info["ok"] is True
        adapter.stop()

    assert pw.stopped == 1
    assert chromium.launch_calls == []


# --- no forced termination / profile preservation ------------------------


class _RecordingLauncher:
    """Launcher stand-in that records any attempt to start/stop Edge."""

    def __init__(self, profile_dir):
        self.profile_dir = str(Path(profile_dir))
        self.port = 9224
        self._process = None
        self.started = 0
        self.stopped = 0

    def cdp_url(self):
        return "http://127.0.0.1:9224"

    def is_healthy(self):
        return False

    def start(self):
        self.started += 1
        raise AssertionError("attach-only must never start Edge")

    def stop(self):
        self.stopped += 1
        raise AssertionError("attach-only must never stop/terminate Edge")


def test_attach_only_terminate_managed_never_stops_the_borrowed_browser():
    from unittest.mock import patch

    from opencode_bridge.managed_edge import CdpEdgeAdapter

    page = _Page("https://chatgpt.com/g/g-p-6ae87c1e48b08191a2cd33139c40639f/project")
    chromium = _Chromium(_Browser([_Ctx([page])]), http_error=False)
    pw = _PW(chromium)
    launcher = _RecordingLauncher(profile_dir="unused")

    with patch("playwright.sync_api.sync_playwright") as mock_sync:
        mock_sync.return_value.start.return_value = pw
        adapter = CdpEdgeAdapter(launcher=launcher, attach_only=True)
        assert adapter.attach_existing()["ok"] is True
        adapter.terminate_managed()  # would raise if launcher.stop() were called
        adapter.stop()  # idempotent after terminate

    assert launcher.started == 0
    assert launcher.stopped == 0
    assert chromium.launch_calls == []


def test_attach_only_start_reports_blocked_and_creates_no_profile_dir(tmp_path):
    from unittest.mock import patch

    from opencode_bridge.managed_edge import CdpEdgeAdapter, ManagedEdgeError

    profile = tmp_path / "must-not-exist"
    launcher = _RecordingLauncher(profile_dir=profile)
    chromium = _Chromium(_Browser([]))  # no endpoint reachable
    pw = _PW(chromium)

    with patch("playwright.sync_api.sync_playwright") as mock_sync:
        mock_sync.return_value.start.return_value = pw
        adapter = CdpEdgeAdapter(launcher=launcher, attach_only=True, user_data_dir=str(tmp_path))
        try:
            adapter.start()
        except ManagedEdgeError as exc:
            msg = str(exc)
        else:  # pragma: no cover - failure path must not be silent
            raise AssertionError("attach-only start() must raise when CDP is missing")

    assert "CDP attach failed (cdp_connect_failed)" in msg
    assert launcher.started == 0
    assert chromium.launch_calls == []
    assert not profile.exists(), "attach must not create a user-data directory"


def test_launcher_stop_is_noop_when_it_spawned_nothing():
    from opencode_bridge.managed_edge import ManagedEdgeLauncher

    launcher = ManagedEdgeLauncher(profile_dir="unused")
    assert launcher._process is None
    launcher.stop()  # must not raise / must not touch any process
    assert launcher._process is None


def test_no_forced_termination_primitives_in_attach_or_launch_paths():
    text_attach = read("edge_attach.py")
    text_managed = read("managed_edge.py")
    for token in ("psutil", "taskkill", "Stop-Process", "killall", "/F /PID", "os.kill"):
        assert token not in text_attach, f"edge_attach.py must not contain {token!r}"
        assert token not in text_managed, f"managed_edge.py must not contain {token!r}"
    # The only terminate/kill calls are the launcher's own spawned child.
    assert text_managed.count(".terminate()") == 1
    assert text_managed.count(".kill()") == 1
