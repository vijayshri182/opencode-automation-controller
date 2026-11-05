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
groups = page.query_selector_all("div.group")
print("groups:", len(groups))
for i,g in enumerate(groups[-6:]):
    txt = (g.inner_text() or "")[:300]
    print(f"--- group {i} ---")
    print(txt.encode("ascii","backslashreplace").decode("ascii"))
pw.stop()