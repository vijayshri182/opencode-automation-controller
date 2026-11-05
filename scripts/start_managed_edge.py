import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from opencode_bridge.managed_edge import ManagedEdgeLauncher

launcher = ManagedEdgeLauncher(profile_dir=".edge-profile-automation", port=9222)
launcher.start()
print("CDP_READY", flush=True)
while True:
    time.sleep(1)