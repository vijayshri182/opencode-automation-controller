import sys, time
sys.path.insert(0, "src")
from playwright.sync_api import sync_playwright

target = "6ae8462d-8234-83ee-add5-6d72dabaac15"
pw = sync_playwright().start()
b = pw.chromium.connect_over_cdp("http://127.0.0.1:9224")
ctx = b.contexts[0]
page = ctx.pages[0] if ctx.pages else ctx.new_page()
page.goto("https://chatgpt.com/g/g-p-6ae87c1e48b08191a2cd33139c40639f/project", timeout=30000, wait_until="domcontentloaded")
time.sleep(5)
print("URL1:", page.url)
print("TITLE1:", page.title())
time.sleep(10)
print("URL2:", page.url)
print("TITLE2:", page.title())
try:
    links = page.query_selector_all("a")
    print("links:", len(links))
except Exception as e:
    print("link err", e)
found = False
for l in links:
    href = l.get_attribute("href") or ""
    if target in href:
        found = True
        print("FOUND in project:", href, (l.inner_text() or "")[:40])
        break
if not found:
    print("NOT FOUND in project conversation list")
pw.stop()
print("done")