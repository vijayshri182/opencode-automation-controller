import sys
sys.path.insert(0, "src")
from playwright.sync_api import sync_playwright

pw = sync_playwright().start()
b = pw.chromium.connect_over_cdp("http://127.0.0.1:9224")
ctx = b.contexts[0]
page = ctx.pages[0] if ctx.pages else ctx.new_page()
page.goto("https://chatgpt.com/", timeout=30000)
import time; time.sleep(5)
print("URL:", page.url)
print("TITLE:", page.title())
# Check several selectors
selectors = [
    "textarea",
    "button[aria-label='Send prompt']",
    "button:has-text('New chat')",
    "[data-testid='profile-button']",
    "nav",
    "button:has-text('Log in')",
    "button:has-text('Sign up')",
    "div[role='textbox']",
]
for s in selectors:
    try:
        nodes = page.query_selector_all(s)
        print(f"{s}: {len(nodes)}")
    except Exception as e:
        print(f"{s}: ERROR {e}")
# Print outer html snippet of body (first 500 chars) maybe
print("BODY_SNIPPET:", (page.content() or "")[:300].replace("\n"," "))
pw.stop()