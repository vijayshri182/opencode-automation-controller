import json
import os
import re
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, Optional

from .config import DEV_WORKSPACE

TASK_MARKER_START = "<!-- OPENCODE_TASK -->"
TASK_MARKER_END = "<!-- /OPENCODE_TASK -->"
TASK_MARKER_START_ALT = "[OPENCODE_TASK]"
TASK_MARKER_END_ALT = "[/OPENCODE_TASK]"


@dataclass
class BrowserState:
    conversation_url: str = ""
    project_url: str = ""
    conversation_id: str = ""
    conversation_title: str = ""
    current_task_id: str = ""
    status: str = "idle"
    paused: bool = False
    last_error: str = ""
    last_submitted_marker: str = ""
    last_assistant_response: str = ""
    latest_user_message: str = ""
    latest_user_message_at: str = ""


class BrowserAdapter:
    """Interface for browser automation (Playwright or mock)."""

    def start(self) -> bool:
        raise NotImplementedError

    def stop(self):
        raise NotImplementedError

    def navigate(self, url: str) -> bool:
        raise NotImplementedError

    def current_url(self) -> str:
        raise NotImplementedError

    def wait_for_response(self, timeout: float = 60.0) -> bool:
        raise NotImplementedError

    def extract_last_assistant_text(self) -> str:
        raise NotImplementedError

    def get_page_text(self) -> str:
        raise NotImplementedError

    def submit_message(self, text: str) -> bool:
        raise NotImplementedError

    def verify_submitted(self, text: str) -> bool:
        raise NotImplementedError

    def conversation_health(self) -> dict:
        raise NotImplementedError

    def open_project_conversation(self, project_url: str, conversation_id: str) -> bool:
        raise NotImplementedError

    def select_project_conversation_by_ui(self, project_name: str, conversation_title: str) -> bool:
        raise NotImplementedError

    def is_authenticated(self) -> bool:
        raise NotImplementedError

    def create_project_chat(self, project_name: str) -> str:
        raise NotImplementedError

    def discover_project_conversations(self, project_url: str) -> list:
        """Return list of {title, conversation_id, href, index} from the live Project list."""
        raise NotImplementedError

    def select_latest_project_conversation(self, project_url: str, excluded_titles: list = None) -> dict:
        """Open project, discover list, select newest eligible conv. Returns dict with title, conversation_id, clicked, reason."""
        raise NotImplementedError


class MockBrowserAdapter(BrowserAdapter):
    def __init__(self):
        self._url = ""
        self._text = ""
        self._submitted = []
        self._auth = True

    def start(self):
        return True

    def stop(self):
        pass

    def navigate(self, url):
        self._url = url
        return True

    def current_url(self):
        return self._url

    def wait_for_response(self, timeout=60.0):
        return True

    def extract_last_assistant_text(self):
        return self._text

    def get_page_text(self):
        return self._text

    def set_assistant_text(self, text):
        self._text = text

    def submit_message(self, text):
        self._submitted.append(text)
        return True

    def verify_submitted(self, text):
        # Mock: submitted list contains text
        return any(text in s for s in self._submitted)

    def conversation_health(self):
        return {
            "browser_connected": True,
            "authenticated": self._auth,
            "conversation_loaded": bool(self._url),
            "readable": True,
            "writeable": True,
        }

    def open_project_conversation(self, project_url: str, conversation_id: str) -> bool:
        self._url = f"https://chatgpt.com/c/{conversation_id}"
        return True

    def is_authenticated(self):
        return self._auth

    def create_project_chat(self, project_name: str) -> str:
        new_url = f"https://chatgpt.com/c/mock-{project_name}"
        self._url = new_url
        return new_url

    def select_project_conversation_by_ui(self, project_name: str, conversation_title: str) -> bool:
        self._url = f"https://chatgpt.com/c/mock-{conversation_title}"
        return True

    def discover_project_conversations(self, project_url: str) -> list:
        return [
            {"title": "Project Test", "conversation_id": "6ae87c0a-10c8-83ee-a666-c3a5cfea6521", "href": "/c/6ae87c0a-10c8-83ee-a666-c3a5cfea6521", "index": 0},
            {"title": "OpenCode Automation Testing", "conversation_id": "6ae87cee-50a4-83e8-a0e6-eba390f83a7a", "href": "/c/6ae87cee-50a4-83e8-a0e6-eba390f83a7a", "index": 1},
        ]

    def select_latest_project_conversation(self, project_url: str, excluded_titles: list = None) -> dict:
        excluded = set(excluded_titles or [])
        convs = self.discover_project_conversations(project_url)
        eligible = [c for c in convs if c["title"] not in excluded]
        if not eligible:
            return {"title": "", "conversation_id": "", "clicked": False, "reason": "no_eligible"}
        chosen = eligible[0]
        self._url = f"https://chatgpt.com/c/mock-{chosen['title']}"
        return {"title": chosen["title"], "conversation_id": chosen["conversation_id"], "clicked": True, "reason": "newest_eligible"}

    def submitted(self):
        return list(self._submitted)


