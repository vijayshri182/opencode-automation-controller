import sys, time
sys.path.insert(0, "src")
from playwright.sync_api import sync_playwright

pw = sync_playwright().start()
b = pw.chromium.connect_over_cdp("http://127.0.0.1:9224")
ctx = b.contexts[0]
page = ctx.pages[0] if ctx.pages else ctx.new_page()
page.goto("https://chatgpt.com/g/g-p-6ae87c1e48b08191a2cd33139c40639f/project", timeout=30000, wait_until="domcontentloaded")
time.sleep(6)
# Click New chat
btn = page.query_selector("button:has-text('New chat')")
if btn:
    btn.evaluate("el => el.click()")
    print("clicked new chat")
    time.sleep(5)
# Type a harmless binding message
box = page.query_selector("div[role='textbox']")
if box:
    box.click()
    page.keyboard.type("OpenCode automation binding test. No task yet.")
    time.sleep(1)
    send = page.query_selector("button[aria-label='Send']")
    if send:
        send.click()
        print("sent binding message")
    else:
        print("no send button")
# Wait for URL to become a conversation
deadline = time.time() + 30
while time.time() < deadline:
    url = page.url
    if "/c/" in url:
        break
    time.sleep(1)
print("FINAL_URL:", page.url)
print("TITLE:", page.title())
pw.stop()
print("done")