import sys, time
sys.path.insert(0, "src")
from playwright.sync_api import sync_playwright

pw = sync_playwright().start()
b = pw.chromium.connect_over_cdp("http://127.0.0.1:9224")
ctx = b.contexts[0]
page = ctx.pages[0] if ctx.pages else ctx.new_page()
page.goto("https://chatgpt.com/", timeout=30000)
time.sleep(4)
print("URL:", page.url)
print("TITLE:", page.title())
print("TEXTAREA:", page.query_selector("textarea") is not None)
login = page.query_selector("button:has-text('Log in')")
print("LOGIN_BUTTON:", login is not None)
pw.stop()