class PlaywrightEdgeAdapter(BrowserAdapter):
    def __init__(self, profile_dir: str, conversation_url: str = "", headless: bool = False):
        self.profile_dir = profile_dir
        self.conversation_url = conversation_url
        self.headless = headless
        self._pw = None
        self._context = None
        self._page = None
        # WP-421A: when True the adapter only borrowed an existing tab.
        self._attached = False
        self.last_attach_info = {}

    def attach_existing(
        self,
        cdp_url: str = None,
        project_url: str = None,
        wait_seconds: float = None,
        user_data_dir: str = None,
    ) -> dict:
        """WP-421A/WP-422: reuse the already-running managed Edge over CDP.

        Never launches a browser. Returns the structured attach result; on a
        blocked result ``ok`` is False and ``last_attach_info['error']`` holds
        the exact failure so callers can report it without guessing.
        """
        from .edge_attach import (
            CDP_URL,
            DEFAULT_READY_WAIT,
            PALMISTRY_PROJECT_URL,
            attach_existing_edge,
        )

        info = attach_existing_edge(
            cdp_url=cdp_url or CDP_URL,
            project_url=project_url or PALMISTRY_PROJECT_URL,
            wait_seconds=DEFAULT_READY_WAIT if wait_seconds is None else wait_seconds,
            user_data_dir=user_data_dir,
        )
        self.last_attach_info = {
            k: v for k, v in info.items() if k not in ("page", "browser", "playwright")
        }
        if info.get("ok"):
            self._pw = info.get("playwright") or self._pw
            self._page = info.get("page")
            self._attached = True
            self.conversation_url = info.get("current_url") or getattr(self._page, "url", "") or self.conversation_url
        return info

    def start(self) -> bool:
        try:
            from playwright.sync_api import sync_playwright
        except Exception as e:
            raise RuntimeError(
                "Playwright is not installed for this Python executable. "
                "Use the project virtual environment or install with: "
                "python -m pip install -r requirements.txt. "
                f"Original error: {e}"
            )
        self._pw = sync_playwright().start()
        from .config import edge_executable_path
        edge_path = edge_executable_path()
        if not os.path.exists(edge_path) or "msedge.exe" not in edge_path.lower():
            raise RuntimeError("Microsoft Edge executable not found or invalid. Set EDGE_EXECUTABLE_PATH to msedge.exe.")
        self._context = self._pw.chromium.launch_persistent_context(
            self.profile_dir,
            executable_path=edge_path,
            headless=self.headless,
            chromium_sandbox=True,
        )
        if self._context.pages:
            self._page = self._context.pages[0]
        else:
            self._page = self._context.new_page()
        if self.conversation_url:
            self._page.goto(self.conversation_url)
        return True

    def stop(self):
        if self._attached:
            # WP-421A: borrowed tab — disconnect only. Never close the user's
            # browser context/page.
            try:
                if self._pw:
                    self._pw.stop()
            except Exception:
                pass
            self._page = None
            self._context = None
            self._attached = False
            return
        try:
            if self._context:
                self._context.close()
        except Exception:
            pass
        try:
            if self._pw:
                self._pw.stop()
        except Exception:
            pass

    def navigate(self, url: str) -> bool:
        if not self._page:
            return False
        self._page.goto(url)
        self.conversation_url = url
        return True

    def current_url(self) -> str:
        return self._page.url if self._page else self.conversation_url

    def wait_for_response(self, timeout: float = 60.0) -> bool:
        if not self._page:
            return False
        # Wait for streaming to finish: send button re-enabled / stop button gone.
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                # ChatGPT shows a "Stop generating" button while streaming.
                stop = self._page.query_selector("button[aria-label='Stop generating']")
                if stop is None:
                    return True
            except Exception:
                return True
            time.sleep(0.5)
        return False

    def extract_last_assistant_text(self) -> str:
        if not self._page:
            return ""
        # Best-effort: read last assistant message container.
        try:
            nodes = self._page.query_selector_all("div[data-message-author-role='assistant']")
            if nodes:
                return nodes[-1].inner_text()
            # Fallback for project conversations: parse visible text.
            try:
                txt = self._page.inner_text("body") or ""
                import re
                matches = re.findall(r"ChatGPT said:\s*(.*?)(?=You said:|$)", txt, re.S)
                if matches:
                    return matches[-1].strip()
            except Exception:
                pass
            return ""
        except Exception:
            return ""

    def get_page_text(self) -> str:
        if not self._page:
            return ""
        try:
            return self._page.inner_text("body") or ""
        except Exception:
            try:
                return self._page.content() or ""
            except Exception:
                return ""

    def submit_message(self, text: str) -> bool:
        if not self._page:
            return False
        try:
            box = self._page.query_selector("div[role='textbox']")
            if box is None:
                box = self._page.query_selector("textarea")
            if box is None:
                return False
            box.click()
            self._page.keyboard.type(text)
            btn = (self._page.query_selector("button[aria-label='Send']") or
                   self._page.query_selector("button[aria-label='send']") or
                   self._page.query_selector("button[aria-label='Send prompt']") or
                   self._page.query_selector("button[aria-label='send prompt']") or
                   self._page.query_selector("button[data-testid='send-button']"))
            if btn is None:
                return False
            btn.click()
            return True
        except Exception:
            return False

    def verify_submitted(self, text: str) -> bool:
        if not self._page:
            return False
        try:
            # Wait briefly for the message to appear in the conversation.
            snippet = text.strip()[:80]
            deadline = time.time() + 10
            while time.time() < deadline:
                content = self._page.inner_text("body") if self._page else ""
                if snippet and snippet in content:
                    return True
                time.sleep(0.5)
            return False
        except Exception:
            return False

    def conversation_health(self) -> dict:
        if not self._page:
            return {"browser_connected": False, "authenticated": False, "conversation_loaded": False, "readable": False, "writeable": False}
        try:
            content = self._page.content() or ""
            url = self._page.url or ""
            return {
                "browser_connected": True,
                "authenticated": ("Log in" not in content) and ("Sign up" not in content),
                "conversation_loaded": "chatgpt.com" in url,
                "readable": len(self._page.inner_text("body") or "") > 100 if self._page else False,
                "writeable": self._page.query_selector("div[role='textbox']") is not None or self._page.query_selector("textarea") is not None,
            }
        except Exception:
            return {"browser_connected": False, "authenticated": False, "conversation_loaded": False, "readable": False, "writeable": False}

    def open_project_conversation(self, project_url: str, conversation_id: str) -> bool:
        if not self._page:
            return False
        try:
            self._page.goto(project_url, timeout=30000, wait_until="domcontentloaded")
            import time
            time.sleep(10)
            # find link containing conversation_id
            links = self._page.query_selector_all("a[href*='/c/']")
            target = None
            for l in links:
                href = l.get_attribute("href") or ""
                if conversation_id in href:
                    target = l
                    break
            if target is None:
                return False
            target.evaluate("el => el.click()")
            time.sleep(10)
            if conversation_id in (self._page.url or ""):
                return True
            content = self._page.content() or ""
            return conversation_id in content
        except Exception:
            return False

    def select_project_conversation_by_ui(self, project_name: str, conversation_title: str) -> bool:
        if not self._page:
            return False
        try:
            import time
            # Step 1: click Projects in sidebar (try several selectors; UI label may vary)
            proj_btn = None
            for _sel in ("button:has-text('Projects')", "a:has-text('Projects')", ":text('Projects')", "[aria-label*='Project']"):
                try:
                    proj_btn = self._page.query_selector(_sel)
                    if proj_btn:
                        break
                except Exception:
                    proj_btn = None
            if proj_btn:
                proj_btn.click()
                time.sleep(3)
            # Step 2: click project
            proj_link = None
            for _sel in (f"a:has-text('{project_name}')", f"button:has-text('{project_name}')", f":text('{project_name}')"):
                try:
                    proj_link = self._page.query_selector(_sel)
                    if proj_link:
                        break
                except Exception:
                    proj_link = None
            if proj_link:
                proj_link.click()
                time.sleep(4)
            # Step 3: find conversation by title
            conv = None
            for _sel in (f"a:has-text('{conversation_title}')", f":text('{conversation_title}')"):
                try:
                    conv = self._page.query_selector(_sel)
                    if conv:
                        break
                except Exception:
                    conv = None
            if conv is None:
                return False
            conv.click()
            time.sleep(6)
            return True
        except Exception:
            return False

    def discover_project_conversations(self, project_url: str) -> list:
        if not self._page:
            return []
        try:
            self._page.goto(project_url, timeout=30000, wait_until="domcontentloaded")
            import time
            # bounded wait for conversation list
            deadline = time.time() + 20
            while time.time() < deadline:
                links = self._page.query_selector_all("a[href*='/c/']")
                if links:
                    break
                time.sleep(1)
            links = self._page.query_selector_all("a[href*='/c/']")
            # restrict to this project's conversations only (href contains project slug)
            project_slug = ""
            try:
                # project_url like .../g/g-p-<id>/project
                for part in (project_url or "").split("/"):
                    if part.startswith("g-p-"):
                        project_slug = part
                        break
            except Exception:
                project_slug = ""
            result = []
            seen = set()
            seen_ids = set()
            idx = 0
            for l in links:
                try:
                    href = l.get_attribute("href") or ""
                    title = (l.inner_text() or "").strip().replace("\\n", " ")
                except Exception:
                    href = ""; title = ""
                if not href or "/c/" not in href:
                    continue
                if project_slug and project_slug not in href:
                    continue
                # dedup by conversation id, keep first (newest) occurrence
                cid_check = ""
                if "/c/" in href:
                    cid_check = href.split("/c/")[-1].split("?")[0].split("#")[0]
                if cid_check and cid_check in seen_ids:
                    continue
                if cid_check:
                    seen_ids.add(cid_check)
                # extract conversation id from href
                cid = ""
                if "/c/" in href:
                    cid = href.split("/c/")[-1].split("?")[0].split("#")[0]
                key = (href, title)
                if key in seen:
                    continue
                seen.add(key)
                result.append({"title": title, "conversation_id": cid, "href": href, "index": idx})
                idx += 1
            return result
        except Exception:
            return []

    def select_latest_project_conversation(self, project_url: str, excluded_titles: list = None) -> dict:
        excluded = set(excluded_titles or [])
        convs = self.discover_project_conversations(project_url)
        eligible = [c for c in convs if not any((ex or "") in (c.get("title") or "") for ex in excluded)]
        if not convs:
            return {"title": "", "conversation_id": "", "clicked": False, "reason": "no_conversations"}
        if not eligible:
            return {"title": "", "conversation_id": "", "clicked": False, "reason": "no_eligible"}
        chosen = eligible[0]
        # click via visible UI
        clicked = False
        try:
            # find the link element matching chosen href/title
            links = self._page.query_selector_all("a[href*='/c/']")
            target = None
            for l in links:
                try:
                    href = l.get_attribute("href") or ""
                    title = (l.inner_text() or "").strip()
                except Exception:
                    href = ""; title = ""
                if chosen["conversation_id"] and chosen["conversation_id"] in href:
                    target = l
                    break
                if not target and chosen["title"] and chosen["title"] in title:
                    target = l
                    break
            if target is not None:
                target.click()
                clicked = True
                import time
                time.sleep(6)
        except Exception:
            clicked = False
        return {
            "title": chosen.get("title", ""),
            "conversation_id": chosen.get("conversation_id", ""),
            "clicked": clicked,
            "reason": "newest_eligible" if clicked else "click_failed",
            "candidates": [c.get("title") for c in convs],
        }

    def is_authenticated(self) -> bool:
        if not self._page:
            return False
        try:
            if "chatgpt.com" not in self._page.url:
                return False
            content = self._page.content() or ""
            if "Log in" in content or "Sign up" in content:
                return False
            if self._page.query_selector("button:has-text('New chat')") is not None:
                return True
            if self._page.query_selector("div[role='textbox']") is not None and "data-theme-user-id" in content:
                return True
            return False
        except Exception:
            return False

    def create_project_chat(self, project_name: str) -> str:
        if not self._page:
            return ""
        try:
            sel = f"button[aria-label='New chat in {project_name}']"
            btn = self._page.query_selector(sel)
            if btn is None:
                # fallback: first New chat button
                btn = self._page.query_selector("button:has-text('New chat')")
            if btn is None:
                return ""
            btn.click()
            import time
            time.sleep(3)
            return self._page.url
        except Exception:
            return ""


