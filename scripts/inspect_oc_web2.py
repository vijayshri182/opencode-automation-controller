import sys, time
sys.path.insert(0, "src")
from opencode_bridge.config import opencode_username, opencode_password
from playwright.sync_api import sync_playwright

user = opencode_username()
pw = opencode_password()
url = f"http://{user}:{pw}@127.0.0.1:4097"
print("using auth url (secret redacted)")

pwctx = sync_playwright().start()
b = pwctx.chromium.connect_over_cdp("http://127.0.0.1:9224")
ctx = b.contexts[0]
page = ctx.new_page()
page.goto(url, timeout=15000, wait_until="domcontentloaded")
time.sleep(6)
print("URL:", page.url)
print("TITLE:", page.title())
for sel in ["textarea", "input", "button", "div[contenteditable='true']"]:
    try:
        print(sel, ":", len(page.query_selector_all(sel)))
    except Exception as e:
        print(sel, "ERROR", e)
btns = page.query_selector_all("button")
print("buttons:", len(btns))
for btn in btns[:20]:
    try:
        print(" BTN", repr(btn.get_attribute("aria-label")), (btn.inner_text() or "")[:30])
    except Exception:
        pass
pwctx.stop()
print("done")