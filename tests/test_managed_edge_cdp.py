import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest

try:
    import playwright  # noqa
    HAS_PW = True
except Exception:
    HAS_PW = False

from opencode_bridge.managed_edge import ManagedEdgeLauncher, CdpEdgeAdapter


@pytest.mark.skipif(not HAS_PW, reason="Playwright not installed")
def test_managed_edge_cdp():
    launcher = ManagedEdgeLauncher(profile_dir=".edge-profile-automation-test", port=9225)
    adapter = CdpEdgeAdapter(launcher=launcher, conversation_url="https://chatgpt.com/", headless=True)
    assert adapter.start() is True
    assert "chatgpt.com" in adapter.current_url()
    adapter.stop()
    launcher.stop()