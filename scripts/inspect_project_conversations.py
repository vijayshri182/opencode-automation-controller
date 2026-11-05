import sys, time
sys.path.insert(0, "src")
from playwright.sync_api import sync_playwright

pw = sync_playwright().start()
b = pw.chromium.connect_over_cdp("http://127.0.0.1:9224")
ctx = b.contexts[0]
page = ctx.pages[0] if ctx.pages else ctx.new_page()
page.goto("https://chatgpt.com/g/g-p-6ae87c1e48b08191a2cd33139c40639f/project", timeout=30000, wait_until="domcontentloaded")
time.sleep(6)
links = page.query_selector_all("a[href*='/c/']")
print("conversation links:", len(links))
for l in links[:15]:
    print(" LINK", l.get_attribute("href"), (l.inner_text() or "")[:40])
pw.stop()
print("done")