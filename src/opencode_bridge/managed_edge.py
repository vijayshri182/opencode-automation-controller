import json
import os
import subprocess
import time
import urllib.request
from pathlib import Path
from typing import Optional

from .config import edge_executable_path

DEFAULT_CDP_PORT = 9224
DEFAULT_PROFILE_DIR = ".edge-profile-automation"


class ManagedEdgeError(Exception):
    pass


class ManagedEdgeLauncher:
    def __init__(self, profile_dir: str, port: int = DEFAULT_CDP_PORT, executable_path: Optional[str] = None):
        self.profile_dir = str(Path(profile_dir).resolve())
        self.port = port
        self.executable_path = executable_path or edge_executable_path()
        self._process = None

    def _cdp_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def is_healthy(self) -> bool:
        try:
            with urllib.request.urlopen(f"{self._cdp_url()}/json/version", timeout=3) as resp:
                data = json.loads(resp.read().decode())
                browser = data.get("Browser", "")
                return "Edge" in browser or "Edg" in browser
        except Exception:
            return False

    def start(self) -> bool:
        if self.is_healthy():
            return True
        if not os.path.exists(self.executable_path) or "msedge.exe" not in self.executable_path.lower():
            raise ManagedEdgeError("Microsoft Edge executable not found or invalid.")
        Path(self.profile_dir).mkdir(parents=True, exist_ok=True)
        args = [
            self.executable_path,
            f"--remote-debugging-port={self.port}",
            f"--user-data-dir={self.profile_dir}",
            "--no-first-run",
            "--no-default-browser-check",
        ]
        self._process = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        deadline = time.time() + 15
        while time.time() < deadline:
            if self.is_healthy():
                return True
            if self._process.poll() is not None:
                raise ManagedEdgeError("Edge process exited during startup.")
            time.sleep(0.5)
        raise ManagedEdgeError("CDP endpoint did not become healthy.")

    def stop(self):
        if self._process and self._process.poll() is None:
            self._process.terminate()
            try:
                self._process.wait(timeout=10)
            except Exception:
                self._process.kill()
        self._process = None

    def cdp_url(self) -> str:
        return self._cdp_url()


