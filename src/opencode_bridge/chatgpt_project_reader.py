"""WP-431B: ChatGPT project registry, conversation observation and read-only reader.

Reuses the existing PlaywrightChatGPTAdapter (WP-424) and BridgeDB. No new
browser automation. Polling is disabled by default.

This module is read-only: it never sends messages, creates conversations,
submits tasks or executes OpenCode work.
"""

import contextlib
import hashlib
import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from .chatgpt_interface import (
    PALMISTRY_PROJECT_URL,
    PALMISTRY_PROJECT_ID,
    ChatGPTInterface,
    build_inbound_message,
    derive_message_id,
)


# --- validation ---------------------------------------------------------

def validate_project_key(key: str) -> bool:
    if not key or not isinstance(key, str):
        return False
    if len(key) > 64:
        return False
    return all(c.isalnum() or c in "-_." for c in key)


def validate_project_url(url: str) -> bool:
    if not url or not isinstance(url, str):
        return False
    if len(url) > 512:
        return False
    if not url.startswith("https://chatgpt.com/g/g-p-"):
        return False
    if "/project" not in url:
        return False
    return True


def derive_project_id(url: str) -> str:
    import re
    m = re.search(r"/g/(g-p-[0-9a-z]+)/", (url or "") + "/")
    return m.group(1) if m else ""


# --- project registry ---------------------------------------------------

