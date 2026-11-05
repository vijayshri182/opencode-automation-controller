import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from opencode_bridge.browser_automation import PlaywrightEdgeAdapter, PlaywrightChatGPTController
from opencode_bridge.config import DEV_WORKSPACE
from opencode_bridge.db import BridgeDB
from opencode_bridge.controller import TaskController
from opencode_bridge.opencode_adapter import OpenCodeAdapter


def main():
    import sys as _sys
    print("Python executable:", _sys.executable)
    try:
        import playwright  # noqa: F401
        print("Playwright: available")
    except Exception as e:
        print("Playwright: MISSING")
        print("Install with: python -m pip install -r requirements.txt")
        print("Or use project venv: .venv\\Scripts\\python.exe -m opencode_bridge.operator_cli ...")
        return 1
    parser = argparse.ArgumentParser(description="Supervised ChatGPT/OpenCode cycle")
    parser.add_argument("--conversation-url", default="https://chatgpt.com/")
    parser.add_argument("--profile-dir", required=True)
    parser.add_argument("--db", default=None)
    parser.add_argument("--model-provider", default=None)
    parser.add_argument("--model-id", default=None)
    parser.add_argument("--opencode-url", default=None)
    parser.add_argument("--keep-open", action="store_true")
    parser.add_argument("--bounded", action="store_true")
    parser.add_argument("--max-cycles", type=int, default=5)
    parser.add_argument("--interval", type=float, default=5.0)
    parser.add_argument("--cdp", action="store_true")
    parser.add_argument("--cdp-port", type=int, default=9224)
    parser.add_argument("--attach-only", action="store_true", help="Attach to an already-running browser; never launch one.")
    parser.add_argument("--user-data-dir", default=None, help="Existing browser user-data dir (enables DevToolsActivePort attach).")
    parser.add_argument("--managed-profile", default=".edge-profile-automation")
    args = parser.parse_args()

    import os as _os
    if args.opencode_url:
        _os.environ["OPENCODE_BASE_URL"] = args.opencode_url

    from opencode_bridge.config import opencode_base_url
    db_path = Path(args.db) if args.db else (Path(args.profile_dir) / "bridge.db")
    db = BridgeDB(db_path)
    adapter = OpenCodeAdapter()
    try:
        print("OpenCode health:", adapter.health())
    except Exception as e:
        print("OpenCode unavailable:", e)
        return 1
    ctrl = TaskController(db=db, adapter=adapter, auto_worker=False)

    model = None
    if args.model_provider and args.model_id:
        model = {"providerID": args.model_provider, "modelID": args.model_id}

    if args.cdp:
        from opencode_bridge.managed_edge import ManagedEdgeLauncher, CdpEdgeAdapter
        launcher = ManagedEdgeLauncher(profile_dir=args.managed_profile, port=args.cdp_port)
        browser = CdpEdgeAdapter(
            launcher=launcher,
            conversation_url=args.conversation_url,
            headless=False,
            attach_only=bool(args.attach_only),
            user_data_dir=args.user_data_dir,
        )
    else:
        browser = PlaywrightEdgeAdapter(profile_dir=args.profile_dir, conversation_url=args.conversation_url, headless=False)
    orch = PlaywrightChatGPTController(browser=browser, task_controller=ctrl, state_path=Path(args.profile_dir) / "state.json", model=model)
    if not orch.start():
        print("Browser start failed")
        return 1
    orch.set_conversation_url(args.conversation_url)
    if not orch.verify_conversation():
        print("Conversation mismatch:", orch.state.last_error)
        orch.stop()
        return 1

    if args.keep_open:
        print("Browser is open at:", browser.current_url())
        print("Authentication required:", not browser.is_authenticated())
        print("Browser is open. Keep this process running; terminate it to close the browser.")
        import time
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
        orch.stop()
        return 0

    if args.bounded:
        from opencode_bridge.autonomous import AutonomousOrchestrator
        auto = AutonomousOrchestrator(orch)
        results = auto.run_bounded(max_cycles=args.max_cycles, interval_seconds=args.interval)
        print("Bounded results:", results)
        orch.stop()
        return 0

    r = orch.run_one_cycle()
    print("Cycle result:", r)
    if not r.get("ok"):
        orch.stop()
        return 1

    print("\nExtracted task preview:\n", r.get("task_preview"))
    print("\nTarget repository:", DEV_WORKSPACE)
    approval = input("Approve task? (yes/no): ").strip().lower()
    if approval != "yes":
        orch.state.status = "rejected"
        orch._save_state()
        orch.stop()
        print("Task rejected; stopped.")
        return 0

    ar = orch.approve_current_task(approved_by="operator")
    print("Execution:", ar)
    if not ar.get("ok"):
        orch.stop()
        return 1

    status = ctrl.get_status(orch.state.current_task_id)
    print("Task status:", status.get("status"))
    rr = orch.return_result_to_chatgpt()
    print("Result submission:", rr)
    orch.stop()
    print("Stopped; waiting for next instruction.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())