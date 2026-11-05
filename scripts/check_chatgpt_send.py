import sys, time
sys.path.insert(0, "src")
from playwright.sync_api import sync_playwright

pw = sync_playwright().start()
b = pw.chromium.connect_over_cdp("http://127.0.0.1:9224")
ctx = b.contexts[0]
page = ctx.pages[0] if ctx.pages else ctx.new_page()
# find the conversation page if possible
for pg in ctx.pages:
    if "chatgpt.com/c/" in pg.url or "chatgpt.com/g/" in pg.url:
        page = pg
        break
page.goto("https://chatgpt.com/g/g-p-6ae87c1e48b08191a2cd33139c40639f/project", timeout=30000, wait_until="domcontentloaded")
time.sleep(8)
# Use the first New chat? Instead, just send a test message in current composer
box = page.query_selector("div[role='textbox']")
if box:
    box.click()
    page.keyboard.type("WP414 connection test. Reply with: WP414_OK")
    time.sleep(1)
    send = page.query_selector("button[aria-label='Send']")
    if send:
        send.click()
        print("sent")
    else:
        print("no send button")
# wait for response
time.sleep(15)
# extract last assistant text via page content? Use query_selector
nodes = page.query_selector_all("div[data-message-author-role='assistant']")
print("assistant nodes:", len(nodes))
if nodes:
    print("LAST:", (nodes[-1].inner_text() or "")[:200])
pw.stop()
print("done")