import sys, time
sys.path.insert(0, "src")
from opencode_bridge.managed_edge import CdpEdgeAdapter, ManagedEdgeLauncher
from opencode_bridge.browser_automation import extract_task_from_text

launcher = ManagedEdgeLauncher(profile_dir=".edge-profile-automation", port=9224)
adapter = CdpEdgeAdapter(launcher=launcher, conversation_url="", headless=False)
adapter.start()
time.sleep(2)
# navigate to conversation
page = adapter._context.pages[0] if adapter._context.pages else adapter._context.new_page()
adapter._page = page
try:
    page.goto("https://chatgpt.com/c/6ae8462d-8234-83ee-add5-6d72dabaac15", timeout=60000, wait_until="domcontentloaded")
    print("goto ok")
except Exception as e:
    print("goto err", e)
time.sleep(10)
text = adapter.get_page_text()
print("TITLE:", page.title())
print("URL:", page.url)
print("AUTH:", adapter.is_authenticated())
print("TEXT_LEN:", len(text))
print("HAS_MARKER:", "OPENCODE_TASK" in text)
task = extract_task_from_text(text)
print("TASK:", repr(task[:200] if task else None))
adapter.stop()