import sys, time
sys.path.insert(0, "src")
from playwright.sync_api import sync_playwright

pw = sync_playwright().start()
b = pw.chromium.connect_over_cdp("http://127.0.0.1:9224")
ctx = b.contexts[0]
page = ctx.pages[0] if ctx.pages else ctx.new_page()
time.sleep(2)
content = page.content() or ""
print("WP414 in content:", "WP414" in content)
print("URL:", page.url)
print("TITLE:", page.title())
# try to find any text containing WP414
import re
idx = content.find("WP414")
if idx >= 0:
    print("snippet:", content[idx:idx+200].replace("\n"," "))
pw.stop()
print("done")