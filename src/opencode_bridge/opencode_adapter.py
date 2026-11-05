import json
import logging
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

from .config import (opencode_base_url, opencode_password, opencode_username,
                     opencode_timeout, opencode_max_retries, opencode_retry_backoff)

logger = logging.getLogger("opencode_bridge.adapter")


class OpenCodeError(Exception):
    """Base error for OpenCode adapter failures."""


class OpenCodeConnectionError(OpenCodeError):
    pass


class OpenCodeAuthError(OpenCodeError):
    pass


class OpenCodeTimeoutError(OpenCodeError):
    pass


class OpenCodeAPIError(OpenCodeError):
    pass


class OpenCodeAdapter:
    """HTTP client for the official OpenCode server API."""

    def __init__(self, base_url: str = None, username: str = None, password: str = None, timeout: float = None,
                 agent: Optional[str] = None, tools: Optional[Dict[str, bool]] = None,
                 research_mode: bool = False):
        self.base_url = (base_url or opencode_base_url()).rstrip("/")
        self.username = username if username is not None else opencode_username()
        self.password = password if password is not None else opencode_password()
        self.timeout = timeout if timeout is not None else opencode_timeout()
        self.agent = agent
        self.tools = tools
        self.research_mode = research_mode

    def _request(self, method: str, path: str, body: Any = None, retry: bool = False, query: Optional[Dict[str, str]] = None) -> Any:
        url = self.base_url + path
        if query:
            import urllib.parse as _up
            url = url + "?" + _up.urlencode({k: v for k, v in query.items() if v is not None})
        data = None
        headers = {"Accept": "application/json"}
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        attempts = opencode_max_retries() if retry else 1
        last_exc = None
        for attempt in range(1, attempts + 1):
            req = urllib.request.Request(url, data=data, headers=headers, method=method)
            if self.password:
                import base64
                token = base64.b64encode(f"{self.username}:{self.password}".encode()).decode()
                req.add_header("Authorization", f"Basic {token}")
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    raw = resp.read().decode("utf-8", errors="replace")
                    if not raw.strip():
                        return None
                    try:
                        return json.loads(raw)
                    except json.JSONDecodeError:
                        return raw
            except urllib.error.HTTPError as e:
                body_text = e.read().decode("utf-8", errors="replace")
                if e.code in (401, 403):
                    raise OpenCodeAuthError(f"HTTP {e.code} {e.reason}: {body_text[:300]}")
                raise OpenCodeAPIError(f"HTTP {e.code} {e.reason}: {body_text[:300]}")
            except urllib.error.URLError as e:
                last_exc = OpenCodeConnectionError(f"connection failed: {e.reason}")
                logger.warning("OpenCode connection attempt %d/%d failed: %s", attempt, attempts, e.reason)
            except TimeoutError as e:
                last_exc = OpenCodeTimeoutError(f"request timed out after {self.timeout}s")
                logger.warning("OpenCode timeout attempt %d/%d", attempt, attempts)
            except Exception as e:
                last_exc = OpenCodeError(f"request failed: {e}")
                logger.warning("OpenCode request error attempt %d/%d: %s", attempt, attempts, e)
            if attempt < attempts:
                time.sleep(opencode_retry_backoff() * attempt)
        raise last_exc if last_exc else OpenCodeError("request failed")

    def health(self) -> Dict[str, Any]:
        return self._request("GET", "/global/health", retry=True)

    def create_session(self, title: str = "", directory: Optional[str] = None, agent: Optional[str] = None) -> Dict[str, Any]:
        body = {"title": title}
        eff_agent = agent if agent is not None else getattr(self, "agent", None)
        if eff_agent:
            body["agent"] = eff_agent
        query = {"directory": directory} if directory else None
        return self._request("POST", "/session", body, retry=True, query=query)

    def send_prompt_async(self, session_id: str, text: str, model: Optional[Dict[str, str]] = None, directory: Optional[str] = None,
                         agent: Optional[str] = None, tools: Optional[Dict[str, bool]] = None) -> None:
        body: Dict[str, Any] = {"parts": [{"type": "text", "text": text}]}
        if model:
            body["model"] = model
        eff_agent = agent if agent is not None else getattr(self, "agent", None)
        if eff_agent:
            body["agent"] = eff_agent
        eff_tools = tools if tools is not None else getattr(self, "tools", None)
        if eff_tools:
            body["tools"] = eff_tools
        query = {"directory": directory} if directory else None
        self._request("POST", f"/session/{session_id}/prompt_async", body, query=query)

    def get_messages(self, session_id: str, limit: int = 50, directory: Optional[str] = None) -> List[Dict[str, Any]]:
        query = {"limit": str(limit)}
        if directory:
            query["directory"] = directory
        res = self._request("GET", f"/session/{session_id}/message", retry=True, query=query)
        if isinstance(res, list):
            return res
        if isinstance(res, dict) and "messages" in res:
            return res["messages"]
        return []

    def abort(self, session_id: str, directory: Optional[str] = None) -> bool:
        try:
            query = {"directory": directory} if directory else None
            self._request("POST", f"/session/{session_id}/abort", query=query)
            return True
        except OpenCodeError:
            return False

    @staticmethod
    def extract_final_assistant(messages: List[Dict[str, Any]]) -> str:
        # Messages are {info, parts}; find last assistant message text.
        last = ""
        for m in messages:
            info = m.get("info", {}) if isinstance(m, dict) else {}
            role = info.get("role") or m.get("role")
            if role != "assistant":
                continue
            parts = m.get("parts", [])
            texts = []
            for p in parts:
                if isinstance(p, dict) and p.get("type") == "text":
                    texts.append(p.get("text", ""))
            if texts:
                last = "\n".join(texts)
        return last


class MockOpenCodeAdapter(OpenCodeAdapter):
    """Deterministic adapter for tests and offline development."""

    def __init__(self, response_text: str = "MOCK_OPENCODE_OK", delay: float = 0.0, fail: bool = False, timeout_fail: bool = False):
        super().__init__(base_url="http://mock", username="mock", password="")
        self.response_text = response_text
        self.delay = delay
        self.fail = fail
        self.timeout_fail = timeout_fail
        self._sessions = {}
        self._counter = 0

    def health(self):
        return {"healthy": True, "version": "mock"}

    def create_session(self, title="", directory=None, agent=None):
        self._counter += 1
        sid = f"mock-session-{self._counter}"
        self._sessions[sid] = {"title": title, "directory": directory, "agent": agent or self.agent, "messages": []}
        return {"id": sid}

    def send_prompt_async(self, session_id, text, model=None, directory=None, agent=None, tools=None):
        if self.fail:
            raise OpenCodeError("mock failure")
        if self.timeout_fail:
            time.sleep(100)
        if self.delay:
            time.sleep(self.delay)
        self._sessions[session_id]["messages"].append({
            "info": {"role": "assistant"},
            "parts": [{"type": "text", "text": self.response_text}],
        })

    def get_messages(self, session_id, limit=50, directory=None):
        return list(self._sessions.get(session_id, {}).get("messages", []))

    def abort(self, session_id, directory=None):
        return True