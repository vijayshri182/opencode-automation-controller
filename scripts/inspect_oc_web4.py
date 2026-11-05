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
time.sleep(5)
# Click New session using locator
try:
    page.get_by_role("button", name="New session").click(timeout=5000)
    time.sleep(4)
    print("clicked new session")
except Exception as e:
    print("click err", e)
print("URL:", page.url)
print("TITLE:", page.title())
for sel in ["textarea", "input", "button", "div[contenteditable='true']"]:
    try:
        print(sel, ":", len(page.query_selector_all(sel)))
    except Exception as e:
        print(sel, "ERROR", e)
# find composer: maybe a div with role textbox after clicking
for sel in ["textarea", "input", "div[contenteditable='true']", "[role='textbox']", "div[role='presentation']"]:
    els = page.query_selector_all(sel)
    for el in els:
        try:
            print("CANDIDATE", sel, repr(el.get_attribute("placeholder")), (el.inner_text() or "")[:40])
        except Exception:
            pass
btns = page.query_selector_all("button")
print("buttons:", len(btns))
for btn in btns:
    try:
        al = btn.get_attribute("aria-label")
        txt = (btn.inner_text() or "")[:30]
        if al or "send" in txt.lower():
            print(" BTN", repr(al), txt)
    except Exception:
        pass
pwctx.stop()
print("done")