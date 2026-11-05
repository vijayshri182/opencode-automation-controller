import sys, time
sys.path.insert(0, "src")
from playwright.sync_api import sync_playwright

pw = sync_playwright().start()
b = pw.chromium.connect_over_cdp("http://127.0.0.1:9224")
ctx = b.contexts[0]
page = ctx.pages[0] if ctx.pages else ctx.new_page()
page.goto("https://chatgpt.com/g/g-p-6ae87c1e48b08191a2cd33139c40639f/project", timeout=30000, wait_until="domcontentloaded")
time.sleep(6)
btn = page.query_selector("button:has-text('New chat')")
if btn:
    btn.evaluate("el => el.click()")
    print("clicked")
time.sleep(8)
print("URL:", page.url)
print("TITLE:", page.title())
for sel in ["textarea", "div[role='textbox']", "div[contenteditable='true']", "input"]:
    print(sel, ":", len(page.query_selector_all(sel)))
main = page.query_selector("main")
if main:
    print("MAIN:", (main.inner_text() or "")[:500].replace("\n", " "))
# buttons
btns = page.query_selector_all("button")
print("buttons:", len(btns))
for btn in btns[:15]:
    print(" BTN", repr(btn.get_attribute("aria-label")), (btn.inner_text() or "")[:20])
pw.stop()
print("done")