class CdpEdgeAdapter:
    """BrowserAdapter using CDP attachment to a managed Edge instance."""

    def __init__(self, launcher: ManagedEdgeLauncher, conversation_url: str = "", headless: bool = False, attach_only: bool = False, user_data_dir: Optional[str] = None):
        self.launcher = launcher
        self.conversation_url = conversation_url
        self.headless = headless
        # WP-421A: attach_only never launches/spawns Edge; it requires an
        # already-running CDP endpoint.
        self.attach_only = attach_only
        # WP-422: enables the DevToolsActivePort (edge://inspect) attach route.
        self.user_data_dir = user_data_dir
        self._attached = False
        self.last_attach_info = {}
        self._pw = None
        self._browser = None
        self._context = None
        self._page = None

    def attach_existing(self, project_url: str = None, wait_seconds: float = None, user_data_dir: str = None) -> dict:
        """WP-421A/WP-422: connect to the running Edge and reuse an existing tab."""
        from .edge_attach import (
            DEFAULT_READY_WAIT,
            PALMISTRY_PROJECT_URL,
            attach_existing_edge,
        )

        info = attach_existing_edge(
            cdp_url=self.launcher.cdp_url(),
            project_url=project_url or PALMISTRY_PROJECT_URL,
            wait_seconds=DEFAULT_READY_WAIT if wait_seconds is None else wait_seconds,
            user_data_dir=user_data_dir or self.user_data_dir,
        )
        self.last_attach_info = {
            k: v for k, v in info.items() if k not in ("page", "browser", "playwright")
        }
        if info.get("ok"):
            self._pw = info.get("playwright") or self._pw
            self._browser = info.get("browser")
            self._page = info.get("page")
            selected = info.get("selected") or {}
            # Recover the owning context of the borrowed page.
            try:
                self._context = self._page.context
            except Exception:
                self._context = None
            self._attached = True
            self.conversation_url = info.get("current_url") or selected.get("url") or self.conversation_url
        return info

    def start(self) -> bool:
        if self.attach_only:
            # Never launch. Attach to the existing endpoint or fail.
            info = self.attach_existing()
            if not info.get("ok"):
                raise ManagedEdgeError(
                    f"CDP attach failed ({info.get('reason')}): {info.get('error')}"
                )
            return True
        try:
            from playwright.sync_api import sync_playwright
        except Exception as e:
            raise RuntimeError(f"Playwright not installed: {e}")
        self.launcher.start()
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.connect_over_cdp(self.launcher.cdp_url())
        contexts = self._browser.contexts
        self._context = contexts[0] if contexts else self._browser.new_context()
        pages = self._context.pages
        self._page = pages[0] if pages else self._context.new_page()
        if self.conversation_url:
            self._page.goto(self.conversation_url)
        return True

    def stop(self):
        if self._attached:
            # WP-421A: borrowed browser — disconnect only, leave Edge running.
            # Do not call browser.close(): that can clear CDP-created contexts.
            try:
                if self._pw:
                    self._pw.stop()
            except Exception:
                pass
            self._page = None
            self._context = None
            self._browser = None
            self._attached = False
            return
        try:
            if self._browser:
                self._browser.close()
        except Exception:
            pass
        try:
            if self._pw:
                self._pw.stop()
        except Exception:
            pass
        # Keep managed Edge running for reuse.

    def terminate_managed(self):
        """Drop the connection; only terminate a browser this adapter launched.

        WP-422: in attach-only mode the browser belongs to the operator, so the
        launcher is never touched — no terminate, no kill, no close.
        """
        self.stop()
        if self.attach_only:
            return
        self.launcher.stop()

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
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                if self._page.query_selector("button[aria-label='Stop generating']") is None:
                    return True
            except Exception:
                return True
            time.sleep(0.5)
        return False

    def extract_last_assistant_text(self) -> str:
        if not self._page:
            return ""
        try:
            nodes = self._page.query_selector_all("div[data-message-author-role='assistant']")
            if nodes:
                return nodes[-1].inner_text()
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
            textarea = self._page.query_selector("textarea")
            if textarea is None:
                return False
            textarea.fill(text)
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
            snippet = text.strip()[:80]
            deadline = time.time() + 10
            while time.time() < deadline:
                if snippet and snippet in (self._page.inner_text("body") or ""):
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
            proj_btn = self._page.query_selector("button:has-text('Projects'), a:has-text('Projects')")
            if proj_btn:
                proj_btn.click()
                import time
                time.sleep(3)
            proj_link = self._page.query_selector(f"a:has-text('{project_name}'), button:has-text('{project_name}')")
            if proj_link:
                proj_link.click()
                time.sleep(4)
            conv = self._page.query_selector(f"a:has-text('{conversation_title}')")
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
            deadline = time.time() + 20
            while time.time() < deadline:
                links = self._page.query_selector_all("a[href*='/c/']")
                if links:
                    break
                time.sleep(1)
            links = self._page.query_selector_all("a[href*='/c/']")
            project_slug = ""
            try:
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
                    title = (l.inner_text() or "").strip().replace("\n", " ")
                except Exception:
                    href = ""; title = ""
                if not href or "/c/" not in href:
                    continue
                if project_slug and project_slug not in href:
                    continue
                cid_check = ""
                if "/c/" in href:
                    cid_check = href.split("/c/")[-1].split("?")[0].split("#")[0]
                if cid_check and cid_check in seen_ids:
                    continue
                if cid_check:
                    seen_ids.add(cid_check)
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
        clicked = False
        try:
            links = self._page.query_selector_all("a[href*='/c/']")
            target = None
            for l in links:
                try:
                    href = l.get_attribute("href") or ""
                    title = (l.inner_text() or "").strip()
                except Exception:
                    href = ""; title = ""
                if chosen["conversation_id"] and chosen["conversation_id"] in href:
                    target = l; break
                if not target and chosen["title"] and chosen["title"] in title:
                    target = l; break
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
            content = self._page.content() or ""
            if "chatgpt.com" not in self._page.url:
                return False
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
                btn = self._page.query_selector("button:has-text('New chat')")
            if btn is None:
                return ""
            btn.click()
            import time
            time.sleep(3)
            return self._page.url
        except Exception:
            return ""
