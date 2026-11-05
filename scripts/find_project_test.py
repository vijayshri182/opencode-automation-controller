import sys, time
sys.path.insert(0, "src")
from playwright.sync_api import sync_playwright

pw = sync_playwright().start()
b = pw.chromium.connect_over_cdp("http://127.0.0.1:9224")
ctx = b.contexts[0]
page = ctx.pages[0] if ctx.pages else ctx.new_page()
page.goto("https://chatgpt.com/g/g-p-6ae87c1e48b08191a2cd33139c40639f/project", timeout=30000, wait_until="domcontentloaded")
time.sleep(10)
links = page.query_selector_all("a")
print("total links:", len(links))
found = []
for l in links:
    href = l.get_attribute("href") or ""
    txt = (l.inner_text() or "").strip()
    if "/c/" in href and "Project Test" in txt:
        found.append((href, txt))
        print("FOUND:", href, "|", txt.replace("\n"," ")[:80])
if not found:
    print("No exact 'Project Test' link found. Listing /c/ links:")
    seen = set()
    for l in links:
        href = l.get_attribute("href") or ""
        txt = (l.inner_text() or "").strip()
        if "/c/" in href and href not in seen:
            seen.add(href)
            print("  ", href, "|", txt[:60].replace("\n"," "))
pw.stop()
print("done")