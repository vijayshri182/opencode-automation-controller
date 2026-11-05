import sys
sys.path.insert(0, "src")
from playwright.sync_api import sync_playwright

pw = sync_playwright().start()
b = pw.chromium.connect_over_cdp("http://127.0.0.1:9224")
ctx = b.contexts[0]
page = ctx.pages[0] if ctx.pages else ctx.new_page()
page.goto("https://chatgpt.com/", timeout=30000)
import time; time.sleep(5)
box = page.query_selector("div[role='textbox']")
if box:
    box.click()
    page.keyboard.type("hello test")
    time.sleep(2)
btns = page.query_selector_all("button")
print("button count:", len(btns))
for btn in btns:
    try:
        al = btn.get_attribute("aria-label")
        txt = (btn.inner_text() or "")[:30]
        if al or "send" in txt.lower() or "arrow" in (btn.get_attribute("class") or "").lower():
            print(repr(al), "|", txt)
    except Exception as e:
        print("err", e)
pw.stop()