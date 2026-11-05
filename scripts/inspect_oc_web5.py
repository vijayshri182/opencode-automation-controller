import sys, time
sys.path.insert(0, "src")
from opencode_bridge.config import opencode_username, opencode_password
from playwright.sync_api import sync_playwright

user = opencode_username()
pw = opencode_password()
auth_url = f"http://{user}:{pw}@127.0.0.1:4097"

pwctx = sync_playwright().start()
b = pwctx.chromium.connect_over_cdp("http://127.0.0.1:9224")
ctx = b.contexts[0]
page = ctx.new_page()
page.goto(auth_url, timeout=15000, wait_until="domcontentloaded")
time.sleep(6)
print("URL before click:", page.url)
# Try clicking New session
try:
    page.get_by_text("New session").click(timeout=5000)
    print("clicked")
except Exception as e:
    print("click err", e)
time.sleep(8)
print("URL after click:", page.url)
print("TITLE:", page.title())
# Dump all elements with role textbox or contenteditable
for sel in ["*", "div", "span", "p"]:
    pass
# Try to find any element containing 'prompt' or 'message'
content = page.content()
print("has 'prompt':", "prompt" in content.lower())
print("has 'message':", "message" in content.lower())
# list all buttons again
btns = page.query_selector_all("button")
print("buttons:", len(btns))
for btn in btns:
    try:
        print(" BTN", repr(btn.get_attribute("aria-label")), (btn.inner_text() or "")[:40])
    except Exception:
        pass
pwctx.stop()
print("done")