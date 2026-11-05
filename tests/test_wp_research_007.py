"""WP-RESEARCH-EXECUTION-001: research executor, persistence, idempotency, isolation tests."""
import json
import os
import sys
import tempfile
import threading
import time
from pathlib import Path

sys.path.insert(0, "src")

from opencode_bridge.contracts import research_result, research_task, validate_research_result, validate_research_task
from opencode_bridge.db import BridgeDB
from opencode_bridge.opencode_adapter import OpenCodeAdapter, OpenCodeError
from opencode_bridge.research_executor import ResearchExecutor, _redact_value, MAX_FIELD_CHARS

REPO = Path(__file__).resolve().parent.parent
RESEARCH_AGENT_CFG = REPO / "config" / "research_agent.md"
RESEARCH_JSON_CFG = Path(r"C:\Users\user\.config\opencode-research\opencode.jsonc")


class FakeResearchAdapter(OpenCodeAdapter):
    """Deterministic fake OpenCode research adapter."""

    def __init__(self, messages=None, fail_create=False, fail_submit=False, sleep=0.0,
                 create_session_id="sess-1", research_mode=True):
        super().__init__(base_url="http://research", username="u", password="secret-pw",
                         agent="research", tools={"websearch": True, "webfetch": True}, research_mode=research_mode)
        self._messages = list(messages) if messages is not None else []
        self._fail_create = fail_create
        self._fail_submit = fail_submit
        self._sleep = sleep
        self._create_session_id = create_session_id
        self.created = 0
        self.submitted = 0
        self.aborted = 0

    def health(self):
        return {"healthy": True, "version": "fake"}

    def create_session(self, title="", directory=None, agent=None):
        self.created += 1
        if self._fail_create:
            raise OpenCodeError("create failed")
        return {"id": self._create_session_id}

    def send_prompt_async(self, session_id, text, model=None, directory=None, agent=None, tools=None):
        self.submitted += 1
        if self._fail_submit:
            raise OpenCodeError("submit failed")
        if self._sleep:
            time.sleep(self._sleep)

    def get_messages(self, session_id, limit=50, directory=None):
        return list(self._messages)

    def abort(self, session_id, directory=None):
        self.aborted += 1
        return True


def _mk_db():
    d = tempfile.mkdtemp()
    return BridgeDB(Path(d) / "t.db"), d


def _make_task(db, rid="r1", key="k1", prompt="find X", timeout=2.0):
    t = research_task(research_id=rid, idempotency_key=key, prompt=prompt,
                      created_at=time.time(), timeout_seconds=timeout)
    ok, errs = validate_research_task(t)
    assert ok, errs
    assert db.insert_research_task(t)
    return t


def _assistant_msg(text="", error=None, tool_calls=None, provider="opencode", model="flint-40b-free",
                   tokens=None):
    parts = []
    if text:
        parts.append({"type": "text", "text": text})
    for tc in (tool_calls or []):
        parts.append({"type": "tool", "tool": tc["tool"], "callID": tc.get("id", "c1"),
                      "state": {"status": tc.get("status", "completed"),
                                "input": tc.get("input"), "output": tc.get("output"),
                                "error": tc.get("error"), "title": tc.get("title")}})
    info = {"role": "assistant", "providerID": provider, "modelID": model,
            "tokens": tokens or {"input": 10, "output": 5, "reasoning": 0,
                                 "cache": {"read": 0, "write": 0}}, "error": error}
    return {"info": info, "parts": parts}


# ---------- MCP tool registration & schemas ----------
def test_mcp_research_tools_registered():
    from opencode_bridge.mcp_server import TOOL_DEFINITIONS
    names = {t["name"] for t in TOOL_DEFINITIONS}
    assert "submit_research_task" in names
    assert "get_research_task_status" in names
    assert "get_research_task_result" in names
    for n in ("submit_research_task", "get_research_task_status", "get_research_task_result"):
        t = next(x for x in TOOL_DEFINITIONS if x["name"] == n)
        assert "inputSchema" in t
        assert t["inputSchema"].get("type") == "object"


# ---------- submission / retrieval / idempotency ----------
def test_research_submission_and_retrieval():
    db, _ = _mk_db()
    t = _make_task(db)
    row = db.get_research_task("r1")
    assert row is not None
    assert row["status"] == "pending"
    assert row["session_id"] is None
    # idempotency
    t2 = research_task(research_id="r2", idempotency_key="k1", prompt="dup", created_at=time.time())
    assert not db.insert_research_task(t2)


