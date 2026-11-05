import sys, time
sys.path.insert(0, "src")
from playwright.sync_api import sync_playwright

pw = sync_playwright().start()
b = pw.chromium.connect_over_cdp("http://127.0.0.1:9224")
ctx = b.contexts[0]
page = ctx.pages[0] if ctx.pages else ctx.new_page()
page.goto("https://chatgpt.com/g/g-p-6ae87c1e48b08191a2cd33139c40639f/project", timeout=30000, wait_until="domcontentloaded")
time.sleep(10)
# find project-specific new chat button
btn = None
try:
    btn = page.query_selector("button[aria-label='New chat in Palmistry Project']")
except Exception as e:
    print("query err", e)
print("button found:", btn is not None)
if btn:
    try:
        btn.evaluate("el => el.click()")
        print("clicked")
        time.sleep(8)
    except Exception as e:
        print("click err", e)
print("URL:", page.url)
print("TITLE:", page.title())
try:
    print("textbox:", page.query_selector("div[role='textbox']") is not None)
except Exception as e:
    print("textbox err", e)
pw.stop()
print("done")