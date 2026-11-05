import sys
sys.path.insert(0, "src")
from playwright.sync_api import sync_playwright

pw = sync_playwright().start()
b = pw.chromium.connect_over_cdp("http://127.0.0.1:9224")
ctx = b.contexts[0]
page = ctx.pages[0] if ctx.pages else ctx.new_page()
page.goto("https://chatgpt.com/", timeout=30000)
import time; time.sleep(5)
selectors = [
    "div[role='textbox']",
    "#prompt-textarea",
    "button[data-testid='send-button']",
    "button[aria-label='Send prompt']",
    "button[aria-label='Send message']",
    "button:has-text('New chat')",
    "nav a",
]
for s in selectors:
    try:
        print(f"{s}: {len(page.query_selector_all(s))}")
    except Exception as e:
        print(f"{s}: ERROR {e}")
pw.stop()