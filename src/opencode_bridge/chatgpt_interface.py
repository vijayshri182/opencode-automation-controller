"""WP-423: provider-independent ChatGPT communication boundary.

The orchestrator depends only on :class:`ChatGPTInterface`, never on Playwright.
:class:`PlaywrightChatGPTAdapter` delegates to the *existing* ``BrowserAdapter``
(``PlaywrightEdgeAdapter`` / ``MockBrowserAdapter``) and the existing
``PlaywrightChatGPTController`` discovery logic — it does not reimplement browser
automation, and it never launches a browser.

Preserved WP-419/WP-421 rules enforced here:

* discovery always goes through the fixed Project URL and the Project's own
  conversation list — never a stored ``/c/<id>`` URL;
* a new conversation is never created;
* the adapter never silently switches to another Project: the returned
  ``project_id`` must match the requested one or the call is blocked.

Message identity: the ChatGPT DOM does not expose a stable per-message id in this
Project view, so the adapter derives a deterministic content hash and labels it
``message_identity_source="derived_content_hash"``. It is never presented as a UI
id, and it is stable across re-reads, which is what makes ingestion idempotent.
"""

import hashlib
import re
import time
from typing import Any, Dict, List, Optional

from .contracts import INBOUND_MESSAGE_SCHEMA
from .browser_automation import TASK_END_BRACKET, TASK_START_BRACKET, extract_task_from_text

#: Fixed Palmistry Project (never user-supplied at runtime).
PALMISTRY_PROJECT_URL = "https://chatgpt.com/g/g-p-6ae87c1e48b08191a2cd33139c40639f/project"
PALMISTRY_PROJECT_ID = "g-p-6ae87c1e48b08191a2cd33139c40639f"

DEFAULT_EXCLUDED_TITLES = ["OpenCode Automation Testing"]

# Stable, machine-readable failure reasons shared by orchestrator and tests.
CHATGPT_RATE_LIMITED = "chatgpt_rate_limited"
CHATGPT_AUTH_REQUIRED = "chatgpt_authentication_required"
CHATGPT_PROJECT_UNAVAILABLE = "chatgpt_project_unavailable"
CHATGPT_CONVERSATION_UNAVAILABLE = "chatgpt_conversation_unavailable"
CHATGPT_DELIVERY_UNCERTAIN = "chatgpt_delivery_uncertain"
CHATGPT_AMBIGUOUS_RESPONSE = "chatgpt_ambiguous_response"
CHATGPT_DISCONNECTED = "chatgpt_cdp_disconnected"


class ChatGPTInterface:
    """Operations a ChatGPT transport must provide. No implementation details."""

    provider = "chatgpt"

    def discover_project(self, project_url: str) -> Dict[str, Any]:  # pragma: no cover - interface
        raise NotImplementedError

    def discover_latest_conversation(
        self, project_url: str, excluded_titles: Optional[List[str]] = None
    ) -> Dict[str, Any]:  # pragma: no cover - interface
        raise NotImplementedError

    def read_latest_messages(
        self,
        project_url: str,
        excluded_titles: Optional[List[str]] = None,
        max_messages: int = 5,
    ) -> Dict[str, Any]:  # pragma: no cover - interface
        raise NotImplementedError

    def deliver_message(
        self, conversation: Dict[str, Any], content: str, dedupe_key: str = ""
    ) -> Dict[str, Any]:  # pragma: no cover - interface
        raise NotImplementedError

    def verify_delivery(self, attempt: Dict[str, Any]) -> Dict[str, Any]:  # pragma: no cover - interface
        raise NotImplementedError


def derive_message_id(project_id: str, conversation_id: str, content: str) -> str:
    """Deterministic, content-derived message identity (explicitly not a UI id)."""
    payload = f"{project_id}\x1f{conversation_id}\x1f{content.strip()}"
    return "derived-" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


