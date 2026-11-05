import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from opencode_bridge.browser_automation import PlaywrightEdgeAdapter
from opencode_bridge.managed_edge import ManagedEdgeLauncher


def test_playwright_launch_uses_chromium_sandbox():
    captured = {}

    class FakePW:
        class chromium:
            @staticmethod
            def launch_persistent_context(*args, **kwargs):
                captured["args"] = args
                captured["kwargs"] = kwargs
                ctx = MagicMock()
                ctx.pages = []
                return ctx

    with patch("playwright.sync_api.sync_playwright") as mock_sync:
        mock_sync.return_value.start.return_value = FakePW()
        adapter = PlaywrightEdgeAdapter(profile_dir="C:\\tmp\\prof", headless=True)
        adapter.start()
        kwargs = captured["kwargs"]
        assert kwargs.get("chromium_sandbox") is True, "chromium_sandbox must be True to avoid --no-sandbox"
        # args list must not contain --no-sandbox
        launch_args = kwargs.get("args") or []
        assert "--no-sandbox" not in launch_args
        adapter.stop()


def test_managed_edge_launcher_does_not_add_no_sandbox():
    launcher = ManagedEdgeLauncher(profile_dir="C:\\tmp\\prof", port=9999)
    # inspect the constructed args by calling start's arg build indirectly: replicate
    import subprocess
    # Monkeypatch Popen to capture args
    captured = {}
    def fake_popen(args, **kw):
        captured["args"] = args
        class P:
            def poll(self): return None
        return P()
    with patch("subprocess.Popen", side_effect=fake_popen):
        with patch.object(launcher, "is_healthy", return_value=False):
            try:
                launcher.start()
            except Exception:
                pass
    args = captured.get("args", [])
    assert "--no-sandbox" not in args, "ManagedEdgeLauncher must not add --no-sandbox"
    assert any("remote-debugging-port" in a for a in args)