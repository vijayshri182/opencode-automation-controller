import sys, time
sys.path.insert(0, "src")
from playwright.sync_api import sync_playwright

pw = sync_playwright().start()
b = pw.chromium.connect_over_cdp("http://127.0.0.1:9224")
ctx = b.contexts[0]
page = ctx.pages[0] if ctx.pages else ctx.new_page()
page.goto("https://chatgpt.com/g/g-p-6ae87c1e48b08191a2cd33139c40639f/project", timeout=30000, wait_until="networkidle")
time.sleep(5)
# find all links with /c/
links = page.query_selector_all("a[href*='/c/']")
print("total conv links:", len(links))
seen = set()
for l in links:
    href = l.get_attribute("href")
    txt = (l.inner_text() or "").strip()
    if href and href not in seen:
        seen.add(href)
        print("LINK:", href, "|", txt[:60])
pw.stop()
print("done")