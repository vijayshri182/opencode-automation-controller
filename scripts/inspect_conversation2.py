import sys, time
sys.path.insert(0, "src")
from playwright.sync_api import sync_playwright

pw = sync_playwright().start()
b = pw.chromium.connect_over_cdp("http://127.0.0.1:9224")
ctx = b.contexts[0]
page = ctx.pages[0] if ctx.pages else ctx.new_page()
page.goto("https://chatgpt.com/c/6ae8462d-8234-83ee-add5-6d72dabaac15", timeout=30000, wait_until="domcontentloaded")
time.sleep(6)
print("URL:", page.url)
print("TITLE:", page.title())
# Try various selectors
for sel in ["article", "div[data-message-author-role]", "div[data-testid^='conversation-turn']", "main", "div.group"]:
    try:
        print(sel, ":", len(page.query_selector_all(sel)))
    except Exception as e:
        print(sel, "ERROR", e)
# Print text of main
main = page.query_selector("main")
if main:
    print("MAIN_TEXT:", (main.inner_text() or "")[:500].replace("\n"," "))
pw.stop()