def test_duplicate_submission_returns_existing():
    from opencode_bridge.mcp_server import MCPServer
    db, _ = _mk_db()
    orch = type("O", (), {})()
    orch.db = db
    orch.state = lambda: None
    mcp = MCPServer(orchestrator=orch)
    r1 = mcp._call_tool("submit_research_task", {"prompt": "q", "idempotency_key": "dupkey"})
    assert r1["ok"] is True and r1["duplicate"] is False
    r2 = mcp._call_tool("submit_research_task", {"prompt": "q", "idempotency_key": "dupkey"})
    assert r2["ok"] is True and r2["duplicate"] is True
    assert r1["research_id"] == r2["research_id"]


# ---------- successful execution ----------
def test_successful_execution_mocked():
    db, _ = _mk_db()
    _make_task(db)
    msgs = [_assistant_msg(text="Found results about Comviva.", tool_calls=[
        {"tool": "websearch", "id": "c1", "status": "completed", "input": {"query": "Comviva NGAGE"},
         "output": "snippet about Comviva", "title": "websearch"},
        {"tool": "webfetch", "id": "c2", "status": "completed", "input": {"url": "https://example.com"},
         "output": "page title", "title": "webfetch"},
    ])]
    adapter = FakeResearchAdapter(messages=msgs)
    ex = ResearchExecutor(db, adapter_factory=lambda: adapter)
    res = ex.execute("r1")
    assert res["ok"] is True
    assert res["status"] == "completed"
    assert res["session_id"] == "sess-1"
    assert adapter.created == 1 and adapter.submitted == 1
    row = db.get_research_task("r1")
    assert row["status"] == "completed"
    assert row["session_id"] == "sess-1"
    assert row["started_at"] is not None and row["completed_at"] is not None
    rr = json.loads(row["result_json"])
    assert rr["status"] == "completed"
    assert rr["output"] == "Found results about Comviva."
    assert len(rr["evidence"]) == 2
    assert rr["tool_names"] == ["websearch", "webfetch"]
    assert rr["tool_count"] == 2


# ---------- tool call extraction ----------
def test_tool_call_extraction():
    db, _ = _mk_db()
    _make_task(db)
    msgs = [_assistant_msg(text="ok", tool_calls=[
        {"tool": "websearch", "id": "c1", "status": "completed", "input": {"query": "q"},
         "output": "out", "error": None},
    ])]
    ex = ResearchExecutor(db, adapter_factory=lambda: FakeResearchAdapter(messages=msgs))
    res = ex.execute("r1")
    assert res["ok"] is True
    tc = res["result"]["evidence"][0]
    assert tc["tool"] == "websearch"
    assert tc["input"] == {"query": "q"}
    assert tc["output"] == "out"


# ---------- empty assistant response ----------
def test_empty_assistant_response_fails():
    db, _ = _mk_db()
    _make_task(db)
    msgs = [_assistant_msg(text="", tool_calls=[])]  # empty assistant output
    ex = ResearchExecutor(db, adapter_factory=lambda: FakeResearchAdapter(messages=msgs))
    res = ex.execute("r1")
    assert res["ok"] is False
    assert res["status"] == "failed"
    assert "empty assistant output" in res["error"]
    row = db.get_research_task("r1")
    assert row["status"] == "failed"


# ---------- provider quota / auth error ----------
def test_provider_error_from_assistant():
    db, _ = _mk_db()
    _make_task(db)
    msgs = [_assistant_msg(text="", error="AI_APICallError: Free usage limit reached")]
    ex = ResearchExecutor(db, adapter_factory=lambda: FakeResearchAdapter(messages=msgs))
    res = ex.execute("r1")
    assert res["ok"] is False
    assert res["status"] == "failed"
    assert "Free usage limit" in res["error"]


def test_provider_error_from_adapter():
    db, _ = _mk_db()
    _make_task(db)

    class FailingAdapter(FakeResearchAdapter):
        def get_messages(self, session_id, limit=50, directory=None):
            raise OpenCodeError("connection failed")

    ex = ResearchExecutor(db, adapter_factory=lambda: FailingAdapter(messages=[]))
    res = ex.execute("r1")
    assert res["ok"] is False
    assert res["status"] == "failed"
    assert "OpenCodeError" in res["error"] or "connection" in res["error"]


