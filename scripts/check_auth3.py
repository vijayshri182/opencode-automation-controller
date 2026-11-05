import sys
sys.path.insert(0, "src")
from opencode_bridge.managed_edge import CdpEdgeAdapter, ManagedEdgeLauncher

launcher = ManagedEdgeLauncher(profile_dir=".edge-profile-automation", port=9224)
adapter = CdpEdgeAdapter(launcher=launcher, conversation_url="https://chatgpt.com/c/6ae8462d-8234-83ee-add5-6d72dabaac15", headless=False)
adapter.start()
print("URL:", adapter.current_url())
print("AUTH:", adapter.is_authenticated())
print("EXACT:", adapter.current_url().rstrip("/") == "https://chatgpt.com/c/6ae8462d-8234-83ee-add5-6d72dabaac15".rstrip("/"))
adapter.stop()  # disconnect only