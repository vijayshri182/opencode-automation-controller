import sys, time
sys.path.insert(0, "src")
from playwright.sync_api import sync_playwright
from opencode_bridge.browser_automation import extract_task_from_text

pw = sync_playwright().start()
b = pw.chromium.connect_over_cdp("http://127.0.0.1:9224")
ctx = b.contexts[0]
page = ctx.pages[0] if ctx.pages else ctx.new_page()
time.sleep(2)
content = page.content() or ""
print("content len:", len(content))
print("has marker:", "OPENCODE_TASK" in content)
task = extract_task_from_text(content)
print("extracted:", repr(task))
# also try inner text
txt = page.inner_text("body") if page.query_selector("body") else ""
print("inner text len:", len(txt))
task2 = extract_task_from_text(txt)
print("extracted2:", repr(task2))
pw.stop()
print("done")