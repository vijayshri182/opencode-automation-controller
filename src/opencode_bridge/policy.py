import re
from enum import Enum
from typing import Tuple

class TaskPolicy(str, Enum):
    AUTO_APPROVE = "auto_approve"
    REQUIRES_APPROVAL = "requires_approval"
    BLOCKED = "blocked"


AUTO_KEYWORDS = (
    "inspect", "read", "analyse", "analyze", "report", "diagnose", "test", "documentation", "docs",
)
BLOCKED_KEYWORDS = (
    "password", "secret", "token", "credential", "live trade", "live trading", "deploy", "production",
    "commit", "push", "delete", "rm -rf", "format disk", "bypass auth", "disable auth",
)
REQUIRES_KEYWORDS = (
    "modify", "change", "edit", "write", "install", "upgrade", "terminate", "restart", "submit", "send",
    "deploy", "release", "migrate",
)


def classify_task(task_text: str) -> Tuple[TaskPolicy, str]:
    low = (task_text or "").lower()
    for kw in BLOCKED_KEYWORDS:
        if kw in low:
            return TaskPolicy.BLOCKED, f"blocked keyword: {kw}"
    # If task mentions source modification or dependency/process actions -> requires approval
    for kw in REQUIRES_KEYWORDS:
        if kw in low:
            # But read-only inspection phrases can still be auto if only inspect/analyse
            if not any(ak in low for ak in ("inspect", "analyse", "analyze", "report", "diagnose")):
                return TaskPolicy.REQUIRES_APPROVAL, f"requires approval keyword: {kw}"
    # Auto-approve only if clearly read-only/harmless
    if any(ak in low for ak in AUTO_KEYWORDS) and not any(rk in low for rk in ("modify", "change", "write", "install")):
        return TaskPolicy.AUTO_APPROVE, "read-only/diagnostic task"
    return TaskPolicy.REQUIRES_APPROVAL, "uncertain classification (default approval)"