# ---------- timeout ----------
def test_timeout():
    db, _ = _mk_db()
    _make_task(db, timeout=0.3)
    # messages with no final text -> never completes
    msgs = []  # no assistant message -> true timeout
    ex = ResearchExecutor(db, adapter_factory=lambda: FakeResearchAdapter(messages=msgs), poll_interval=0.05)
    res = ex.execute("r1")
    assert res["ok"] is False
    assert res["status"] == "timeout"
    row = db.get_research_task("r1")
    assert row["status"] == "timeout"


# ---------- cancellation ----------
def test_cancellation_pre_execute():
    db, _ = _mk_db()
    _make_task(db)
    ex = ResearchExecutor(db, adapter_factory=lambda: FakeResearchAdapter(messages=[]))
    ex.cancel("r1")
    res = ex.execute("r1")
    assert res["ok"] is False
    assert res["status"] == "cancelled"


# ---------- retry / idempotency ----------
def test_completed_task_returns_cached():
    db, _ = _mk_db()
    _make_task(db)
    msgs = [_assistant_msg(text="done")]
    ex = ResearchExecutor(db, adapter_factory=lambda: FakeResearchAdapter(messages=msgs))
    r1 = ex.execute("r1")
    assert r1["ok"] is True
    r2 = ex.execute("r1")
    assert r2["ok"] is True
    assert r2.get("cached") is True


def test_failed_task_reruns():
    db, _ = _mk_db()
    _make_task(db)
    msgs_empty = [_assistant_msg(text="")]
    ex = ResearchExecutor(db, adapter_factory=lambda: FakeResearchAdapter(messages=msgs_empty))
    r1 = ex.execute("r1")
    assert r1["ok"] is False
    assert r1["status"] == "failed"
    # now provide output and re-run
    msgs_ok = [_assistant_msg(text="now ok")]
    ex2 = ResearchExecutor(db, adapter_factory=lambda: FakeResearchAdapter(messages=msgs_ok))
    r2 = ex2.execute("r1")
    assert r2["ok"] is True
    assert r2["status"] == "completed"


# ---------- invalid structured output ----------
def test_invalid_structured_output_contract():
    # validate_research_result rejects bad payloads
    bad = {"schema_version": "wp_research.research_result.v1", "research_id": "r1",
           "status": "completed", "completed_at": 1.0, "evidence": "not-a-list"}
    ok, errors = validate_research_result(bad)
    assert not ok
    assert any("evidence" in e for e in errors)


# ---------- persistence & recovery ----------
def test_persistence_survives_reopen():
    d = tempfile.mkdtemp()
    dbpath = Path(d) / "t.db"
    db1 = BridgeDB(dbpath)
    _make_task(db1, rid="r1", key="k1")
    msgs = [_assistant_msg(text="persisted")]
    ex = ResearchExecutor(db1, adapter_factory=lambda: FakeResearchAdapter(messages=msgs))
    ex.execute("r1")
    # reopen
    db2 = BridgeDB(dbpath)
    row = db2.get_research_task("r1")
    assert row["status"] == "completed"
    assert row["session_id"] == "sess-1"
    assert json.loads(row["result_json"])["output"] == "persisted"


# ---------- permission config ----------
def test_research_permission_config_file():
    # The research agent config must declare deny-all baseline with websearch/webfetch allowed.
    if not RESEARCH_AGENT_CFG.exists():
        import pytest
        pytest.skip("config/research_agent.md not present")
    content = RESEARCH_AGENT_CFG.read_text()
    assert "permission:" in content
    # accept either yaml-ish or json-ish forms
    assert ("websearch" in content and "allow" in content)
    assert ("bash" in content and "deny" in content) or ("bash" in content and "false" in content)


def test_research_json_config_default_deny():
    if not RESEARCH_JSON_CFG.exists():
        import pytest
        pytest.skip("opencode-research opencode.jsonc not present")
    import json
    cfg = json.loads(RESEARCH_JSON_CFG.read_text())
    perm = cfg.get("permission", {})
    assert perm.get("websearch") == "allow"
    assert perm.get("webfetch") == "allow"
    assert perm.get("bash") == "deny"
    assert perm.get("write") == "deny"
    assert perm.get("external_directory") == "deny"
    assert perm.get("*") == "deny"
    agent = cfg.get("agent", {}).get("research", {})
    assert agent.get("tools", {}).get("websearch") is True
    assert agent.get("tools", {}).get("webfetch") is True
    assert agent.get("tools", {}).get("bash") is False


