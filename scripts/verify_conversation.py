import sys
sys.path.insert(0, "src")
from opencode_bridge.managed_edge import CdpEdgeAdapter, ManagedEdgeLauncher

url = "https://chatgpt.com/c/6ae8462d-8234-83ee-add5-6d72dabaac15"
launcher = ManagedEdgeLauncher(profile_dir=".edge-profile-automation", port=9224)
adapter = CdpEdgeAdapter(launcher=launcher, conversation_url=url, headless=False)
print("start:", adapter.start())
print("current_url:", adapter.current_url())
print("auth:", adapter.is_authenticated())
# verify exact
expected = url
actual = adapter.current_url()
print("exact_match:", actual.rstrip("/") == expected.rstrip("/"))
adapter.stop()  # disconnect only; managed edge stays running