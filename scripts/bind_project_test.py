import sys, time
sys.path.insert(0, "src")
from playwright.sync_api import sync_playwright

project_url = "https://chatgpt.com/g/g-p-6ae87c1e48b08191a2cd33139c40639f/project"
conv_id = "6ae87c0a-10c8-83ee-a666-c3a5cfea6521"

pw = sync_playwright().start()
b = pw.chromium.connect_over_cdp("http://127.0.0.1:9224")
ctx = b.contexts[0]
page = ctx.pages[0] if ctx.pages else ctx.new_page()
page.goto(project_url, timeout=30000, wait_until="domcontentloaded")
time.sleep(10)
# find link containing conv_id
links = page.query_selector_all("a")
target = None
for l in links:
    href = l.get_attribute("href") or ""
    if conv_id in href:
        target = l
        break
print("target found:", target is not None)
if target:
    target.evaluate("el => el.click()")
    print("clicked")
    time.sleep(8)
    print("URL:", page.url)
    print("TITLE:", page.title())
    print("ID in URL:", conv_id in page.url)
    print("AUTH:", "Log in" not in (page.content() or ""))
    print("TEXTBOX:", page.query_selector("div[role='textbox']") is not None)
    print("TEXT_LEN:", len(page.content() or ""))
pw.stop()
print("done")