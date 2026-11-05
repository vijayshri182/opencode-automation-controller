import sys, time
sys.path.insert(0, "src")
from opencode_bridge.managed_edge import CdpEdgeAdapter, ManagedEdgeLauncher

project_url = "https://chatgpt.com/g/g-p-6ae87c1e48b08191a2cd33139c40639f/project"
conv_id = "6ae8462d-8234-83ee-add5-6d72dabaac15"
launcher = ManagedEdgeLauncher(profile_dir=".edge-profile-automation", port=9224)
adapter = CdpEdgeAdapter(launcher=launcher, conversation_url="", headless=False)
print("start:", adapter.start())
ok = adapter.open_project_conversation(project_url, conv_id)
print("open_project_conversation:", ok)
print("URL:", adapter.current_url())
print("AUTH:", adapter.is_authenticated())
page = adapter._page
if page:
    print("TITLE:", page.title())
    print("TEXT_LEN:", len(page.content() or ""))
    print("TEXTBOX:", page.query_selector("div[role='textbox']") is not None)
adapter.stop()
print("done")