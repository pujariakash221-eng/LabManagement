"""SQLite persistence for users, managed agents, and audit events."""

import sqlite3
import os
from datetime import datetime, timezone
from pathlib import Path


from contextlib import contextmanager


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class Database:
    def __init__(self, path: str, audit_max_entries: int = 10000) -> None:
        self.path = Path(path)
        self.audit_max_entries = audit_max_entries
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()
        try:
            os.chmod(self.path, 0o600)
        except OSError:
            pass

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def initialize(self) -> None:
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY,
                    username TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    role TEXT NOT NULL CHECK (role IN ('VIEWER', 'OPERATOR', 'ADMIN')),
                    created_at TEXT NOT NULL,
                    enabled INTEGER NOT NULL DEFAULT 1
                );
                CREATE TABLE IF NOT EXISTS agents (
                    agent_id TEXT PRIMARY KEY,
                    hostname TEXT NOT NULL,
                    ip_address TEXT NOT NULL,
                    operating_system TEXT NOT NULL,
                    first_seen TEXT NOT NULL,
                    last_seen TEXT NOT NULL,
                    status TEXT NOT NULL,
                    credential_hash TEXT NOT NULL,
                    enabled INTEGER NOT NULL DEFAULT 1
                );
                CREATE TABLE IF NOT EXISTS audit_log (
                    id INTEGER PRIMARY KEY,
                    timestamp TEXT NOT NULL,
                    username TEXT,
                    action TEXT NOT NULL,
                    target_agent TEXT,
                    result TEXT NOT NULL,
                    metadata TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_audit_log_timestamp ON audit_log(timestamp DESC);
            """)

    def bootstrap_user(self, username: str, password_hash: str, role: str) -> None:
        with self.connect() as db:
            db.execute("INSERT OR IGNORE INTO users (username, password_hash, role, created_at, enabled) VALUES (?, ?, ?, ?, 1)", (username, password_hash, role, utcnow()))

    def get_user(self, username: str):
        with self.connect() as db:
            row = db.execute("SELECT username, password_hash, role, enabled FROM users WHERE username = ?", (username,)).fetchone()
            return dict(row) if row else None

    def upsert_agent(self, registration: dict[str, str], credential_hash: str) -> dict:
        now = utcnow()
        with self.connect() as db:
            existing = db.execute("SELECT first_seen FROM agents WHERE agent_id = ?", (registration["agent_id"],)).fetchone()
            db.execute("""INSERT INTO agents (agent_id, hostname, ip_address, operating_system, first_seen, last_seen, status, credential_hash, enabled)
                VALUES (?, ?, ?, ?, ?, ?, 'ONLINE', ?, 1)
                ON CONFLICT(agent_id) DO UPDATE SET hostname=excluded.hostname, ip_address=excluded.ip_address,
                operating_system=excluded.operating_system, last_seen=excluded.last_seen, status='ONLINE', credential_hash=excluded.credential_hash""",
                (registration["agent_id"], registration["hostname"], registration["ip_address"], registration["operating_system"], existing["first_seen"] if existing else now, now, credential_hash))
        return self.get_agent(registration["agent_id"])

    def heartbeat(self, agent_id: str) -> dict | None:
        with self.connect() as db:
            previous = db.execute("SELECT status FROM agents WHERE agent_id = ? AND enabled = 1", (agent_id,)).fetchone()
            if previous is None:
                return None
            db.execute("UPDATE agents SET last_seen = ?, status = 'ONLINE' WHERE agent_id = ? AND enabled = 1", (utcnow(), agent_id))
        result = self.get_agent(agent_id)
        result["was_offline"] = previous["status"] == "OFFLINE"
        return result

    def get_agent(self, agent_id: str) -> dict | None:
        with self.connect() as db:
            row = db.execute("SELECT agent_id, hostname, ip_address, operating_system, first_seen, last_seen, status FROM agents WHERE agent_id = ? AND enabled = 1", (agent_id,)).fetchone()
        return dict(row) if row else None

    def get_managed_agent(self, agent_id: str) -> dict | None:
        """Return an agent including its enabled state for server-side validation."""
        with self.connect() as db:
            row = db.execute("SELECT agent_id, hostname, ip_address, operating_system, first_seen, last_seen, status, enabled FROM agents WHERE agent_id = ?", (agent_id,)).fetchone()
        return dict(row) if row else None

    def list_agents(self) -> list[dict]:
        with self.connect() as db:
            rows = db.execute("SELECT agent_id, hostname, ip_address, operating_system, first_seen, last_seen, status FROM agents WHERE enabled = 1 ORDER BY hostname").fetchall()
        return [dict(row) for row in rows]

    def update_status(self, agent_id: str, status: str) -> None:
        with self.connect() as db:
            db.execute("UPDATE agents SET status = ? WHERE agent_id = ?", (status, agent_id))

    def add_audit(self, username: str | None, action: str, target_agent: str | None, result: str, metadata: str | None) -> None:
        with self.connect() as db:
            db.execute("INSERT INTO audit_log (timestamp, username, action, target_agent, result, metadata) VALUES (?, ?, ?, ?, ?, ?)", (utcnow(), username, action, target_agent, result, metadata))
            db.execute("DELETE FROM audit_log WHERE id NOT IN (SELECT id FROM audit_log ORDER BY id DESC LIMIT ?)", (self.audit_max_entries,))

    def recent_audit(self, limit: int = 100) -> list[dict]:
        with self.connect() as db:
            rows = db.execute("SELECT timestamp, username, action, target_agent, result, metadata FROM audit_log ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(row) for row in rows]
