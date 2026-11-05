import sys, time
sys.path.insert(0, "src")
from playwright.sync_api import sync_playwright

pw = sync_playwright().start()
b = pw.chromium.connect_over_cdp("http://127.0.0.1:9224")
ctx = b.contexts[0]
page = ctx.pages[0] if ctx.pages else ctx.new_page()
time.sleep(8)
print("URL:", page.url)
print("TITLE:", page.title())
sidebar = page.query_selector("nav") or page.query_selector("aside")
if sidebar:
    txt = (sidebar.inner_text() or "")
    print("SIDEBAR_TEXT:\n", txt)
pw.stop()
print("done")