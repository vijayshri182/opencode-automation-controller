import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest

try:
    import playwright  # noqa
    HAS_PW = True
except Exception:
    HAS_PW = False

from opencode_bridge.browser_automation import PlaywrightEdgeAdapter


@pytest.mark.skipif(not HAS_PW, reason="Playwright not installed")
def test_real_edge_launch():
    with tempfile.TemporaryDirectory() as d:
        adapter = PlaywrightEdgeAdapter(profile_dir=d, headless=True)
        assert adapter.start() is True
        assert adapter.current_url() in ("about:blank", "")
        adapter.stop()