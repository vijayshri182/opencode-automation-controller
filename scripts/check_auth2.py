import sys
sys.path.insert(0, "src")
from opencode_bridge.managed_edge import CdpEdgeAdapter, ManagedEdgeLauncher

launcher = ManagedEdgeLauncher(profile_dir=".edge-profile-automation", port=9224)
adapter = CdpEdgeAdapter(launcher=launcher, conversation_url="https://chatgpt.com/", headless=False)
adapter.start()
print("URL:", adapter.current_url())
print("AUTH:", adapter.is_authenticated())
adapter.stop()  # disconnect only; managed edge stays running