class ChatGPTProjectRegistry:
    """Manages configured ChatGPT Projects. Backed by BridgeDB."""

    def __init__(self, db):
        self.db = db
        self._ensure_tables()
        self._register_default()

    def _ensure_tables(self):
        with self.db._lock:
            with contextlib.closing(self.db._connect()) as conn:
                conn.executescript("""
                CREATE TABLE IF NOT EXISTS chatgpt_projects (
                    project_key TEXT PRIMARY KEY,
                    display_name TEXT NOT NULL,
                    project_url TEXT NOT NULL,
                    project_id TEXT NOT NULL,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    selection_policy TEXT NOT NULL DEFAULT 'latest_eligible',
                    read_only INTEGER NOT NULL DEFAULT 1,
                    polling_interval_seconds INTEGER NOT NULL DEFAULT 0,
                    excluded_titles_json TEXT NOT NULL DEFAULT '[]',
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS chatgpt_project_state (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    active_project_key TEXT,
                    polling_enabled INTEGER NOT NULL DEFAULT 0,
                    last_read_at REAL,
                    last_error TEXT,
                    updated_at REAL NOT NULL
                );
                INSERT OR IGNORE INTO chatgpt_project_state (id, active_project_key, polling_enabled, updated_at)
                VALUES (1, NULL, 0, 0);
                CREATE TABLE IF NOT EXISTS chatgpt_pinned_conversations (
                    project_key TEXT NOT NULL,
                    conversation_id TEXT NOT NULL,
                    conversation_title TEXT,
                    pinned_at REAL NOT NULL,
                    pinned_by TEXT,
                    PRIMARY KEY (project_key, conversation_id),
                    FOREIGN KEY (project_key) REFERENCES chatgpt_projects(project_key)
                );
                CREATE TABLE IF NOT EXISTS chatgpt_observer_state (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    status TEXT NOT NULL DEFAULT 'STOPPED',
                    active_project_key TEXT,
                    pinned_conversation_id TEXT,
                    last_poll_at REAL,
                    last_error TEXT,
                    poll_count INTEGER NOT NULL DEFAULT 0,
                    updated_at REAL NOT NULL
                );
                INSERT OR IGNORE INTO chatgpt_observer_state (id, status, updated_at) VALUES (1, 'STOPPED', 0);
                CREATE TABLE IF NOT EXISTS chatgpt_observations (
                    observation_id TEXT PRIMARY KEY,
                    project_key TEXT NOT NULL,
                    conversation_id TEXT NOT NULL,
                    conversation_title TEXT,
                    message_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    visible_timestamp TEXT,
                    observed_at REAL NOT NULL,
                    first_seen_at REAL NOT NULL,
                    last_seen_at REAL NOT NULL,
                    is_duplicate INTEGER NOT NULL DEFAULT 0,
                    edit_of TEXT,
                    acknowledged INTEGER NOT NULL DEFAULT 0,
                    acknowledged_at REAL,
                    acknowledged_by TEXT,
                    FOREIGN KEY (project_key) REFERENCES chatgpt_projects(project_key)
                );
                CREATE INDEX IF NOT EXISTS idx_obs_project ON chatgpt_observations(project_key);
                CREATE INDEX IF NOT EXISTS idx_obs_conv ON chatgpt_observations(conversation_id);
                CREATE UNIQUE INDEX IF NOT EXISTS idx_obs_unique ON chatgpt_observations(project_key, conversation_id, message_id, content_hash);
                """)
                conn.commit()

    def _register_default(self):
        try:
            if not self.get_project("palmistry"):
                self.register_project(
                    project_key="palmistry",
                    display_name="Palmistry Project",
                    project_url=PALMISTRY_PROJECT_URL,
                    enabled=True,
                    selection_policy="latest_eligible",
                    read_only=True,
                    polling_interval_seconds=0,
                    excluded_titles=["OpenCode Automation Testing"],
                )
            if not self.get_active_project_key():
                self.set_active_project("palmistry")
        except Exception:
            pass

    def register_project(self, project_key, display_name, project_url, enabled=True,
                         selection_policy="latest_eligible", read_only=True,
                         polling_interval_seconds=0, excluded_titles=None):
        if not validate_project_key(project_key):
            raise ValueError("invalid project_key")
        if not display_name or not isinstance(display_name, str):
            raise ValueError("display_name required")
        if not validate_project_url(project_url):
            raise ValueError("invalid project_url")
        project_id = derive_project_id(project_url)
        if not project_id:
            raise ValueError("could not derive project_id from URL")
        excluded = excluded_titles if excluded_titles is not None else ["OpenCode Automation Testing"]
        now = time.time()
        with self.db._lock:
            with contextlib.closing(self.db._connect()) as conn:
                conn.execute(
                    """INSERT INTO chatgpt_projects
                       (project_key, display_name, project_url, project_id, enabled,
                        selection_policy, read_only, polling_interval_seconds,
                        excluded_titles_json, created_at, updated_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?)
                       ON CONFLICT(project_key) DO UPDATE SET
                        display_name=excluded.display_name,
                        project_url=excluded.project_url,
                        project_id=excluded.project_id,
                        enabled=excluded.enabled,
                        selection_policy=excluded.selection_policy,
                        read_only=excluded.read_only,
                        polling_interval_seconds=excluded.polling_interval_seconds,
                        excluded_titles_json=excluded.excluded_titles_json,
                        updated_at=excluded.updated_at""",
                    (project_key, display_name, project_url, project_id, int(enabled),
                     selection_policy, int(read_only), int(polling_interval_seconds),
                     json.dumps(excluded), now, now),
                )
                conn.commit()

    def list_projects(self):
        with self.db._lock:
            with contextlib.closing(self.db._connect()) as conn:
                rows = conn.execute("SELECT * FROM chatgpt_projects ORDER BY project_key").fetchall()
                return [dict(r) for r in rows]

    def get_project(self, project_key):
        with self.db._lock:
            with contextlib.closing(self.db._connect()) as conn:
                row = conn.execute("SELECT * FROM chatgpt_projects WHERE project_key=?", (project_key,)).fetchone()
                return dict(row) if row else None

    def get_active_project_key(self):
        with self.db._lock:
            with contextlib.closing(self.db._connect()) as conn:
                row = conn.execute("SELECT active_project_key FROM chatgpt_project_state WHERE id=1").fetchone()
                return row["active_project_key"] if row else None

    def set_active_project(self, project_key):
        proj = self.get_project(project_key)
        if not proj:
            raise ValueError("project not registered")
        if not proj["enabled"]:
            raise ValueError("project is disabled")
        with self.db._lock:
            with contextlib.closing(self.db._connect()) as conn:
                conn.execute(
                    "UPDATE chatgpt_project_state SET active_project_key=?, updated_at=? WHERE id=1",
                    (project_key, time.time()),
                )
                conn.commit()

    def get_polling_enabled(self):
        with self.db._lock:
            with contextlib.closing(self.db._connect()) as conn:
                row = conn.execute("SELECT polling_enabled FROM chatgpt_project_state WHERE id=1").fetchone()
                return bool(row["polling_enabled"]) if row else False

    def set_polling_enabled(self, enabled):
        with self.db._lock:
            with contextlib.closing(self.db._connect()) as conn:
                conn.execute(
                    "UPDATE chatgpt_project_state SET polling_enabled=?, updated_at=? WHERE id=1",
                    (int(bool(enabled)), time.time()),
                )
                conn.commit()

    def get_state(self):
        with self.db._lock:
            with contextlib.closing(self.db._connect()) as conn:
                row = conn.execute("SELECT * FROM chatgpt_project_state WHERE id=1").fetchone()
                return dict(row) if row else {}

    def update_read_state(self, last_read_at=None, last_error=None):
        with self.db._lock:
            with contextlib.closing(self.db._connect()) as conn:
                if last_read_at is not None:
                    conn.execute("UPDATE chatgpt_project_state SET last_read_at=?, updated_at=? WHERE id=1",
                                 (last_read_at, time.time()))
                if last_error is not None:
                    conn.execute("UPDATE chatgpt_project_state SET last_error=?, updated_at=? WHERE id=1",
                                 (last_error, time.time()))
                conn.commit()

    # --- conversation pinning ---

    def pin_conversation(self, project_key, conversation_id, conversation_title=None, pinned_by="operator"):
        proj = self.get_project(project_key)
        if not proj:
            raise ValueError("project not registered")
        if not proj["enabled"]:
            raise ValueError("project is disabled")
        now = time.time()
        with self.db._lock:
            with contextlib.closing(self.db._connect()) as conn:
                conn.execute(
                    "INSERT INTO chatgpt_pinned_conversations (project_key, conversation_id, conversation_title, pinned_at, pinned_by) VALUES (?,?,?,?,?) ON CONFLICT(project_key, conversation_id) DO UPDATE SET conversation_title=excluded.conversation_title, pinned_at=excluded.pinned_at, pinned_by=excluded.pinned_by",
                    (project_key, conversation_id, conversation_title, now, pinned_by),
                )
                conn.commit()
        return {"project_key": project_key, "conversation_id": conversation_id, "pinned_at": now}

    def unpin_conversation(self, project_key, conversation_id):
        with self.db._lock:
            with contextlib.closing(self.db._connect()) as conn:
                cur = conn.execute("DELETE FROM chatgpt_pinned_conversations WHERE project_key=? AND conversation_id=?", (project_key, conversation_id))
                conn.commit()
                return cur.rowcount > 0

    def get_pinned_conversation(self, project_key):
        with self.db._lock:
            with contextlib.closing(self.db._connect()) as conn:
                row = conn.execute("SELECT * FROM chatgpt_pinned_conversations WHERE project_key=? ORDER BY pinned_at DESC LIMIT 1", (project_key,)).fetchone()
                return dict(row) if row else None

    def list_pinned_conversations(self, project_key):
        with self.db._lock:
            with contextlib.closing(self.db._connect()) as conn:
                rows = conn.execute("SELECT * FROM chatgpt_pinned_conversations WHERE project_key=? ORDER BY pinned_at DESC", (project_key,)).fetchall()
                return [dict(r) for r in rows]

    # --- acknowledgement ---

    def acknowledge_observation(self, observation_id, acknowledged_by="operator"):
        with self.db._lock:
            with contextlib.closing(self.db._connect()) as conn:
                cur = conn.execute("UPDATE chatgpt_observations SET acknowledged=1, acknowledged_at=?, acknowledged_by=? WHERE observation_id=?", (time.time(), acknowledged_by, observation_id))
                conn.commit()
                return cur.rowcount > 0

    def get_unread_messages(self, project_key=None, conversation_id=None, limit=50):
        query = "SELECT * FROM chatgpt_observations WHERE acknowledged=0 AND role='user'"
        params = []
        if project_key:
            query += " AND project_key=?"
            params.append(project_key)
        if conversation_id:
            query += " AND conversation_id=?"
            params.append(conversation_id)
        query += " ORDER BY observed_at ASC LIMIT ?"
        params.append(limit)
        with self.db._lock:
            with contextlib.closing(self.db._connect()) as conn:
                rows = conn.execute(query, params).fetchall()
                return [dict(r) for r in rows]

    # --- observer state ---

    def get_observer_state(self):
        with self.db._lock:
            with contextlib.closing(self.db._connect()) as conn:
                row = conn.execute("SELECT * FROM chatgpt_observer_state WHERE id=1").fetchone()
                return dict(row) if row else {}

    def set_observer_status(self, status, active_project_key=None, pinned_conversation_id=None, last_error=None):
        valid = {"STOPPED", "RUNNING", "PAUSED", "ATTACHMENT_BLOCKED", "CONVERSATION_UNAVAILABLE", "ERROR"}
        if status not in valid:
            raise ValueError("invalid status: " + status)
        with self.db._lock:
            with contextlib.closing(self.db._connect()) as conn:
                if active_project_key is not None:
                    conn.execute("UPDATE chatgpt_observer_state SET active_project_key=?, updated_at=? WHERE id=1", (active_project_key, time.time()))
                if pinned_conversation_id is not None:
                    conn.execute("UPDATE chatgpt_observer_state SET pinned_conversation_id=?, updated_at=? WHERE id=1", (pinned_conversation_id, time.time()))
                if last_error is not None:
                    conn.execute("UPDATE chatgpt_observer_state SET last_error=?, updated_at=? WHERE id=1", (last_error, time.time()))
                conn.execute("UPDATE chatgpt_observer_state SET status=?, updated_at=? WHERE id=1", (status, time.time()))
                conn.commit()

    def increment_poll_count(self):
        with self.db._lock:
            with contextlib.closing(self.db._connect()) as conn:
                conn.execute("UPDATE chatgpt_observer_state SET poll_count=poll_count+1, last_poll_at=?, updated_at=? WHERE id=1", (time.time(), time.time()))
                conn.commit()

    def get_message_history(self, message_id, project_key=None):
        query = "SELECT * FROM chatgpt_observations WHERE message_id=?"
        params = [message_id]
        if project_key:
            query += " AND project_key=?"
            params.append(project_key)
        query += " ORDER BY observed_at ASC"
        with self.db._lock:
            with contextlib.closing(self.db._connect()) as conn:
                rows = conn.execute(query, params).fetchall()
                return [dict(r) for r in rows]

    # --- observations ---

    def record_observation(self, project_key, conversation_id, conversation_title,
                           message_id, role, content, visible_timestamp=None):
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        obs_id = "obs-" + hashlib.sha256((project_key + conversation_id + message_id + content_hash).encode()).hexdigest()[:16]
        now = time.time()
        with self.db._lock:
            with contextlib.closing(self.db._connect()) as conn:
                existing = conn.execute(
                    "SELECT observation_id, content_hash FROM chatgpt_observations WHERE project_key=? AND conversation_id=? AND message_id=?",
                    (project_key, conversation_id, message_id),
                ).fetchone()
                is_dup = 0
                edit_of = None
                if existing:
                    if existing["content_hash"] != content_hash:
                        edit_of = existing["observation_id"]
                    is_dup = 1
                try:
                    conn.execute(
                        """INSERT INTO chatgpt_observations
                           (observation_id, project_key, conversation_id, conversation_title,
                            message_id, role, content, content_hash, visible_timestamp,
                            observed_at, first_seen_at, last_seen_at, is_duplicate, edit_of)
                           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (obs_id, project_key, conversation_id, conversation_title,
                         message_id, role, content, content_hash, visible_timestamp,
                         now, now, now, is_dup, edit_of),
                    )
                    conn.commit()
                    return {"observation_id": obs_id, "duplicate": bool(is_dup), "edited": edit_of is not None, "edit_of": edit_of}
                except Exception:
                    return {"observation_id": obs_id, "duplicate": True, "edited": False, "edit_of": None}

    def get_observations(self, project_key=None, conversation_id=None, role=None, limit=50):
        query = "SELECT * FROM chatgpt_observations WHERE 1=1"
        params = []
        if project_key:
            query += " AND project_key=?"
            params.append(project_key)
        if conversation_id:
            query += " AND conversation_id=?"
            params.append(conversation_id)
        if role:
            query += " AND role=?"
            params.append(role)
        query += " ORDER BY observed_at DESC LIMIT ?"
        params.append(limit)
        with self.db._lock:
            with contextlib.closing(self.db._connect()) as conn:
                rows = conn.execute(query, params).fetchall()
                return [dict(r) for r in rows]

    def get_latest_observation(self, project_key=None):
        query = "SELECT * FROM chatgpt_observations WHERE 1=1"
        params = []
        if project_key:
            query += " AND project_key=?"
            params.append(project_key)
        query += " ORDER BY observed_at DESC LIMIT 1"
        with self.db._lock:
            with contextlib.closing(self.db._connect()) as conn:
                row = conn.execute(query, params).fetchone()
                return dict(row) if row else None


class ChatGPTProjectReader:
    """Read-only reader. Wraps PlaywrightChatGPTAdapter. Never sends messages."""

    def __init__(self, adapter, registry, project_key=None):
        if not hasattr(adapter, "read_latest_messages"):
            from .chatgpt_interface import PlaywrightChatGPTAdapter
            adapter = PlaywrightChatGPTAdapter(adapter)
        self.adapter = adapter
        self.registry = registry
        self.project_key = project_key or registry.get_active_project_key()

    def _project(self):
        if not self.project_key:
            raise ValueError("no active project configured")
        proj = self.registry.get_project(self.project_key)
        if not proj:
            raise ValueError("project not registered: " + self.project_key)
        if not proj["enabled"]:
            raise ValueError("project is disabled: " + self.project_key)
        return proj

    def discover_conversation(self):
        proj = self._project()
        excluded = json.loads(proj.get("excluded_titles_json") or "[]")
        result = self.adapter.discover_latest_conversation(proj["project_url"], excluded_titles=excluded)
        if not result.get("ok"):
            self.registry.update_read_state(last_error=result.get("reason", "discovery_failed"))
            return result
        if result.get("project_id") and result["project_id"] != proj["project_id"]:
            self.registry.update_read_state(last_error="project_identity_mismatch")
            return {"ok": False, "reason": "project_identity_mismatch",
                    "expected": proj["project_id"], "actual": result["project_id"]}
        return result

    def read_messages(self, max_messages=10):
        proj = self._project()
        excluded = json.loads(proj.get("excluded_titles_json") or "[]")
        result = self.adapter.read_latest_messages(proj["project_url"], excluded_titles=excluded, max_messages=max_messages)
        if not result.get("ok"):
            self.registry.update_read_state(last_error=result.get("reason", "read_failed"))
            return result

        conversation_id = result.get("conversation_id", "")
        conversation_title = result.get("title", "")
        messages = result.get("messages", [])
        observations = []
        for msg in messages:
            mid = msg.get("message_id", "")
            role = "user" if msg.get("source") == "chatgpt" else msg.get("role", "assistant")
            content = msg.get("message_content", "")
            obs = self.registry.record_observation(
                project_key=self.project_key,
                conversation_id=conversation_id,
                conversation_title=conversation_title,
                message_id=mid,
                role=role,
                content=content,
                visible_timestamp=msg.get("message_timestamp"),
            )
            observations.append({"message_id": mid, "role": role, "content": content, "observation": obs})

        self.registry.update_read_state(last_read_at=time.time(), last_error=None)
        return {
            "ok": True,
            "project_key": self.project_key,
            "project_name": proj["display_name"],
            "conversation_id": conversation_id,
            "conversation_title": conversation_title,
            "messages": observations,
            "message_count": len(observations),
            "user_message_count": sum(1 for o in observations if o["role"] == "user"),
        }

    def pin_conversation(self, conversation_id, conversation_title=None, pinned_by="operator"):
        proj = self._project()
        return self.registry.pin_conversation(self.project_key, conversation_id, conversation_title, pinned_by)

    def unpin_conversation(self, conversation_id):
        return self.registry.unpin_conversation(self.project_key, conversation_id)

    def get_pinned_conversation(self):
        return self.registry.get_pinned_conversation(self.project_key)

    def acknowledge(self, observation_id, acknowledged_by="operator"):
        return self.registry.acknowledge_observation(observation_id, acknowledged_by)

    def get_unread(self, limit=50):
        return {"ok": True, "messages": self.registry.get_unread_messages(self.project_key, limit=limit)}

    def get_latest_snapshot(self):
        obs = self.registry.get_latest_observation(self.project_key)
        if not obs:
            return {"ok": False, "reason": "no_observations"}
        return {"ok": True, "observation": obs}

    def get_new_user_messages(self, since_observed_at=None):
        obs_list = self.registry.get_observations(project_key=self.project_key, role="user", limit=100)
        if since_observed_at:
            obs_list = [o for o in obs_list if o["observed_at"] > since_observed_at]
        return {"ok": True, "messages": obs_list, "count": len(obs_list)}

    def get_state(self):
        return {
            "ok": True,
            "project_key": self.project_key,
            "state": self.registry.get_state(),
            "project": self.registry.get_project(self.project_key) if self.project_key else None,
            "observer": self.registry.get_observer_state(),
            "pinned_conversation": self.registry.get_pinned_conversation(self.project_key),
        }

    def get_message_history(self, message_id):
        return {"ok": True, "history": self.registry.get_message_history(message_id, self.project_key)}
