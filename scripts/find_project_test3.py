import sys, time
sys.path.insert(0, "src")
from playwright.sync_api import sync_playwright

target = "6ae87c0a-10c8-83ee-a666-c3a5cfea6521"
pw = sync_playwright().start()
b = pw.chromium.connect_over_cdp("http://127.0.0.1:9224")
ctx = b.contexts[0]
page = ctx.pages[0] if ctx.pages else ctx.new_page()
page.goto("https://chatgpt.com/g/g-p-6ae87c1e48b08191a2cd33139c40639f/project", timeout=30000, wait_until="domcontentloaded")
time.sleep(12)
links = page.query_selector_all("a")
print("total links:", len(links))
found = False
for l in links:
    href = l.get_attribute("href") or ""
    txt = (l.inner_text() or "").strip()
    if target in href:
        found = True
        print("FOUND:", href, "|", txt.replace("\n"," ")[:80])
        break
if not found:
    print("NOT FOUND. Searching page content...")
    content = page.content() or ""
    print("ID in content:", target in content)
    # list some /c/ links
    seen = set()
    for l in links:
        href = l.get_attribute("href") or ""
        if "/c/" in href and href not in seen:
            seen.add(href)
            if len(seen) <= 10:
                print("  ", href)
pw.stop()
print("done")