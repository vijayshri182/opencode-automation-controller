"""WP-421A: attach to the already-running managed Edge over CDP.

This module intentionally contains **no launch path**. It never calls
``chromium.launch()`` / ``launch_persistent_context()`` and never spawns a
process; it only connects to an existing CDP endpoint, enumerates the tabs that
are already open, and reuses the best one.

If the endpoint is unreachable the caller receives a structured blocked result
with the exact error. There is no fallback that opens a browser.
"""

import os
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from .managed_edge import DEFAULT_CDP_PORT

# Managed Edge CDP endpoint (WP-419 / WP-421 / WP-422). Single configured port:
# 9224, overridable by EDGE_CDP_URL for diagnostics only.
CDP_URL = os.environ.get("EDGE_CDP_URL") or f"http://127.0.0.1:{DEFAULT_CDP_PORT}"

# Default Edge profile location (the operator's normal browser).
DEFAULT_EDGE_USER_DATA_DIR = str(
    Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "Edge" / "User Data"
)

# Fixed Palmistry Project entry point.
PALMISTRY_PROJECT_URL = (
    "https://chatgpt.com/g/g-p-6ae87c1e48b08191a2cd33139c40639f/project"
)
PALMISTRY_PROJECT_ID = "g-p-6ae87c1e48b08191a2cd33139c40639f"
PALMISTRY_PROJECT_NAME = "Palmistry"

CHAT_HOST = "chatgpt.com"

# Tab ranks (lower wins).
RANK_PROJECT = 0
RANK_CHATGPT = 1
RANK_OTHER = 9

DEFAULT_READY_WAIT = 20.0


class CdpAttachError(Exception):
    """Raised by callers that require a hard failure instead of a blocked result."""


class CdpLaunchForbidden(RuntimeError):
    """Guards against accidental browser launch in the attach path."""


def classify_tab(url: str, title: str = "", project_url: str = PALMISTRY_PROJECT_URL) -> Dict[str, Any]:
    """Rank an already-open tab for reuse. Pure function (unit-testable)."""
    url = url or ""
    project_id = PALMISTRY_PROJECT_ID
    for part in (project_url or "").split("/"):
        if part.startswith("g-p-"):
            project_id = part
            break

    if project_id and project_id in url:
        # Project root page, or a conversation opened inside the project.
        kind = "project_conversation" if "/c/" in url else "project"
        return {"rank": RANK_PROJECT, "kind": kind, "eligible": True}

    if CHAT_HOST in url:
        return {"rank": RANK_CHATGPT, "kind": "chatgpt", "eligible": True}

    return {"rank": RANK_OTHER, "kind": "other", "eligible": False}


def _tab_snapshot(page, context_index: int, page_index: int, project_url: str) -> Dict[str, Any]:
    url = ""
    title = ""
    try:
        url = page.evaluate("() => window.location.href", timeout=2000) or ""
    except Exception:
        try:
            url = page.url or ""
        except Exception:
            url = ""
    try:
        title = page.evaluate("() => document.title", timeout=2000) or ""
    except Exception:
        try:
            title = page.title() or ""
        except Exception:
            title = ""

    cls = classify_tab(url, title, project_url)
    return {
        "context_index": context_index,
        "page_index": page_index,
        "url": url,
        "title": title,
        "kind": cls["kind"],
        "rank": cls["rank"],
        "eligible": cls["eligible"],
        "page": page,
    }


def _count_conversation_links(page) -> int:
    try:
        return len(page.query_selector_all("a[href*='/c/']") or [])
    except Exception:
        return 0


def _await_project_ready(page, started: bool, wait_seconds: float, project_url: str) -> Dict[str, Any]:
    """Bounded readiness wait: project page rendered + conversation list present."""
    url = ""
    try:
        url = page.url or ""
    except Exception:
        url = ""

    # Only wait when we just navigated; a reused tab should already be stable.
    deadline = time.time() + (wait_seconds if started else min(wait_seconds, 5.0))
    links = 0
    text = ""
    while True:
        links = _count_conversation_links(page)
        try:
            text = page.inner_text("body") or ""
        except Exception:
            try:
                text = page.content() or ""
            except Exception:
                text = ""
        if links > 0 or not started:
            break
        if time.time() >= deadline:
            break
        time.sleep(1.0)

    try:
        url = page.url or url
    except Exception:
        pass

    on_project = PALMISTRY_PROJECT_ID in url
    authenticated = ("Log in" not in text) and ("Sign up" not in text) and bool(text.strip())
    project_marker = PALMISTRY_PROJECT_NAME.lower() in (text or "").lower()
    return {
        "url": url,
        "on_project": on_project,
        "conversation_links": links,
        "conversation_list_rendered": links > 0,
        "authenticated": authenticated,
        "project_marker": project_marker,
        "project_verified": on_project or project_marker,
        "text_len": len(text or ""),
    }


