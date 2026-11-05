import sys, time
sys.path.insert(0, "src")
from opencode_bridge.opencode_adapter import OpenCodeAdapter
from opencode_bridge.managed_edge import CdpEdgeAdapter, ManagedEdgeLauncher

def log(msg):
    print(msg, flush=True)

# Step 1: OpenCode inspects repo
oc = OpenCodeAdapter(base_url="http://127.0.0.1:4097", timeout=30)
log("OpenCode health: " + str(oc.health().get("healthy")))
s = oc.create_session(title="wp415-context")
sid = s["id"]
log("session: " + sid)
prompt = ("Inspect the repository at C:\\Vijay_GitHub\\opencode-automation-controller. "
          "Summarize its purpose, technology stack, main components and current status in under 200 words. "
          "Do not modify files.")
oc.send_prompt_async(sid, prompt, model={"providerID": "opencode-go", "modelID": "beam-free"})
deadline = time.time() + 120
final = ""
while time.time() < deadline:
    msgs = oc.get_messages(sid, limit=50)
    final = oc.extract_final_assistant(msgs)
    if final:
        break
    time.sleep(3)
log("OPENCODE_CONTEXT_LEN: " + str(len(final)))
log("OPENCODE_CONTEXT: " + final[:500])

# Step 2: Send to ChatGPT
launcher = ManagedEdgeLauncher(profile_dir=".edge-profile-automation", port=9224)
adapter = CdpEdgeAdapter(launcher=launcher, conversation_url="https://chatgpt.com/g/g-p-6ae87c1e48b08191a2cd33139c40639f/project", headless=False)
adapter.start()
log("adapter started")
time.sleep(4)
adapter._page.goto("https://chatgpt.com/g/g-p-6ae87c1e48b08191a2cd33139c40639f/project", timeout=30000, wait_until="domcontentloaded")
time.sleep(8)

msg = (
    "Project context from OpenCode:\n\n" + final + "\n\n"
    "Please provide a comprehensive architecture and phased development plan for this project. "
    "Include purpose, existing state, target architecture, components, data flows, security constraints, "
    "development phases, acceptance criteria, testing strategy, and the first execution-ready OpenCode task."
)
ok = adapter.submit_message(msg)
log("submitted to ChatGPT: " + str(ok))
# wait for response
for i in range(24):
    time.sleep(5)
    txt = adapter.extract_last_assistant_text()
    if txt and len(txt) > 50:
        log("RESPONSE_LEN: " + str(len(txt)))
        log("RESPONSE_SNIPPET: " + txt[:500])
        break
    log("waiting... " + str(i))
adapter.stop()
log("done")