import sys, time
sys.path.insert(0, "src")
from playwright.sync_api import sync_playwright

pw = sync_playwright().start()
b = pw.chromium.connect_over_cdp("http://127.0.0.1:9224")
ctx = b.contexts[0]
page = ctx.pages[0] if ctx.pages else ctx.new_page()
page.goto("https://chatgpt.com/g/g-p-6ae87c1e48b08191a2cd33139c40639f/project", timeout=30000, wait_until="domcontentloaded")
for attempt in range(5):
    time.sleep(5)
    try:
        links = page.query_selector_all("a")
        seen = set()
        for l in links:
            href = l.get_attribute("href") or ""
            txt = (l.inner_text() or "").strip()
            if "/c/" in href and href not in seen:
                seen.add(href)
                if "Project Test" in txt or "Test project" in txt:
                    print("FOUND:", href, "|", txt.replace("\n"," ")[:80])
        if seen:
            print("total conv links:", len(seen))
            break
    except Exception as e:
        print("attempt", attempt, "err", e)
pw.stop()
print("done")