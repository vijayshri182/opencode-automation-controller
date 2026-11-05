import sys
sys.path.insert(0, "src")
from playwright.sync_api import sync_playwright

pw = sync_playwright().start()
b = pw.chromium.connect_over_cdp("http://127.0.0.1:9224")
ctx = b.contexts[0]
page = ctx.pages[0] if ctx.pages else ctx.new_page()
page.goto("https://chatgpt.com/", timeout=30000)
import time; time.sleep(5)
btns = page.query_selector_all("button")
print("button count:", len(btns))
for btn in btns[:40]:
    try:
        print(repr(btn.get_attribute("aria-label")), "|", (btn.inner_text() or "")[:40])
    except Exception as e:
        print("err", e)
pw.stop()