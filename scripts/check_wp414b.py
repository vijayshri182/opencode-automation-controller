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
# get all text
txt = page.inner_text("body") if page.query_selector("body") else ""
print("BODY_LEN:", len(txt))
# find WP414_OK
idx = txt.find("WP414_OK")
if idx >= 0:
    print("WP414_OK found at", idx)
    print("SNIPPET:", txt[max(0,idx-100):idx+100])
pw.stop()
print("done")