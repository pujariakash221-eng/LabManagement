"""Reusable, secret-safe audit logging."""
import json


def audit_log(database, action: str, username: str | None = None, target_agent: str | None = None, result: str = "success", metadata: dict | None = None) -> None:
    database.add_audit(username, action, target_agent, result, json.dumps(metadata) if metadata else None)
