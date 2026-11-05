"""WP-433 / WP-433R: Continuous ChatGPT conversation observer (read-only).

Maintains a single persistent CDP connection for the observer lifecycle.
Reuses the same attached browser context and pinned conversation page.
Polling does not create new browser attachments.

No messages are sent. No tasks are executed.
"""

import threading
import time
from typing import Any, Dict, Optional

from .chatgpt_project_reader import ChatGPTProjectReader


class ChatGPTObserver:
    """Controlled read-only observer. Polling must be explicitly started.

    Maintains one persistent CDP connection. Reconnects only on genuine
    connection loss, with bounded retries. Ordinary page-read errors do not
    trigger reattachment.
    """

    def __init__(self, reader: ChatGPTProjectReader, registry, interval_seconds: int = 15):
        self.reader = reader
        self.registry = registry
        self.interval_seconds = max(5, int(interval_seconds))
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._running = False

        # Connection tracking (WP-433R)
        self._connection_state: str = "DISCONNECTED"  # DISCONNECTED, CONNECTED, RECONNECTING
        self._attachment_count: int = 0
        self._reconnect_count: int = 0
        self._last_disconnect_reason: Optional[str] = None
        self._last_attach_time: Optional[float] = None
        self._consecutive_failures: int = 0
        self._max_reconnects: int = 3
        self._reconnect_backoff: float = 5.0

    @property
    def status(self) -> str:
        return self.registry.get_observer_state().get("status", "STOPPED")

    @property
    def connection_state(self) -> str:
        return self._connection_state

    @property
    def attachment_count(self) -> int:
        return self._attachment_count

    @property
    def reconnect_count(self) -> int:
        return self._reconnect_count

    @property
    def last_disconnect_reason(self) -> Optional[str]:
        return self._last_disconnect_reason

    def get_connection_info(self) -> Dict[str, Any]:
        """Return connection diagnostics for operator inspection."""
        return {
            "connection_state": self._connection_state,
            "attachment_count": self._attachment_count,
            "reconnect_count": self._reconnect_count,
            "last_disconnect_reason": self._last_disconnect_reason,
            "last_attach_time": self._last_attach_time,
            "consecutive_failures": self._consecutive_failures,
            "is_running": self.is_running(),
            "interval_seconds": self.interval_seconds,
        }

    def start(self) -> Dict[str, Any]:
        with self._lock:
            if self._running:
                return {"ok": False, "reason": "already_running"}
            state = self.registry.get_observer_state()
            if state.get("status") == "RUNNING":
                return {"ok": False, "reason": "already_running"}

            proj = self.registry.get_project(self.reader.project_key) if self.reader.project_key else None
            if not proj or not proj["enabled"]:
                self.registry.set_observer_status("ATTACHMENT_BLOCKED", last_error="project not available")
                return {"ok": False, "reason": "project_not_available"}

            # Verify browser attachment (do not attach if not already attached)
            adapter = self.reader.adapter
            browser = getattr(adapter, "browser", None)
            if browser is not None:
                try:
                    health = browser.conversation_health() if hasattr(browser, "conversation_health") else {}
                    if not health.get("browser_connected", True):
                        self._connection_state = "DISCONNECTED"
                        self.registry.set_observer_status("ATTACHMENT_BLOCKED", last_error="browser not connected")
                        return {"ok": False, "reason": "browser_not_connected"}
                except Exception as exc:
                    self._connection_state = "DISCONNECTED"
                    self.registry.set_observer_status("ATTACHMENT_BLOCKED", last_error=f"{type(exc).__name__}: {exc}")
                    return {"ok": False, "reason": "attachment_check_failed", "error": str(exc)[:200]}

            # Connection established (browser already attached by operator/CSS)
            self._connection_state = "CONNECTED"
            self._attachment_count += 1
            self._last_attach_time = time.time()
            self._consecutive_failures = 0

            self.registry.set_observer_status("RUNNING", active_project_key=self.reader.project_key)
            self._stop_event.clear()
            self._running = True
            self._thread = threading.Thread(target=self._poll_loop, daemon=True, name="chatgpt-observer")
            self._thread.start()
            return {"ok": True, "status": "RUNNING", "interval_seconds": self.interval_seconds,
                    "attachment_count": self._attachment_count}

    def stop(self) -> Dict[str, Any]:
        with self._lock:
            if not self._running:
                self.registry.set_observer_status("STOPPED")
                self._connection_state = "DISCONNECTED"
                return {"ok": True, "status": "STOPPED", "was_running": False}
            self._stop_event.set()
            self._running = False
            if self._thread and self._thread.is_alive():
                self._thread.join(timeout=10)
            self._thread = None
            self._connection_state = "DISCONNECTED"
            self.registry.set_observer_status("STOPPED")
            return {"ok": True, "status": "STOPPED", "was_running": True,
                    "attachment_count": self._attachment_count,
                    "reconnect_count": self._reconnect_count}

    def _poll_loop(self):
        while not self._stop_event.is_set():
            try:
                result = self.reader.read_messages(max_messages=10)
                if result.get("ok"):
                    self.registry.increment_poll_count()
                    self.registry.set_observer_status("RUNNING", last_error=None)
                    self._consecutive_failures = 0
                else:
                    reason = result.get("reason", "read_failed")
                    # Ordinary read errors do NOT trigger reattachment.
                    # Only genuine connection loss triggers reconnect.
                    if self._is_connection_lost(reason):
                        self._handle_disconnect(reason)
                    else:
                        self.registry.set_observer_status("RUNNING", last_error=reason)
            except Exception as exc:
                err = f"{type(exc).__name__}: {exc}"
                if self._is_connection_lost(err):
                    self._handle_disconnect(err)
                else:
                    self.registry.set_observer_status("RUNNING", last_error=err)
            # Wait for next poll
            self._stop_event.wait(self.interval_seconds)
        self._running = False

    def _is_connection_lost(self, reason: str) -> bool:
        """Distinguish genuine connection loss from ordinary read errors."""
        lowered = (reason or "").lower()
        connection_indicators = [
            "disconnected", "connection", "refused", "unreachable",
            "closed", "reset", "broken pipe", "not connected",
            "target closed", "browser has been closed",
        ]
        return any(ind in lowered for ind in connection_indicators)

    def _handle_disconnect(self, reason: str):
        """Bounded reconnect on genuine connection loss. Never launches browser."""
        self._last_disconnect_reason = reason
        self._connection_state = "RECONNECTING"
        self.registry.set_observer_status("ATTACHMENT_BLOCKED", last_error=reason)

        if self._reconnect_count >= self._max_reconnects:
            self._connection_state = "DISCONNECTED"
            self.registry.set_observer_status("ATTACHMENT_BLOCKED", last_error="max reconnects exceeded: " + reason)
            self._stop_event.set()
            self._running = False
            return

        for attempt in range(1, self._max_reconnects + 1):
            if self._stop_event.is_set():
                return
            self._reconnect_count += 1
            wait = self._reconnect_backoff * attempt
            self._stop_event.wait(wait)
            if self._stop_event.is_set():
                return
            # Try to verify connection is back (do not re-attach, just check)
            adapter = self.reader.adapter
            browser = getattr(adapter, "browser", None)
            if browser is not None:
                try:
                    health = browser.conversation_health() if hasattr(browser, "conversation_health") else {}
                    if health.get("browser_connected", True):
                        self._connection_state = "CONNECTED"
                        self._consecutive_failures = 0
                        self.registry.set_observer_status("RUNNING", last_error=None)
                        return
                except Exception:
                    pass
            # Connection still down
            self._consecutive_failures += 1

        # Exhausted reconnects
        self._connection_state = "DISCONNECTED"
        self.registry.set_observer_status("ATTACHMENT_BLOCKED", last_error="reconnect failed: " + reason)
        self._stop_event.set()
        self._running = False

    def is_running(self) -> bool:
        return self._running and self._thread is not None and self._thread.is_alive()
