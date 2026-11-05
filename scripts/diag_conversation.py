import sys, time
sys.path.insert(0, "src")
from playwright.sync_api import sync_playwright

url = "https://chatgpt.com/c/6ae8462d-8234-83ee-add5-6d72dabaac15"
pw = sync_playwright().start()
b = pw.chromium.connect_over_cdp("http://127.0.0.1:9224")
ctx = b.contexts[0]
page = ctx.new_page()
page.goto(url, timeout=30000, wait_until="domcontentloaded")
time.sleep(8)
print("FINAL_URL:", page.url)
print("TITLE:", page.title())
content = page.content() or ""
print("AUTH_INDICATOR:", "data-theme-user-id" in content)
print("LOADING:", "Loading" in (page.title() or ""))
print("TEXT_LEN:", len(content))
# check if conversation content visible
import re
print("HAS_TASK_MARKER:", "OPENCODE_TASK" in content)
pw.stop()
print("done")