def build_inbound_message(
    *,
    project_id: str,
    conversation_id: str,
    content: str,
    correlation_id: str,
    message_timestamp: Optional[str] = None,
    message_id: Optional[str] = None,
    message_identity_source: str = "derived_content_hash",
    received_at: Optional[float] = None,
) -> Dict[str, Any]:
    """Build a contract-shaped inbound message without inventing a UI id."""
    mid = message_id or derive_message_id(project_id, conversation_id, content)
    return {
        "schema_version": INBOUND_MESSAGE_SCHEMA,
        "message_id": mid,
        "source": "chatgpt",
        "project_id": project_id,
        "conversation_id": conversation_id,
        "message_timestamp": message_timestamp,
        "message_content": content,
        "correlation_id": correlation_id,
        "received_at": time.time() if received_at is None else received_at,
        "message_identity_source": message_identity_source if message_id is None else "ui",
    }


def _project_id_from_url(project_url: str) -> str:
    match = re.search(r"/g/(g-p-[0-9a-z]+)", (project_url or ""))
    return match.group(1) if match else ""


class PlaywrightChatGPTAdapter(ChatGPTInterface):
    """Playwright transport, delegating to the existing browser adapter.

    ``browser`` is an existing ``BrowserAdapter`` (attach-only Playwright or the
    mock). ``controller`` is an optional existing ``PlaywrightChatGPTController``
    used for its proven discovery/read logic. No launch path exists here.
    """

    provider = "chatgpt"

    def __init__(self, browser, controller=None, project_url: str = PALMISTRY_PROJECT_URL):
        self.browser = browser
        self.controller = controller
        self.default_project_url = project_url

    # -- discovery ------------------------------------------------------

    def cdp_status(self) -> Dict[str, Any]:
        '''Report whether the underlying browser is a borrowed CDP attachment.

        Never attempts to launch. Returns a blocked-style dict when the browser
        is not attached or CDP is unavailable.
        '''
        info = getattr(self.browser, "last_attach_info", None)
        if isinstance(info, dict) and info:
            if info.get("ok"):
                return {"ok": True, "cdp": True, "attach_info": info}
            return {
                "ok": False,
                "cdp": False,
                "reason": info.get("error") or info.get("reason") or "cdp_unavailable",
                "attach_info": info,
            }
        # Non-attached browser (e.g. a launched persistent context or a mock).
        if getattr(self.browser, "_attached", False):
            return {"ok": True, "cdp": True, "attached": True}
        if type(self.browser).__name__ == "MockBrowserAdapter":
            return {"ok": True, "cdp": False, "mock": True}
        health = {}
        try:
            health = self.browser.conversation_health() or {}
        except Exception as exc:
            return {"ok": False, "cdp": False, "reason": f"{type(exc).__name__}: {exc}"}
        if not health.get("browser_connected", True):
            return {"ok": False, "cdp": False, "reason": CHATGPT_DISCONNECTED}
        return {"ok": True, "cdp": "unknown", "health": health}

    def discover_project(self, project_url: str) -> Dict[str, Any]:
        project_url = project_url or self.default_project_url
        expected_id = _project_id_from_url(project_url)
        try:
            health = self.browser.conversation_health() or {}
        except Exception as exc:
            return {"ok": False, "reason": CHATGPT_DISCONNECTED, "error": f"{type(exc).__name__}: {exc}"}

        if not health.get("browser_connected", True):
            return {"ok": False, "reason": CHATGPT_DISCONNECTED, "detail": "browser not connected"}
        if not health.get("authenticated", True):
            return {"ok": False, "reason": CHATGPT_AUTH_REQUIRED, "detail": "not authenticated"}

        try:
            conversations = self.browser.discover_project_conversations(project_url) or []
        except Exception as exc:
            return {"ok": False, "reason": CHATGPT_PROJECT_UNAVAILABLE, "error": f"{type(exc).__name__}: {exc}"}
        if not conversations:
            return {"ok": False, "reason": CHATGPT_PROJECT_UNAVAILABLE, "detail": "no conversation links found"}

        return {
            "ok": True,
            "project_id": expected_id,
            "project_url": project_url,
            "conversation_count": len(conversations),
            "conversations": conversations,
        }

    def discover_latest_conversation(
        self, project_url: str, excluded_titles: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        project = self.discover_project(project_url)
        if not project.get("ok"):
            return project
        excluded = list(excluded_titles or DEFAULT_EXCLUDED_TITLES)
        try:
            selection = self.browser.select_latest_project_conversation(project_url, excluded) or {}
        except Exception as exc:
            return {"ok": False, "reason": CHATGPT_CONVERSATION_UNAVAILABLE, "error": f"{type(exc).__name__}: {exc}"}
        if not selection.get("clicked"):
            return {
                "ok": False,
                "reason": CHATGPT_CONVERSATION_UNAVAILABLE,
                "detail": selection.get("reason", "no eligible conversation"),
                "candidates": selection.get("candidates", []),
            }
        cid = selection.get("conversation_id", "")
        if not cid:
            # Never proceed without a verified conversation identity.
            return {"ok": False, "reason": CHATGPT_CONVERSATION_UNAVAILABLE, "detail": "missing conversation id"}
        return {
            "ok": True,
            "project_id": project["project_id"],
            "project_url": project_url,
            "conversation_id": cid,
            "title": selection.get("title", ""),
            "url": self.browser.current_url() if hasattr(self.browser, "current_url") else "",
        }

    # -- reading ---------------------------------------------------------

    def read_latest_messages(
        self,
        project_url: str,
        excluded_titles: Optional[List[str]] = None,
        max_messages: int = 5,
    ) -> Dict[str, Any]:
        conversation = self.discover_latest_conversation(project_url, excluded_titles)
        if not conversation.get("ok"):
            return conversation

        if self.controller is not None:
            try:
                read = self.controller.discover_and_read_latest_message(
                    project_url, excluded_titles=excluded_titles
                )
            except Exception as exc:
                return {"ok": False, "reason": CHATGPT_AMBIGUOUS_RESPONSE, "error": f"{type(exc).__name__}: {exc}"}
            if not read.get("ok"):
                return {"ok": False, "reason": CHATGPT_CONVERSATION_UNAVAILABLE, "detail": read.get("reason")}
            content = read.get("latest_user_message", "")
            stamp = read.get("latest_user_message_at") or None
            conversation_id = read.get("conversation_id") or conversation["conversation_id"]
        else:
            text = self.browser.get_page_text() or ""
            blocks = list(re.finditer(r"You said:\s*(.*?)(?=ChatGPT said:|You said:|$)", text, re.S))
            if not blocks:
                return {"ok": False, "reason": CHATGPT_AMBIGUOUS_RESPONSE, "detail": "no user message block found"}
            content = blocks[-1].group(1).strip()
            stamp = None
            conversation_id = conversation["conversation_id"]

        if not content.strip():
            return {"ok": False, "reason": CHATGPT_AMBIGUOUS_RESPONSE, "detail": "empty message content"}

        project_id = conversation["project_id"]
        message = build_inbound_message(
            project_id=project_id,
            conversation_id=conversation_id,
            content=content,
            correlation_id=f"corr-{conversation_id[:12]}-{int(time.time() * 1000)}",
            message_timestamp=stamp,
        )
        return {
            "ok": True,
            "project_id": project_id,
            "conversation_id": conversation_id,
            "title": conversation.get("title", ""),
            "messages": [message][: max(1, int(max_messages))],
            "task_text": extract_task_from_text(content),
        }

    # -- delivery --------------------------------------------------------

    def deliver_message(
        self, conversation: Dict[str, Any], content: str, dedupe_key: str = ""
    ) -> Dict[str, Any]:
        if not content or not str(content).strip():
            return {"ok": False, "status": "failed", "reason": "empty content"}
        expected_project = conversation.get("project_id") or ""
        expected_conversation = conversation.get("conversation_id") or ""
        current_url = self.browser.current_url() or ""
        actual_project = _project_id_from_url(current_url)
        # The project ID may appear in the URL followed by a slug (e.g.
        # g-p-...-palmistry-project/c/...) rather than a trailing slash, so
        # also check substring presence as a fallback.
        project_present = (not expected_project) or (expected_project in current_url)
        if expected_project and current_url and not project_present:
            # Never silently deliver into a different Project.
            return {
                "ok": False,
                "status": "failed",
                "reason": CHATGPT_PROJECT_UNAVAILABLE,
                "detail": f"project mismatch: expected {expected_project}, page is {actual_project}",
            }
        # Verify the intended conversation is still the one on screen. We never
        # navigate to a stored /c/<id> URL, so a mismatch here means the
        # selection drifted and we must pause rather than guess. The check is
        # only applied when we actually have a non-empty URL to compare
        # against; an empty URL (e.g. a not-yet-navigated mock) is treated as
        # "unknown" rather than "mismatch" so verification is not falsely blocked.
        if expected_conversation and current_url and expected_conversation not in current_url:
            health = self.browser.conversation_health() or {}
            if not health.get("conversation_loaded", True):
                return {
                    "ok": False,
                    "status": "failed",
                    "reason": CHATGPT_CONVERSATION_UNAVAILABLE,
                    "detail": f"conversation not selected: expected {expected_conversation}",
                }
        health = self.browser.conversation_health() or {}
        if not health.get("authenticated", True):
            return {"ok": False, "status": "failed", "reason": CHATGPT_AUTH_REQUIRED}
        if not health.get("writeable", True):
            return {"ok": False, "status": "failed", "reason": CHATGPT_DISCONNECTED, "detail": "composer not ready"}

        try:
            submitted = self.browser.submit_message(content)
        except Exception as exc:
            return {
                "ok": False,
                "status": "uncertain",
                "reason": CHATGPT_DELIVERY_UNCERTAIN,
                "error": f"{type(exc).__name__}: {exc}",
            }
        if not submitted:
            return {"ok": False, "status": "uncertain", "reason": CHATGPT_DELIVERY_UNCERTAIN, "detail": "submit returned False"}

        attempt = {"dedupe_key": dedupe_key, "content_prefix": content[:120]}
        verification = self.verify_delivery(attempt)
        if not verification.get("verified"):
            return {
                "ok": False,
                "status": "uncertain",
                "reason": CHATGPT_DELIVERY_UNCERTAIN,
                "evidence": verification.get("evidence", {}),
            }
        return {
            "ok": True,
            "status": "delivered",
            "evidence": verification.get("evidence", {}),
            "dedupe_key": dedupe_key,
        }

    def verify_delivery(self, attempt: Dict[str, Any]) -> Dict[str, Any]:
        prefix = (attempt or {}).get("content_prefix", "")
        if not prefix:
            return {"ok": False, "verified": False, "evidence": {"reason": "no content prefix"}}
        try:
            verified = bool(self.browser.verify_submitted(prefix))
        except Exception as exc:
            return {
                "ok": False,
                "verified": False,
                "evidence": {"error": f"{type(exc).__name__}: {exc}"},
            }
        return {"ok": True, "verified": verified, "evidence": {"prefix": prefix, "verified": verified}}


class FakeChatGPTAdapter(ChatGPTInterface):
    """Deterministic transport double for orchestration tests.

    Scenario knobs cover the failure modes WP-423 §7 requires: rate limit,
    authentication expiry, CDP disconnection, an inaccessible project, an
    ambiguous response, and an uncertain delivery.
    """

    provider = "chatgpt"

    def __init__(
        self,
        *,
        project_url: str = PALMISTRY_PROJECT_URL,
        project_id: str = PALMISTRY_PROJECT_ID,
        conversation_id: str = "conv-0001",
        messages: Optional[List[str]] = None,
        rate_limited: bool = False,
        auth_required: bool = False,
        disconnected: bool = False,
        project_available: bool = True,
        ambiguous_response: bool = False,
        delivery_fails: bool = False,
        delivery_uncertain: bool = False,
        project_mismatch: bool = False,
    ):
        self.project_url = project_url
        self.project_id = project_id
        self.conversation_id = conversation_id
        self.messages = list(messages or [])
        self.rate_limited = rate_limited
        self.auth_required = auth_required
        self.disconnected = disconnected
        self.project_available = project_available
        self.ambiguous_response = ambiguous_response
        self.delivery_fails = delivery_fails
        self.delivery_uncertain = delivery_uncertain
        self.project_mismatch = project_mismatch
        self.deliveries: List[Dict[str, Any]] = []
        self.read_calls = 0

    def _guard(self) -> Optional[Dict[str, Any]]:
        if self.disconnected:
            return {"ok": False, "reason": CHATGPT_DISCONNECTED}
        if self.auth_required:
            return {"ok": False, "reason": CHATGPT_AUTH_REQUIRED}
        if self.rate_limited:
            return {"ok": False, "reason": CHATGPT_RATE_LIMITED}
        return None

    def discover_project(self, project_url: str) -> Dict[str, Any]:
        blocked = self._guard()
        if blocked:
            return blocked
        if not self.project_available:
            return {"ok": False, "reason": CHATGPT_PROJECT_UNAVAILABLE}
        if not self.messages:
            return {"ok": False, "reason": CHATGPT_PROJECT_UNAVAILABLE, "detail": "no conversation links found"}
        return {
            "ok": True,
            "project_id": self.project_id,
            "project_url": project_url or self.project_url,
            "conversation_count": 1,
            "conversations": [{"conversation_id": self.conversation_id, "title": "Project Test"}],
        }

    def discover_latest_conversation(
        self, project_url: str, excluded_titles: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        project = self.discover_project(project_url)
        if not project.get("ok"):
            return project
        return {
            "ok": True,
            "project_id": self.project_id,
            "project_url": project_url or self.project_url,
            "conversation_id": self.conversation_id,
            "title": "Project Test",
            "url": self.project_url,
        }

    def read_latest_messages(
        self,
        project_url: str,
        excluded_titles: Optional[List[str]] = None,
        max_messages: int = 5,
    ) -> Dict[str, Any]:
        self.read_calls += 1
        conversation = self.discover_latest_conversation(project_url, excluded_titles)
        if not conversation.get("ok"):
            return conversation
        if self.ambiguous_response:
            return {"ok": False, "reason": CHATGPT_AMBIGUOUS_RESPONSE, "detail": "unparseable message block"}
        if not self.messages:
            return {
                "ok": True,
                "project_id": self.project_id,
                "conversation_id": self.conversation_id,
                "messages": [],
                "task_text": None,
            }
        out = []
        for index, content in enumerate(self.messages[-max(1, int(max_messages)):]):
            out.append(
                build_inbound_message(
                    project_id=self.project_id,
                    conversation_id=self.conversation_id,
                    content=content,
                    correlation_id=f"corr-{index}",
                    received_at=1_700_000_000.0 + index,
                )
            )
        latest = self.messages[-1]
        return {
            "ok": True,
            "project_id": self.project_id,
            "conversation_id": self.conversation_id,
            "messages": out,
            "task_text": extract_task_from_text(latest),
        }

    def deliver_message(
        self, conversation: Dict[str, Any], content: str, dedupe_key: str = ""
    ) -> Dict[str, Any]:
        blocked = self._guard()
        if blocked:
            return {"ok": False, "status": "failed", **blocked}
        if not content.strip():
            return {"ok": False, "status": "failed", "reason": "empty content"}
        if self.project_mismatch:
            return {
                "ok": False,
                "status": "failed",
                "reason": CHATGPT_PROJECT_UNAVAILABLE,
                "detail": "project mismatch",
            }
        if self.delivery_fails:
            return {"ok": False, "status": "failed", "reason": "fake delivery failure"}
        if self.delivery_uncertain:
            return {"ok": False, "status": "uncertain", "reason": CHATGPT_DELIVERY_UNCERTAIN}
        record = {"content": content, "dedupe_key": dedupe_key, "conversation_id": conversation.get("conversation_id")}
        self.deliveries.append(record)
        return {
            "ok": True,
            "status": "delivered",
            "evidence": {"verified": True, "dedupe_key": dedupe_key},
            "dedupe_key": dedupe_key,
        }

    def verify_delivery(self, attempt: Dict[str, Any]) -> Dict[str, Any]:
        if self.delivery_uncertain:
            return {"ok": True, "verified": False, "evidence": {"reason": "unverifiable"}}
        return {"ok": True, "verified": True, "evidence": {"verified": True}}


def has_task_markers(text: str) -> bool:
    return TASK_START_BRACKET in (text or "") and TASK_END_BRACKET in (text or "")
