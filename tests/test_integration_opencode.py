import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest

from opencode_bridge.opencode_adapter import OpenCodeAdapter, OpenCodeError


def _server_available():
    try:
        a = OpenCodeAdapter()
        h = a.health()
        return bool(h and h.get("healthy"))
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _server_available(), reason="OpenCode server not available")


def test_integration_health_and_version():
    a = OpenCodeAdapter()
    h = a.health()
    assert h["healthy"] is True
    assert "version" in h


def test_integration_real_task():
    a = OpenCodeAdapter()
    s = a.create_session(title="integration-test")
    sid = s["id"]
    a.send_prompt_async(sid, "Reply with exactly: INTEGRATION_OK", model={"providerID": "opencode-go", "modelID": "beam-free"})
    deadline = time.time() + 120
    final = ""
    while time.time() < deadline:
        msgs = a.get_messages(sid, limit=50)
        final = a.extract_final_assistant(msgs)
        if final:
            break
        time.sleep(2)
    assert final and "INTEGRATION_OK" in final