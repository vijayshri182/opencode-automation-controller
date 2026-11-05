import sys, time
sys.path.insert(0, "src")
from opencode_bridge.managed_edge import CdpEdgeAdapter, ManagedEdgeLauncher

url = "https://chatgpt.com/g/g-p-6ae87c1e48b08191a2cd33139c40639f/c/6ae87c0a-10c8-83ee-a666-c3a5cfea6521"
launcher = ManagedEdgeLauncher(profile_dir=".edge-profile-automation", port=9224)
adapter = CdpEdgeAdapter(launcher=launcher, conversation_url=url, headless=False)
adapter.start()
time.sleep(10)
page = adapter._page
print("URL:", adapter.current_url())
print("AUTH:", adapter.is_authenticated())
print("TITLE:", page.title() if page else "")
print("TEXTBOX:", page.query_selector("div[role='textbox']") is not None if page else False)
txt = page.inner_text("body") if page else ""
print("TEXT_LEN:", len(txt))
print("HAS_MARKER:", "OPENCODE_TASK" in txt)
adapter.stop()
print("done")