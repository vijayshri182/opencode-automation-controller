import sys, time
sys.path.insert(0, "src")
from playwright.sync_api import sync_playwright

pw = sync_playwright().start()
b = pw.chromium.connect_over_cdp("http://127.0.0.1:9224")
ctx = b.contexts[0]
page = ctx.pages[0] if ctx.pages else ctx.new_page()
time.sleep(2)
# find any element with role textbox or contenteditable
for sel in ["[role='textbox']", "[contenteditable='true']", "textarea", "div.ProseMirror", "div[contenteditable]"]:
    try:
        els = page.query_selector_all(sel)
        print(sel, ":", len(els))
    except Exception as e:
        print(sel, "ERR", e)
# print main element text
main = page.query_selector("main")
if main:
    print("MAIN TEXT LEN:", len(main.inner_text() or ""))
    print("MAIN SNIPPET:", (main.inner_text() or "")[:300].replace("\n"," "))
# buttons with send
for btn in page.query_selector_all("button"):
    try:
        al = btn.get_attribute("aria-label") or ""
        if "send" in al.lower() or "send" in (btn.inner_text() or "").lower():
            print("SEND BTN:", repr(al), (btn.inner_text() or "")[:20])
    except Exception:
        pass
pw.stop()
print("done")