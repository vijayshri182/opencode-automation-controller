import sys, time
sys.path.insert(0, "src")
from playwright.sync_api import sync_playwright

pw = sync_playwright().start()
b = pw.chromium.connect_over_cdp("http://127.0.0.1:9224")
ctx = b.contexts[0]
page = ctx.pages[0] if ctx.pages else ctx.new_page()
page.goto("https://chatgpt.com/c/6ae8462d-8234-83ee-add5-6d72dabaac15", timeout=30000, wait_until="domcontentloaded")
time.sleep(5)
print("URL:", page.url)
# Get all message containers
msgs = page.query_selector_all("div[data-message-author-role]")
print("message count:", len(msgs))
for i, m in enumerate(msgs[-10:]):
    role = m.get_attribute("data-message-author-role")
    text = (m.inner_text() or "")[:200].replace("\n", " ")
    print(f"[{i}] {role}: {text}")
pw.stop()