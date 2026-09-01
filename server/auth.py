"""Small, same-origin authentication and authorization helpers."""

import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request, status

from server.config import ServerConfig
from server.database import Database
from server.audit import audit_log

ROLE_ORDER = {"VIEWER": 1, "OPERATOR": 2, "ADMIN": 3}


@dataclass(frozen=True)
class User:
    username: str
    role: str


class AuthService:
    """Authenticates the configured bootstrap administrator and sessions."""

    def __init__(self, config: ServerConfig, database: Database) -> None:
        self.config = config
        self.database = database
        self._bootstrap_users()
        self._sessions: dict[str, float] = {}

    def _bootstrap_users(self) -> None:
        self.database.bootstrap_user(self.config.initial_admin_username, self._hash_password(self.config.initial_admin_password), "ADMIN")
        if self.config.bootstrap_viewer_username and self.config.bootstrap_viewer_password:
            self.database.bootstrap_user(self.config.bootstrap_viewer_username, self._hash_password(self.config.bootstrap_viewer_password), "VIEWER")
        if self.config.bootstrap_operator_username and self.config.bootstrap_operator_password:
            self.database.bootstrap_user(self.config.bootstrap_operator_username, self._hash_password(self.config.bootstrap_operator_password), "OPERATOR")

    @staticmethod
    def _hash_password(password: str, salt: bytes | None = None) -> str:
        salt = salt or secrets.token_bytes(16)
        digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2**14, r=8, p=1)
        return f"scrypt$16384$8$1${salt.hex()}${digest.hex()}"

    @staticmethod
    def _verify_password(password: str, encoded: str) -> bool:
        try:
            _, n, r, p, salt, digest = encoded.split("$")
            candidate = hashlib.scrypt(password.encode("utf-8"), salt=bytes.fromhex(salt), n=int(n), r=int(r), p=int(p))
            return hmac.compare_digest(candidate.hex(), digest)
        except (TypeError, ValueError):
            return False

    def authenticate(self, username: str, password: str) -> User | None:
        record = self.database.get_user(username)
        if not record or not record["enabled"] or not self._verify_password(password, record["password_hash"]):
            return None
        return User(username=record["username"], role=record["role"])

    def create_session(self) -> str:
        session_id = secrets.token_urlsafe(32)
        self._sessions[session_id] = time.time() + self.config.session_max_age
        return session_id

    def revoke_session(self, session_id: str | None) -> None:
        if session_id:
            self._sessions.pop(session_id, None)

    def session_active(self, session_id: str | None) -> bool:
        if not session_id:
            return False
        expiry = self._sessions.get(session_id, 0)
        if expiry <= time.time():
            self._sessions.pop(session_id, None)
            return False
        return True


def user_from_request(request: Request) -> User:
    auth: AuthService = request.app.state.auth
    session = request.session
    session_id = session.get("id")
    role = session.get("role")
    username = session.get("username")
    if not auth.session_active(session_id) or role not in ROLE_ORDER or not isinstance(username, str):
        audit_log(request.app.state.database, "authorization_failure", result="denied", metadata={"path": request.url.path})
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    return User(username=username, role=role)


def require_role(role: str):
    def dependency(request: Request, user: User = Depends(user_from_request)) -> User:
        if ROLE_ORDER[user.role] < ROLE_ORDER[role]:
            audit_log(request.app.state.database, "authorization_failure", username=user.username, result="denied", metadata={"required_role": role})
            if role == "OPERATOR" and request.url.path.endswith(("/shutdown", "/restart")):
                audit_log(request.app.state.database, "POWER_AUTHORIZATION_DENIED", username=user.username, result="denied")
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
        return user
    return dependency


require_viewer = require_role("VIEWER")
require_operator = require_role("OPERATOR")
require_admin = require_role("ADMIN")
