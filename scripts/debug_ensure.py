import sys, time
sys.path.insert(0, "src")
from opencode_bridge.managed_edge import CdpEdgeAdapter, ManagedEdgeLauncher

launcher = ManagedEdgeLauncher(profile_dir=".edge-profile-automation", port=9224)
adapter = CdpEdgeAdapter(launcher=launcher, conversation_url="", headless=False)
adapter.start()
time.sleep(2)
ok = adapter.open_project_conversation("https://chatgpt.com/g/g-p-6ae87c1e48b08191a2cd33139c40639f/project", "6ae87c0a-10c8-83ee-a666-c3a5cfea6521")
print("open_project_conversation:", ok)
page = adapter._page
time.sleep(8)
url = adapter.current_url()
content = ""
try:
    content = page.content() or ""
except Exception as e:
    print("content err", e)
print("URL:", url)
print("ID in URL:", "6ae87c0a-10c8-83ee-a666-c3a5cfea6521" in url)
print("ID in content:", "6ae87c0a-10c8-83ee-a666-c3a5cfea6521" in content)
print("TITLE:", page.title() if page else "")
print("AUTH:", adapter.is_authenticated())
adapter.stop()
print("done")