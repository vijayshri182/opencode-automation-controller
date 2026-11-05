import subprocess
from pathlib import Path
from typing import Tuple

from .config import DEV_WORKSPACE, EXPECTED_BRANCH, PROD_WORKSPACE_HINTS, SENSITIVE_KEYWORDS, MAX_TASK_CHARS


def validate_workspace(workspace: str) -> Tuple[bool, str]:
    try:
        p = Path(workspace).resolve()
    except Exception as e:
        return False, f"invalid workspace path: {e}"
    if p != DEV_WORKSPACE:
        return False, f"workspace must be {DEV_WORKSPACE}; got {p}"
    # PROD path hint guard
    low = str(p).lower()
    for hint in PROD_WORKSPACE_HINTS:
        if hint in low and not low.endswith("-dev"):
            return False, "PROD workspace rejected"
    if not p.exists():
        return False, "workspace does not exist"
    return True, "ok"


def validate_branch(workspace: str, expected: str = EXPECTED_BRANCH) -> Tuple[bool, str, str]:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=workspace, capture_output=True, text=True, timeout=10,
        )
        if out.returncode != 0:
            return False, "git branch check failed", out.stderr.strip()
        branch = out.stdout.strip()
        if branch != expected:
            return False, f"branch mismatch: expected {expected}, got {branch}", branch
        return True, "ok", branch
    except Exception as e:
        return False, f"git unavailable: {e}", ""


def validate_task_text(task_text: str) -> Tuple[bool, str]:
    if not isinstance(task_text, str):
        return False, "task must be a string"
    t = task_text.strip()
    if not t:
        return False, "task is empty"
    if len(t) > MAX_TASK_CHARS:
        return False, f"task exceeds {MAX_TASK_CHARS} characters"
    low = t.lower()
    # PROD path guard
    if "fno-ai-paper-trading" in low and "fno-ai-paper-trading-dev" not in low:
        return False, "task references non-DEV (PROD) repository"
    if r"c:\vijay_github\fno-ai-paper-trading" in low.replace(" ", "") and "dev" not in low:
        return False, "task references PROD repository path"
    # sensitive keyword guard
    for kw in SENSITIVE_KEYWORDS:
        if kw in low:
            return False, f"sensitive action blocked: '{kw}'"
    return True, "ok"


def is_sensitive(text: str) -> bool:
    low = (text or "").lower()
    return any(kw in low for kw in SENSITIVE_KEYWORDS)