TASK_START_BRACKET = "[OPENCODE_TASK_START]"
TASK_END_BRACKET = "[OPENCODE_TASK_END]"


def extract_task_from_text(text: str) -> Optional[str]:
    if not text:
        return None
    # Alt bracket markers used in ChatGPT conversations.
    if TASK_MARKER_START_ALT in text or TASK_MARKER_END_ALT in text:
        if text.count(TASK_MARKER_START_ALT) != 1 or text.count(TASK_MARKER_END_ALT) != 1:
            return None
        start = text.index(TASK_MARKER_START_ALT) + len(TASK_MARKER_START_ALT)
        end = text.index(TASK_MARKER_END_ALT)
        if end <= start:
            return None
        task = text[start:end].strip()
        return task if task else None
    # New explicit bracket marker protocol (preferred).
    if TASK_START_BRACKET in text or TASK_END_BRACKET in text:
        if text.count(TASK_START_BRACKET) != 1 or text.count(TASK_END_BRACKET) != 1:
            return None
        start = text.index(TASK_START_BRACKET) + len(TASK_START_BRACKET)
        end = text.index(TASK_END_BRACKET)
        if end <= start:
            return None
        task = text[start:end].strip()
        return task if task else None
    # Legacy HTML comment markers.
    if TASK_MARKER_START in text and TASK_MARKER_END in text:
        if text.count(TASK_MARKER_START) != 1 or text.count(TASK_MARKER_END) != 1:
            return None
        start = text.index(TASK_MARKER_START) + len(TASK_MARKER_START)
        end = text.index(TASK_MARKER_END)
        if end <= start:
            return None
        task = text[start:end].strip()
        return task if task else None
    # Fallback: fenced block after "OPENCODE_TASK"
    m = re.search(r"OPENCODE_TASK\s*[:\-]?\s*```(?:\w+)?\n(.*?)```", text, re.S | re.I)
    if m:
        return m.group(1).strip()
    return None


