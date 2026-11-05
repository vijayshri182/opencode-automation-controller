import sys, time
sys.path.insert(0, "src")
from opencode_bridge.managed_edge import CdpEdgeAdapter, ManagedEdgeLauncher

launcher = ManagedEdgeLauncher(profile_dir=".edge-profile-automation", port=9224)
adapter = CdpEdgeAdapter(launcher=launcher, conversation_url="", headless=False)
adapter.start()
time.sleep(5)
ok = adapter.open_project_conversation("https://chatgpt.com/g/g-p-6ae87c1e48b08191a2cd33139c40639f/project", "6ae87c0a-10c8-83ee-a666-c3a5cfea6521")
print("open_project_conversation:", ok)
page = adapter._page
time.sleep(5)
print("URL:", page.url)
print("AUTH:", adapter.is_authenticated())
print("TEXTBOX:", page.query_selector("div[role='textbox']") is not None)
adapter.stop()
print("done")