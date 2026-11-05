import sys, time
sys.path.insert(0, "src")
from playwright.sync_api import sync_playwright

project_url = "https://chatgpt.com/g/g-p-6ae87c1e48b08191a2cd33139c40639f/project"
conv_id = "6ae8462d-8234-83ee-add5-6d72dabaac15"

pw = sync_playwright().start()
b = pw.chromium.connect_over_cdp("http://127.0.0.1:9224")
ctx = b.contexts[0]
page = ctx.pages[0] if ctx.pages else ctx.new_page()
page.goto(project_url, timeout=30000, wait_until="domcontentloaded")
time.sleep(10)
links = page.query_selector_all("a[href*='/c/']")
print("links:", len(links))
target = None
for l in links:
    href = l.get_attribute("href") or ""
    if conv_id in href:
        target = l
        print("found target:", href)
        break
if target:
    target.evaluate("el => el.click()")
    print("clicked via js")
    time.sleep(8)
    time.sleep(8)
    print("URL after:", page.url)
    print("conv_id in url:", conv_id in page.url)
    time.sleep(5)
    print("TITLE:", page.title())
    # Check if conversation text appears
    content = page.content() or ""
    print("HAS_MARKER:", "OPENCODE_TASK" in content)
    print("TEXT_LEN:", len(content))
pw.stop()
print("done")