def build_result_message(task_id: str, status: str, final_response: str, report_path: str, test_summary: str, git_status: str, blockers: str = "") -> str:
    parts = [
        f"OpenCode task result (task_id={task_id})",
        f"Status: {status}",
        "",
        "Final OpenCode output:",
        final_response or "(none)",
        "",
        f"Report path: {report_path or '(none)'}",
        f"Test summary: {test_summary or '(none)'}",
        f"Git status: {git_status or '(clean/unknown)'}",
    ]
    if blockers:
        parts += ["", "Blockers/limitations:", blockers]
    parts += ["", "Please review and generate the next OpenCode task if appropriate."]
    return "\n".join(parts)


class PlaywrightChatGPTController:
    def __init__(self, browser: BrowserAdapter, task_controller, state_path: Path, model: Optional[Dict[str, str]] = None):
        self.browser = browser
        self.task_controller = task_controller
        self.state_path = Path(state_path)
        self.model = model
        self.state = self._load_state()

    def _load_state(self) -> BrowserState:
        if self.state_path.exists():
            try:
                data = json.loads(self.state_path.read_text(encoding="utf-8"))
                return BrowserState(**{k: v for k, v in data.items() if k in BrowserState.__dataclass_fields__})
            except Exception:
                pass
        return BrowserState()

    def _save_state(self):
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps(asdict(self.state), indent=2), encoding="utf-8")

    def set_conversation_url(self, url: str):
        self.state.conversation_url = url
        self._save_state()

    def ensure_project_conversation(self, project_url: str, conversation_id: str) -> bool:
        if not project_url or not conversation_id:
            return False
        ok = self.browser.open_project_conversation(project_url, conversation_id)
        if not ok:
            self.state.last_error = "project conversation not found"
            self._save_state()
            return False
        # For project conversations, URL may remain project URL; verify by content presence.
        if isinstance(self.browser, MockBrowserAdapter):
            self.state.conversation_url = self.browser.current_url() or self.state.conversation_url
            self._save_state()
            return True
        page = getattr(self.browser, "_page", None)
        url = self.browser.current_url() or ""
        content = ""
        try:
            if page:
                content = page.content() or ""
        except Exception:
            content = ""
        if conversation_id not in (url + content):
            self.state.last_error = "conversation identity not verified"
            self._save_state()
            return False
        self.state.conversation_url = url or self.state.conversation_url
        self._save_state()
        return True
        self.state.conversation_url = project_url
        self._save_state()
        return True

    def select_project_conversation_by_title(self, project_name: str, conversation_title: str) -> bool:
        if not project_name or not conversation_title:
            return False
        ok = self.browser.select_project_conversation_by_ui(project_name, conversation_title)
        if not ok:
            self.state.last_error = "project conversation selection failed"
            self._save_state()
            return False
        self.state.conversation_url = self.browser.current_url() or self.state.conversation_url
        self._save_state()
        return True

    def record_chat_exchange(self, marker: str, response: str) -> None:
        """Persist a submitted marker and its retrieved assistant response."""
        self.state.last_submitted_marker = marker or ""
        self.state.last_assistant_response = response or ""
        self._save_state()

    def has_submitted_marker(self, marker: str) -> bool:
        return bool(marker) and self.state.last_submitted_marker == marker

    def discover_and_read_latest_message(self, project_url: str, excluded_titles: list = None) -> dict:
        """WP-421: open fixed Project, select newest eligible conversation, read latest user message."""
        import re, time
        excluded = list(excluded_titles or ["OpenCode Automation Testing"])
        self.state.project_url = project_url
        self._save_state()

        # bounded readiness: project page + list
        sel = self.browser.select_latest_project_conversation(project_url, excluded)
        if not sel.get("clicked"):
            self.state.last_error = f"selection failed: {sel.get('reason')}"
            self._save_state()
            return {"ok": False, "reason": sel.get("reason"), "candidates": sel.get("candidates", []), "selected": sel}

        title = sel.get("title", "")
        cid = sel.get("conversation_id", "")
        self.state.conversation_title = title
        self.state.conversation_id = cid
        self.state.conversation_url = self.browser.current_url() or self.state.conversation_url
        self._save_state()

        # bounded wait for history + composer
        deadline = time.time() + 30
        while time.time() < deadline:
            text = self.browser.get_page_text() or ""
            if ("You said:" in text) or (self.browser.conversation_health().get("writeable")):
                break
            time.sleep(2)

        text = self.browser.get_page_text() or ""
        health = self.browser.conversation_health()

        # parse latest user message
        latest_user = ""
        latest_ts = ""
        # find all "You said:" blocks
        matches = list(re.finditer(r"You said:\s*(.*?)(?=ChatGPT said:|You said:|$)", text, re.S))
        if matches:
            last = matches[-1].group(1).strip()
            latest_user = last
            # try to capture a timestamp near the preceding "You said:"
            # look backwards from the match start for a time-like token
            start = matches[-1].start()
            preceding = text[max(0, start-80):start]
            tm = re.search(r"(Today|Yesterday|\d{1,2}:\d{2}\s*(?:AM|PM)?|\w{3}\s+\d{1,2})", preceding)
            if tm:
                latest_ts = tm.group(0)

        self.state.latest_user_message = latest_user
        self.state.latest_user_message_at = latest_ts
        self._save_state()

        return {
            "ok": True,
            "project_url": project_url,
            "title": title,
            "conversation_id": cid,
            "conversation_url": self.state.conversation_url,
            "latest_user_message": latest_user,
            "latest_user_message_at": latest_ts,
            "composer_ready": bool(health.get("writeable")),
            "candidates": sel.get("candidates", []),
            "health": health,
        }

    def verify_conversation(self, expected_url: str = None) -> bool:
        expected = expected_url or self.state.conversation_url
        if not expected:
            self.state.last_error = "no expected conversation URL"
            self._save_state()
            return False
        actual = self.browser.current_url()
        # normalize trailing slashes
        if actual.rstrip("/") != expected.rstrip("/"):
            self.state.last_error = f"conversation mismatch: expected {expected}, got {actual}"
            self.state.status = "paused"
            self._save_state()
            return False
        return True

    def recover(self) -> bool:
        try:
            self.browser.stop()
        except Exception:
            pass
        ok = self.browser.start()
        if ok and self.state.conversation_url:
            self.browser.navigate(self.state.conversation_url)
        self.state.status = "ready" if ok else "error"
        self._save_state()
        return ok

    def start(self) -> bool:
        ok = self.browser.start()
        if ok and self.state.conversation_url:
            self.browser.navigate(self.state.conversation_url)
        self.state.status = "ready" if ok else "error"
        if not ok:
            self.state.last_error = "browser start failed"
        self._save_state()
        return ok

    def stop(self):
        self.browser.stop()
        self.state.status = "stopped"
        self._save_state()

    def pause(self):
        self.state.paused = True
        self._save_state()

    def resume(self):
        self.state.paused = False
        self._save_state()

    def cancel(self):
        self.state.status = "cancelled"
        self.state.paused = False
        self._save_state()

    def run_one_cycle(self) -> Dict[str, Any]:
        if self.state.paused:
            return {"ok": False, "reason": "paused"}
        if self.state.project_url and self.state.conversation_id:
            if not self.browser.open_project_conversation(self.state.project_url, self.state.conversation_id):
                return {"ok": False, "reason": "project conversation not found"}
        elif not self.state.conversation_url:
            return {"ok": False, "reason": "conversation URL not set"}
        else:
            if not self.browser.navigate(self.state.conversation_url):
                return {"ok": False, "reason": "navigation failed"}
        if not self.verify_conversation() and not (self.state.project_url and self.state.conversation_id):
            return {"ok": False, "reason": self.state.last_error}
            return {"ok": False, "reason": self.state.last_error}
        if not self.browser.wait_for_response(timeout=120.0):
            return {"ok": False, "reason": "chatgpt response timeout"}
        text = self.browser.get_page_text()
        task = extract_task_from_text(text)
        if not task:
            return {"ok": False, "reason": "no recognized task marker in ChatGPT response"}
        # submit to controller (awaits approval)
        meta = {"source": "chatgpt", "conversation_url": self.state.conversation_url}
        if self.model:
            meta["model"] = self.model
        res = self.task_controller.submit_task(task_text=task, metadata=meta, workspace=str(DEV_WORKSPACE))
        tid = res["task_id"]
        self.state.current_task_id = tid
        self.state.status = "awaiting_approval"
        self._save_state()
        return {"ok": True, "task_id": tid, "status": res.get("status"), "task_preview": task[:500]}

    def approve_current_task(self, approved_by: str = "operator") -> Dict[str, Any]:
        tid = self.state.current_task_id
        if not tid:
            return {"ok": False, "reason": "no current task"}
        ar = self.task_controller.approve_task(tid, approved_by=approved_by)
        if not ar.get("ok"):
            return ar
        # execute synchronously (supervised)
        self.task_controller.run_task_sync(tid)
        self.state.status = "executed"
        self._save_state()
        return {"ok": True, "task_id": tid, "execution": self.task_controller.get_status(tid)}

    def return_result_to_chatgpt(self) -> Dict[str, Any]:
        tid = self.state.current_task_id
        if not tid:
            return {"ok": False, "reason": "no current task"}
        r = self.task_controller.get_result(tid)
        if not r.get("ok"):
            return {"ok": False, "reason": "result not ready"}
        result = r.get("result") or {}
        msg = build_result_message(
            task_id=tid,
            status=r.get("status", ""),
            final_response=result.get("final_response", ""),
            report_path=(result.get("report_path") if isinstance(result, dict) else "") or "",
            test_summary=result.get("test_summary", "") if isinstance(result, dict) else "",
            git_status=result.get("git_status", "") if isinstance(result, dict) else "",
            blockers=r.get("error") or "",
        )
        ok = self.browser.submit_message(msg)
        if not ok:
            return {"ok": False, "reason": "browser submit failed"}
        verified = self.browser.verify_submitted(msg[:120])
        if not verified:
            self.state.status = "submission_uncertain"
            self._save_state()
            return {"ok": False, "reason": "submission not verified", "task_id": tid, "submitted": False}
        self.state.status = "result_submitted"
        self._save_state()
        return {"ok": True, "task_id": tid, "submitted": True, "verified": True}