def discover_ws_endpoint(user_data_dir: str) -> Dict[str, Any]:
    """Read ``DevToolsActivePort`` and build the browser WebSocket endpoint.

    Edge/Chrome 144+ can enable debugging on the *real* profile from
    ``edge://inspect/#remote-debugging``. On that route HTTP discovery
    (``/json/version``) may be unavailable, but the browser still writes
    ``DevToolsActivePort`` (line 1 = port, line 2 = browser ws path).
    """
    out: Dict[str, Any] = {"ok": False, "reason": "", "ws_endpoint": "", "port": None}
    if not user_data_dir:
        out["reason"] = "no_user_data_dir"
        return out
    path = Path(user_data_dir) / "DevToolsActivePort"
    if not path.exists():
        out["reason"] = "devtools_active_port_absent"
        return out
    try:
        lines = [ln.strip() for ln in path.read_text(encoding="utf-8", errors="replace").splitlines() if ln.strip()]
    except Exception as exc:
        out["reason"] = "devtools_active_port_unreadable"
        out["error"] = f"{type(exc).__name__}: {exc}"
        return out
    if len(lines) < 2 or not lines[0].isdigit():
        out["reason"] = "devtools_active_port_malformed"
        return out
    port = int(lines[0])
    ws_path = lines[1]
    if not ws_path.startswith("/"):
        ws_path = "/" + ws_path
    out.update(
        {
            "ok": True,
            "reason": "devtools_active_port",
            "port": port,
            "ws_endpoint": f"ws://127.0.0.1:{port}{ws_path}",
        }
    )
    return out


def _connect(chromium, endpoint: str):
    return chromium.connect_over_cdp(endpoint)


