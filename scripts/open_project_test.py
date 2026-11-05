import sys, time
sys.path.insert(0, "src")
from playwright.sync_api import sync_playwright

target = "6ae87c0a-10c8-83ee-a666-c3a5cfea6521"
pw = sync_playwright().start()
b = pw.chromium.connect_over_cdp("http://127.0.0.1:9224")
ctx = b.contexts[0]
page = ctx.pages[0] if ctx.pages else ctx.new_page()
page.goto("https://chatgpt.com/g/g-p-6ae87c1e48b08191a2cd33139c40639f/project", timeout=30000, wait_until="domcontentloaded")
time.sleep(8)
links = page.query_selector_all("a")
target_link = None
for l in links:
    href = l.get_attribute("href") or ""
    if target in href:
        target_link = l
        break
print("target found:", target_link is not None)
if target_link:
    target_link.evaluate("el => el.click()")
    print("clicked")
    time.sleep(8)
    print("URL:", page.url)
    print("TITLE:", page.title())
    print("ID in URL:", target in page.url)
    content = page.content() or ""
    print("AUTH:", "Log in" not in content and "Sign up" not in content)
    print("TEXTBOX:", page.query_selector("div[role='textbox']") is not None)
    print("TEXT_LEN:", len(content))
    print("HAS_MARKER:", "OPENCODE_TASK" in content)
pw.stop()
print("done")