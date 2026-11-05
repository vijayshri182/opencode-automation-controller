from typing import Any, Dict, Optional

from .browser_automation import PlaywrightChatGPTController, extract_task_from_text
from .policy import classify_task, TaskPolicy
from .config import DEV_WORKSPACE


class AutonomousOrchestrator:
    def __init__(self, chatgpt_controller: PlaywrightChatGPTController):
        self.chat = chatgpt_controller

    def process_one_cycle(self) -> Dict[str, Any]:
        # Extract task from current conversation
        if self.chat.state.paused:
            return {"ok": False, "reason": "paused"}
        health = self.chat.browser.conversation_health()
        if not (health.get("browser_connected") and health.get("authenticated") and health.get("readable")):
            return {"ok": False, "reason": "conversation unhealthy", "health": health}
        # Project-first navigation
        if self.chat.state.project_url and self.chat.state.conversation_id:
            ok = self.chat.browser.open_project_conversation(self.chat.state.project_url, self.chat.state.conversation_id)
            if not ok:
                return {"ok": False, "reason": "project conversation not found"}
        elif self.chat.state.conversation_url:
            self.chat.browser.navigate(self.chat.state.conversation_url)
        if not self.chat.verify_conversation() and not (self.chat.state.project_url and self.chat.state.conversation_id):
            return {"ok": False, "reason": "conversation mismatch"}
            return {"ok": False, "reason": "conversation mismatch"}
        text = self.chat.browser.get_page_text()
        task = extract_task_from_text(text)
        if not task:
            return {"ok": True, "reason": "no marked task"}
        # submit to controller (duplicate protection inside)
        meta = {"source": "chatgpt", "conversation_url": self.chat.state.conversation_url}
        if self.chat.model:
            meta["model"] = self.chat.model
        res = self.chat.task_controller.submit_task(task_text=task, metadata=meta, workspace=str(DEV_WORKSPACE))
        tid = res["task_id"]
        self.chat.state.current_task_id = tid
        self.chat.state.status = "awaiting_policy"
        self.chat._save_state()
        policy, reason = classify_task(task)
        if policy == TaskPolicy.BLOCKED:
            self.chat.task_controller.reject_task(tid, reason=reason)
            self.chat.state.status = "blocked"
            self.chat._save_state()
            return {"ok": False, "task_id": tid, "policy": policy.value, "reason": reason}
        if policy == TaskPolicy.REQUIRES_APPROVAL:
            self.chat.state.status = "awaiting_approval"
            self.chat._save_state()
            return {"ok": True, "task_id": tid, "policy": policy.value, "reason": reason, "requires_approval": True}
        # AUTO_APPROVE
        ar = self.chat.task_controller.approve_task(tid, approved_by="auto_policy")
        if not ar.get("ok"):
            return {"ok": False, "task_id": tid, "reason": ar.get("reason")}
        self.chat.task_controller.run_task_sync(tid)
        status = self.chat.task_controller.get_status(tid)
        # deliver result
        delivery = self.chat.return_result_to_chatgpt()
        self.chat.state.status = "completed_cycle"
        self.chat._save_state()
        return {
            "ok": True,
            "task_id": tid,
            "policy": policy.value,
            "execution_status": status.get("status"),
            "delivery": delivery,
        }

    def status_summary(self):
        tasks = self.chat.task_controller.list_recent(limit=50)
        summary = {"pending": [], "awaiting_approval": [], "running": [], "completed": [], "failed": [], "blocked": [], "cancelled": []}
        for t in tasks:
            bucket = t["status"] if t["status"] in summary else "completed"
            summary.setdefault(bucket, []).append(t["task_id"])
        return summary

    def run_bounded(self, max_cycles: int = 5, interval_seconds: float = 5.0) -> list:
        import time
        results = []
        for i in range(max_cycles):
            try:
                r = self.process_one_cycle()
            except Exception as e:
                r = {"ok": False, "reason": str(e)}
            results.append(r)
            # Stop conditions
            if r.get("reason") == "paused":
                break
            if r.get("policy") == "blocked":
                break
            if r.get("requires_approval"):
                break
            if r.get("delivery", {}).get("ok"):
                break
            if i < max_cycles - 1:
                time.sleep(interval_seconds)
        return results