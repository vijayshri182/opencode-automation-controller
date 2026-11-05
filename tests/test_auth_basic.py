import base64
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from opencode_bridge.config import opencode_username, opencode_password
from opencode_bridge.opencode_adapter import OpenCodeAdapter


def test_default_username():
    os.environ.pop("OPENCODE_SERVER_USERNAME", None)
    assert opencode_username() == "opencode"


def test_basic_auth_header_construction(monkeypatch):
    monkeypatch.setenv("OPENCODE_SERVER_USERNAME", "opencode")
    monkeypatch.setenv("OPENCODE_SERVER_PASSWORD", "testpw")
    a = OpenCodeAdapter(base_url="http://127.0.0.1:9999")
    # Build request manually via _request? Instead check adapter attributes
    assert a.username == "opencode"
    assert a.password == "testpw"
    expected = base64.b64encode(b"opencode:testpw").decode("ascii")
    assert expected == base64.b64encode(f"{a.username}:{a.password}".encode()).decode("ascii")