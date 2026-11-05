import sys, time
sys.path.insert(0, "src")
from opencode_bridge.managed_edge import CdpEdgeAdapter, ManagedEdgeLauncher

launcher = ManagedEdgeLauncher(profile_dir=".edge-profile-automation", port=9224)
adapter = CdpEdgeAdapter(launcher=launcher, conversation_url="https://chatgpt.com/g/g-p-6ae87c1e48b08191a2cd33139c40639f/project", headless=False)
adapter.start()
time.sleep(4)
# debug: find button
page = adapter._page
btn = page.query_selector("button[aria-label='New chat in Palmistry Project']")
print("button found:", btn is not None)
if btn:
    print("button text:", btn.inner_text())
url = adapter.create_project_chat("Palmistry Project")
print("NEW_URL:", url)
# verify
if url:
    adapter.navigate(url)
    time.sleep(6)
    print("VERIFY_URL:", adapter.current_url())
    print("AUTH:", adapter.is_authenticated())
adapter.stop()  # disconnect only; managed edge stays running