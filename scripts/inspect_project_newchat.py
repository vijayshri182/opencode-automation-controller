import sys, time
sys.path.insert(0, "src")
from playwright.sync_api import sync_playwright

url = "https://chatgpt.com/g/g-p-6ae87c1e48b08191a2cd33139c40639f/project"
pw = sync_playwright().start()
b = pw.chromium.connect_over_cdp("http://127.0.0.1:9224")
ctx = b.contexts[0]
page = ctx.pages[0] if ctx.pages else ctx.new_page()
page.goto(url, timeout=30000, wait_until="domcontentloaded")
time.sleep(6)
print("URL:", page.url)
print("TITLE:", page.title())
# find new chat buttons
for sel in ["button:has-text('New chat')", "a:has-text('New chat')", "[aria-label*='New chat']"]:
    try:
        els = page.query_selector_all(sel)
        print(sel, ":", len(els))
        for el in els[:5]:
            print("  ", repr(el.get_attribute("aria-label")), (el.inner_text() or "")[:40], "href=", el.get_attribute("href"))
    except Exception as e:
        print(sel, "ERR", e)
pw.stop()
print("done")