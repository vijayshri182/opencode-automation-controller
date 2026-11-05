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
# get body text
body = page.query_selector("body")
if body:
    txt = (body.inner_text() or "")[:1000]
    print("BODY:", txt.replace("\n"," ")[:500])
# check for any element with contenteditable
all_els = page.query_selector_all("*")
print("total elements:", len(all_els))
# find elements containing "Project Test"
for el in all_els:
    try:
        t = el.inner_text() or ""
        if "Project Test" in t and len(t) < 200:
            print("FOUND TEXT:", t[:100])
            break
    except Exception:
        pass
pw.stop()
print("done")