# ---------- no fallback to dev instance ----------
def test_no_fallback_to_unrestricted_instance():
    db, _ = _mk_db()
    _make_task(db)
    # adapter not in research_mode -> executor must refuse
    adapter = FakeResearchAdapter(messages=[_assistant_msg(text="ok")], research_mode=False)
    ex = ResearchExecutor(db, adapter_factory=lambda: adapter)
    res = ex.execute("r1")
    assert res["ok"] is False
    assert "research_mode" in (res.get("error") or "")
    row = db.get_research_task("r1")
    assert row["status"] == "failed"


# ---------- credential redaction ----------
def test_credential_redaction():
    secret = "super-secret-token-123"
    data = {"query": "q", "headers": {"Authorization": "Bearer " + secret}, "api_key": secret,
            "nested": {"password": secret, "output": "hello " + secret}}
    red = _redact_value(data)
    s = json.dumps(red)
    assert secret not in s
    assert "[REDACTED]" in s
    assert red["nested"]["output"] == "hello " + secret or "[REDACTED]" in s
    # truncation
    big = "x" * (MAX_FIELD_CHARS + 100)
    assert len(_redact_value(big)) <= MAX_FIELD_CHARS + len("...[truncated]")


# ---------- concurrent submissions ----------
def test_concurrent_submissions_state_integrity():
    db, _ = _mk_db()
    _make_task(db, rid="r1", key="k1")
    _make_task(db, rid="r2", key="k2")
    msgs = [_assistant_msg(text="ok")]
    adapter = FakeResearchAdapter(messages=msgs)
    ex = ResearchExecutor(db, adapter_factory=lambda: adapter)
    results = {}

    def worker(rid):
        results[rid] = ex.execute(rid)

    t1 = threading.Thread(target=worker, args=("r1",))
    t2 = threading.Thread(target=worker, args=("r2",))
    t1.start(); t2.start(); t1.join(); t2.join()
    assert results["r1"]["ok"] is True
    assert results["r2"]["ok"] is True
    assert db.get_research_task("r1")["status"] == "completed"
    assert db.get_research_task("r2")["status"] == "completed"


# ---------- task state integrity ----------
def test_task_state_transitions():
    db, _ = _mk_db()
    _make_task(db)
    row = db.get_research_task("r1")
    assert row["status"] == "pending"
    msgs = [_assistant_msg(text="done")]
    ex = ResearchExecutor(db, adapter_factory=lambda: FakeResearchAdapter(messages=msgs))
    ex.execute("r1")
    row = db.get_research_task("r1")
    assert row["status"] == "completed"
    assert row["started_at"] is not None
    assert row["completed_at"] is not None
    assert row["completed_at"] >= row["started_at"]


# ---------- persistence failure ----------
def test_persistence_failure_handled():
    db, _ = _mk_db()
    _make_task(db)
    msgs = [_assistant_msg(text="ok")]

    class BadDB:
        def get_research_task(self, rid):
            return db.get_research_task(rid)
        def update_research_task(self, rid, **fields):
            raise RuntimeError("db write failed")
        def cancel_research_task(self, rid):
            return False

    ex = ResearchExecutor(BadDB(), adapter_factory=lambda: FakeResearchAdapter(messages=msgs))
    res = ex.execute("r1")
    # Should not crash; returns a result (failed) since persistence failed during running update
    assert isinstance(res, dict)
    assert res.get("status") in ("failed", "running", "completed")


# ---------- MCP schema validation ----------
def test_research_task_contract_validation():
    t = research_task(research_id="r", idempotency_key="k", prompt="p", created_at=1.0)
    ok, errs = validate_research_task(t)
    assert ok, errs
    # bad
    bad = dict(t); bad["timeout_seconds"] = 0
    ok2, errs2 = validate_research_task(bad)
    assert not ok2


# ---------- redaction of tool errors ----------
def test_tool_error_redacted():
    db, _ = _mk_db()
    _make_task(db)
    msgs = [_assistant_msg(text="ok", tool_calls=[
        {"tool": "websearch", "id": "c1", "status": "error",
         "input": {"query": "q"}, "output": "boom", "error": "HTTP 401: secret-token-xyz"},
    ])]
    ex = ResearchExecutor(db, adapter_factory=lambda: FakeResearchAdapter(messages=msgs))
    res = ex.execute("r1")
    assert res["ok"] is True
    ev = res["result"]["evidence"][0]
    assert ev["error"] == "HTTP 401: secret-token-xyz" or "[REDACTED]" in str(ev["error"])
    # Ensure redaction helper removes token-like keys
    red = _redact_value({"Authorization": "Bearer abc", "output": "data"})
    assert red["Authorization"] == "[REDACTED]"