def attach_existing_edge(
    cdp_url: str = CDP_URL,
    project_url: str = PALMISTRY_PROJECT_URL,
    playwright=None,
    wait_seconds: float = DEFAULT_READY_WAIT,
    verify: bool = True,
    navigate_if_needed: bool = True,
    user_data_dir: Optional[str] = None,
) -> Dict[str, Any]:
    """Attach to an existing Edge over CDP and reuse the best open tab.

    Returns a structured result. ``ok`` is False for every blocked case; the
    ``reason`` is a stable machine-readable code and ``error`` carries the exact
    browser/Playwright message. A fresh browser is never launched.

    ``user_data_dir`` enables the ``DevToolsActivePort`` fallback used by Edge's
    ``edge://inspect/#remote-debugging`` opt-in, where HTTP discovery is not
    available but the browser WebSocket is.
    """
    result: Dict[str, Any] = {
        "ok": False,
        "reason": "",
        "error": "",
        "cdp_url": cdp_url,
        "project_url": project_url,
        "discovery": "websocket" if str(cdp_url).startswith("ws") else "http",
        "attempted_endpoints": [],
        "attached_to_existing_browser": False,
        "launched_new_browser": False,
        "contexts": 0,
        "tabs": [],
        "selected": None,
        "navigated": False,
        "navigation_url": "",
        "project_verified": False,
        "authenticated": False,
        "conversation_list_rendered": False,
        "conversation_links": 0,
    }

    owned_pw = False
    if playwright is None:
        try:
            from playwright.sync_api import sync_playwright
        except Exception as exc:  # pragma: no cover - environment dependent
            result["reason"] = "playwright_unavailable"
            result["error"] = f"{type(exc).__name__}: {exc}"
            return result
        try:
            playwright = sync_playwright().start()
            owned_pw = True
        except Exception as exc:  # pragma: no cover - environment dependent
            result["reason"] = "playwright_start_failed"
            result["error"] = f"{type(exc).__name__}: {exc}"
            return result

    result["playwright"] = playwright if owned_pw else None
    result["playwright_owned"] = owned_pw

    chromium = playwright.chromium
    if not hasattr(chromium, "connect_over_cdp"):
        result["reason"] = "chromium_api_unavailable"
        result["error"] = "chromium has no connect_over_cdp; refusing to launch"
        return result

    endpoints = [cdp_url]
    browser = None
    errors: List[str] = []
    while endpoints:
        endpoint = endpoints.pop(0)
        result["attempted_endpoints"].append(endpoint)
        try:
            browser = _connect(chromium, endpoint)
            result["cdp_url"] = endpoint
            break
        except Exception as exc:
            errors.append(f"{endpoint} -> {type(exc).__name__}: {exc}")
            if user_data_dir and not str(endpoint).startswith("ws") and not endpoints:
                ws = discover_ws_endpoint(user_data_dir)
                result["devtools_active_port"] = ws
                if ws["ok"]:
                    endpoints.append(ws["ws_endpoint"])
                    result["discovery"] = "devtools_active_port"

    if browser is None:
        result["reason"] = "cdp_connect_failed"
        result["error"] = "\n".join(errors)
        if owned_pw:
            try:
                playwright.stop()
            except Exception:
                pass
        result["playwright"] = None
        return result

    result["attached_to_existing_browser"] = True
    result["browser"] = browser

    # Enumerate existing contexts and pages. Nothing is created here.
    try:
        contexts = list(browser.contexts or [])
    except Exception as exc:
        result["reason"] = "context_enumeration_failed"
        result["error"] = f"{type(exc).__name__}: {exc}"
        return result
    result["contexts"] = len(contexts)

    tabs: List[Dict[str, Any]] = []
    for ci, ctx in enumerate(contexts):
        try:
            pages = list(ctx.pages or [])
        except Exception:
            pages = []
        for pi, page in enumerate(pages):
            tabs.append(_tab_snapshot(page, ci, pi, project_url))

    result["tabs"] = [
        {k: v for k, v in t.items() if k != "page"} for t in tabs
    ]

    eligible = [t for t in tabs if t["eligible"]]
    if not eligible:
        result["reason"] = "no_suitable_tab"
        result["error"] = (
            f"no ChatGPT tab found among {len(tabs)} open tab(s) on {cdp_url}"
        )
        return result

    # Deterministic: lowest rank, then context index, then page index.
    chosen = sorted(eligible, key=lambda t: (t["rank"], t["context_index"], t["page_index"]))[0]
    page = chosen["page"]
    result["selected"] = {k: v for k, v in chosen.items() if k != "page"}

    navigated = False
    if chosen["rank"] == RANK_CHATGPT:
        if not navigate_if_needed:
            result["reason"] = "chatgpt_tab_not_on_project"
            result["error"] = f"existing ChatGPT tab is at {chosen['url']}"
            return result
        try:
            page.goto(project_url, wait_until="domcontentloaded", timeout=45000)
            navigated = True
            result["navigated"] = True
            result["navigation_url"] = project_url
        except Exception as exc:
            result["reason"] = "navigation_failed"
            result["error"] = f"{type(exc).__name__}: {exc}"
            return result

    result["page"] = page

    if verify:
        ready = _await_project_ready(page, navigated, wait_seconds, project_url)
        result.update(
            {
                "project_verified": ready["project_verified"],
                "authenticated": ready["authenticated"],
                "conversation_list_rendered": ready["conversation_list_rendered"],
                "conversation_links": ready["conversation_links"],
                "current_url": ready["url"],
                "body_text_len": ready["text_len"],
            }
        )
        if not ready["authenticated"] and ready["text_len"] > 0:
            result["reason"] = "not_authenticated"
            result["error"] = "ChatGPT sign-in page detected in the reused tab"
            return result
        if not ready["project_verified"]:
            result["reason"] = "project_not_verified"
            result["error"] = f"reused tab does not show the project: {ready['url']}"
            return result

    result["ok"] = True
    result["reason"] = "reused_project_tab" if not navigated else "navigated_existing_chatgpt_tab"
    return result


def detach(result: Dict[str, Any]) -> None:
    """Disconnect Playwright without closing the user's browser or contexts."""
    pw = (result or {}).get("playwright")
    if pw is None:
        return
    try:
        pw.stop()
    except Exception:
        pass
