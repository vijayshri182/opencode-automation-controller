import sys, time
sys.path.insert(0, "src")
from playwright.sync_api import sync_playwright

def attach():
    pw = sync_playwright().start()
    b = pw.chromium.connect_over_cdp("http://127.0.0.1:9224")
    ctx = b.contexts[0]
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    url = page.url
    pw.stop()
    return url

u1 = attach()
print("First attach URL:", u1)
time.sleep(1)
u2 = attach()
print("Second attach URL:", u2)
print("Reattach OK:", u1 == u2)