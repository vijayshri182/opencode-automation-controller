import sys, time
sys.path.insert(0, "src")
from playwright.sync_api import sync_playwright

conv_url = "https://chatgpt.com/c/6ae8462d-8234-83ee-add5-6d72dabaac15"
pw = sync_playwright().start()
b = pw.chromium.connect_over_cdp("http://127.0.0.1:9224")
ctx = b.contexts[0]
page = ctx.pages[0] if ctx.pages else ctx.new_page()
page.goto(conv_url, timeout=30000, wait_until="domcontentloaded")
time.sleep(10)
print("URL:", page.url)
print("TITLE:", page.title())
print("textbox:", page.query_selector("div[role='textbox']") is not None)
print("textarea:", page.query_selector("textarea") is not None)
print("send btn:", page.query_selector("button[aria-label='Send']") is not None)
# try to send
box = page.query_selector("div[role='textbox']")
if box:
    box.click()
    page.keyboard.type("test msg")
    time.sleep(1)
    send = page.query_selector("button[aria-label='Send']")
    print("send after type:", send is not None)
pw.stop()
print("done")