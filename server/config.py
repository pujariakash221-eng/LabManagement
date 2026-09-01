import os
from dataclasses import dataclass
from pathlib import Path


def _load_env_fallback() -> None:
    if not os.getenv("LAB_APP_SECRET"):
        candidates = [Path(".env"), Path(__file__).resolve().parent.parent / ".env"]
        for path in candidates:
            if path.is_file():
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        for line in f:
                            line = line.strip()
                            if line and not line.startswith("#") and "=" in line:
                                k, v = line.split("=", 1)
                                k, v = k.strip(), v.strip()
                                if k and k not in os.environ:
                                    os.environ[k] = v
                    break
                except OSError:
                    pass


@dataclass(frozen=True)
class ServerConfig:
    """Settings that control how the server is exposed on the network."""

    host: str = "0.0.0.0"
    port: int = 8000
    offline_timeout: float = 15.0
    app_secret: str = ""
    initial_admin_username: str = ""
    initial_admin_password: str = ""
    bootstrap_viewer_username: str = ""
    bootstrap_viewer_password: str = ""
    bootstrap_operator_username: str = ""
    bootstrap_operator_password: str = ""
    agent_enrollment_secret: str = ""
    session_max_age: int = 28800
    secure_cookies: bool = False
    database_path: str = "labmanagement.sqlite3"
    power_dry_run: bool = True
    audit_max_entries: int = 10000

    @classmethod
    def from_environment(cls) -> "ServerConfig":
        """Load server settings from environment variables."""
        _load_env_fallback()
        config = cls(
            host=os.getenv("LAB_SERVER_HOST", cls.host),
            port=int(os.getenv("LAB_SERVER_PORT", str(cls.port))),
            offline_timeout=float(
                os.getenv("LAB_OFFLINE_TIMEOUT", str(cls.offline_timeout))
            ),
            app_secret=os.getenv("LAB_APP_SECRET", ""),
            initial_admin_username=os.getenv("LAB_INITIAL_ADMIN_USERNAME", ""),
            initial_admin_password=os.getenv("LAB_INITIAL_ADMIN_PASSWORD", ""),
            bootstrap_viewer_username=os.getenv("LAB_BOOTSTRAP_VIEWER_USERNAME", ""),
            bootstrap_viewer_password=os.getenv("LAB_BOOTSTRAP_VIEWER_PASSWORD", ""),
            bootstrap_operator_username=os.getenv("LAB_BOOTSTRAP_OPERATOR_USERNAME", ""),
            bootstrap_operator_password=os.getenv("LAB_BOOTSTRAP_OPERATOR_PASSWORD", ""),
            agent_enrollment_secret=os.getenv("LAB_AGENT_ENROLLMENT_SECRET", ""),
            session_max_age=int(os.getenv("LAB_SESSION_MAX_AGE", str(cls.session_max_age))),
            secure_cookies=os.getenv("LAB_SECURE_COOKIES", "false").lower() in {"1", "true", "yes"},
            database_path=os.getenv("LAB_DATABASE_PATH", cls.database_path),
            power_dry_run=os.getenv("LAB_POWER_DRY_RUN", "true").lower() in {"1", "true", "yes"},
            audit_max_entries=int(os.getenv("LAB_AUDIT_MAX_ENTRIES", str(cls.audit_max_entries))),
        )
        missing = [name for name, value in {
            "LAB_APP_SECRET": config.app_secret,
            "LAB_INITIAL_ADMIN_USERNAME": config.initial_admin_username,
            "LAB_INITIAL_ADMIN_PASSWORD": config.initial_admin_password,
            "LAB_AGENT_ENROLLMENT_SECRET": config.agent_enrollment_secret,
        }.items() if not value]
        if missing:
            raise RuntimeError("Missing required security configuration: " + ", ".join(missing))
        if len(config.app_secret) < 32 or len(config.agent_enrollment_secret) < 24:
            raise RuntimeError("LAB_APP_SECRET and LAB_AGENT_ENROLLMENT_SECRET must be long random values")
        if config.offline_timeout <= 0 or config.session_max_age <= 0 or config.audit_max_entries < 100:
            raise RuntimeError("LAB_OFFLINE_TIMEOUT, LAB_SESSION_MAX_AGE, and LAB_AUDIT_MAX_ENTRIES must be positive")
        return config
