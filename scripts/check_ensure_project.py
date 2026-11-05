import sys, time
sys.path.insert(0, "src")
from opencode_bridge.browser_automation import PlaywrightChatGPTController
from opencode_bridge.config import DEV_WORKSPACE
from opencode_bridge.db import BridgeDB
from opencode_bridge.controller import TaskController
from opencode_bridge.opencode_adapter import OpenCodeAdapter
from opencode_bridge.managed_edge import CdpEdgeAdapter, ManagedEdgeLauncher
from pathlib import Path

launcher = ManagedEdgeLauncher(profile_dir=".edge-profile-automation", port=9224)
browser = CdpEdgeAdapter(launcher=launcher, conversation_url="https://chatgpt.com/g/g-p-6ae87c1e48b08191a2cd33139c40639f/project", headless=False)
db = BridgeDB(Path(".edge-profile-automation/bridge.db"))
ctrl = TaskController(db=db, adapter=OpenCodeAdapter(), auto_worker=False)
orch = PlaywrightChatGPTController(browser=browser, task_controller=ctrl, state_path=Path(".edge-profile-automation/state.json"))
orch.start()
print("before:", orch.state.conversation_url, orch.state.conversation_id)
ok = orch.ensure_project_conversation("https://chatgpt.com/g/g-p-6ae87c1e48b08191a2cd33139c40639f/project", "6ae87c0a-10c8-83ee-a666-c3a5cfea6521")
print("ensure_project_conversation:", ok)
print("after url:", orch.state.conversation_url)
print("after id:", orch.state.conversation_id)
print("auth:", browser.is_authenticated())
page = browser._page
if page:
    print("title:", page.title())
    print("textbox:", page.query_selector("div[role='textbox']") is not None)
orch.stop()
print("done")