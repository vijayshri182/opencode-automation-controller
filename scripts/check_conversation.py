import sys, time
sys.path.insert(0, "src")
from playwright.sync_api import sync_playwright

pw = sync_playwright().start()
b = pw.chromium.connect_over_cdp("http://127.0.0.1:9224")
ctx = b.contexts[0]
print("pages:", len(ctx.pages))
for i, pg in enumerate(ctx.pages):
    print(f"PAGE {i}: {pg.url}")
    print("  TITLE:", pg.title())
    time.sleep(2)
    print("  TEXT_LEN:", len(pg.content() or ""))
    if "chatgpt.com/c/" in pg.url:
        txt = pg.content() or ""
        print("  HAS_MARKER:", "OPENCODE_TASK" in txt)
pw.stop()
print("done")