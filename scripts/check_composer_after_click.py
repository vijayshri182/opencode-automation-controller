import sys, time
sys.path.insert(0, "src")
from playwright.sync_api import sync_playwright

conv_id = "6ae8462d-8234-83ee-add5-6d72dabaac15"
pw = sync_playwright().start()
b = pw.chromium.connect_over_cdp("http://127.0.0.1:9224")
ctx = b.contexts[0]
page = ctx.pages[0] if ctx.pages else ctx.new_page()
page.goto("https://chatgpt.com/g/g-p-6ae87c1e48b08191a2cd33139c40639f/project", timeout=30000, wait_until="domcontentloaded")
time.sleep(8)
# find and click conversation link
links = page.query_selector_all("a")
target = None
for l in links:
    href = l.get_attribute("href") or ""
    if conv_id in href:
        target = l
        break
if target:
    target.evaluate("el => el.click()")
    print("clicked")
    time.sleep(8)
    print("URL:", page.url)
    print("TITLE:", page.title())
    print("textbox:", page.query_selector("div[role='textbox']") is not None)
    print("textarea:", page.query_selector("textarea") is not None)
    print("send btn:", page.query_selector("button[aria-label='Send']") is not None)
pw.stop()
print("done")