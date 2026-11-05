import sys, time
sys.path.insert(0, "src")
from playwright.sync_api import sync_playwright

pw = sync_playwright().start()
b = pw.chromium.connect_over_cdp("http://127.0.0.1:9224")
ctx = b.contexts[0]
print("pages:", len(ctx.pages))
for i, pg in enumerate(ctx.pages):
    print(f"PAGE {i}: {pg.url} | {pg.title()}")
pw.stop()
print("done")