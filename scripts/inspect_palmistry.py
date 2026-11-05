import sys, time
sys.path.insert(0, "src")
from playwright.sync_api import sync_playwright

url = "https://chatgpt.com/g/g-p-6ae87c1e48b08191a2cd33139c40639f/project"
pw = sync_playwright().start()
b = pw.chromium.connect_over_cdp("http://127.0.0.1:9224")
ctx = b.contexts[0]
page = ctx.pages[0] if ctx.pages else ctx.new_page()
page.goto(url, timeout=30000, wait_until="domcontentloaded")
time.sleep(8)
print("URL:", page.url)
print("TITLE:", page.title())
# auth indicators
content = page.content() or ""
print("HAS_LOGIN:", "Log in" in content or "Sign up" in content)
print("HAS_NEW_CHAT:", "New chat" in content)
# list links to conversations
links = page.query_selector_all("a[href*='/c/']")
print("conversation links:", len(links))
for l in links[:10]:
    print(" LINK", l.get_attribute("href"))
pw.stop()
print("done")