import sys, time
sys.path.insert(0, "src")
from playwright.sync_api import sync_playwright

pw = sync_playwright().start()
b = pw.chromium.connect_over_cdp("http://127.0.0.1:9224")
ctx = b.contexts[0]
page = ctx.pages[0] if ctx.pages else ctx.new_page()
time.sleep(2)
print("URL:", page.url)
print("TITLE:", page.title())
for sel in ["textarea", "div[role='textbox']", "div[contenteditable='true']", "input"]:
    try:
        print(sel, ":", len(page.query_selector_all(sel)))
    except Exception as e:
        print(sel, "ERR", e)
btns = page.query_selector_all("button")
print("buttons:", len(btns))
for btn in btns[:15]:
    try:
        print(" BTN", repr(btn.get_attribute("aria-label")), (btn.inner_text() or "")[:20])
    except Exception:
        pass
pw.stop()
print("done")