import sys, time
sys.path.insert(0, "src")
from playwright.sync_api import sync_playwright

pw = sync_playwright().start()
b = pw.chromium.connect_over_cdp("http://127.0.0.1:9224")
ctx = b.contexts[0]
page = ctx.pages[0] if ctx.pages else ctx.new_page()
# assume already on project page
time.sleep(2)
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
        print("no send")
# wait
for i in range(10):
    time.sleep(3)
    nodes = page.query_selector_all("div[data-message-author-role='assistant']")
    print(i, "assistant nodes:", len(nodes))
    if nodes:
        print("LAST:", (nodes[-1].inner_text() or "")[:120])
        break
pw.stop()
print("done")