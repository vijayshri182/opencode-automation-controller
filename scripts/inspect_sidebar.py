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
# find sidebar projects
for sel in ["button:has-text('Projects')", "a:has-text('Projects')", "nav", "aside"]:
    try:
        els = page.query_selector_all(sel)
        print(sel, ":", len(els))
    except Exception as e:
        print(sel, "ERR", e)
# list sidebar items text
sidebar = page.query_selector("nav") or page.query_selector("aside")
if sidebar:
    txt = (sidebar.inner_text() or "")[:500]
    print("SIDEBAR:", txt.replace("\n"," | "))
pw.stop()
print("done")