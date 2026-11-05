import sys, time
sys.path.insert(0, "src")
from playwright.sync_api import sync_playwright

pw = sync_playwright().start()
b = pw.chromium.connect_over_cdp("http://127.0.0.1:9224")
ctx = b.contexts[0]
page = ctx.pages[0] if ctx.pages else ctx.new_page()
page.goto("https://chatgpt.com/g/g-p-6ae87c1e48b08191a2cd33139c40639f/project", timeout=30000, wait_until="domcontentloaded")
time.sleep(8)
print("URL:", page.url)
print("TITLE:", page.title())
links = page.query_selector_all("a")
print("total links:", len(links))
found = False
for l in links:
    href = l.get_attribute("href") or ""
    if "6ae8462d" in href:
        found = True
        print("FOUND:", href, (l.inner_text() or "")[:40])
if not found:
    print("NOT FOUND in links")
    # search page content
    content = page.content() or ""
    print("ID in content:", "6ae8462d-8234-83ee-add5-6d72dabaac15" in content)
pw.stop()
print("done")