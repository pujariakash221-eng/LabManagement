"""Configuration values for the lab computer agent."""

import os
from dataclasses import dataclass
from pathlib import Path


def _load_agent_env_fallback() -> None:
    if not os.getenv("LAB_AGENT_TOKEN") and not os.getenv("LAB_AGENT_ENROLLMENT_SECRET"):
        candidates = [
            Path("agent.env"),
            Path(".env"),
            Path(__file__).resolve().parent.parent / "agent.env",
            Path(__file__).resolve().parent.parent / ".env",
        ]
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
class AgentConfig:
    """Settings used when the agent connects to the server."""

    server_url: str = "http://127.0.0.1:8000"
    heartbeat_interval: float = 5.0
    agent_id_path: Path = Path.home() / ".lab_management" / "agent_id"
    enrollment_secret: str = ""
    power_dry_run: bool = True

    @classmethod
    def from_environment(cls) -> "AgentConfig":
        """Build configuration, allowing the server URL to be overridden."""
        _load_agent_env_fallback()
        return cls(
            server_url=os.getenv("LAB_SERVER_URL", cls.server_url),
            heartbeat_interval=float(
                os.getenv("LAB_HEARTBEAT_INTERVAL", str(cls.heartbeat_interval))
            ),
            enrollment_secret=os.getenv("LAB_AGENT_TOKEN") or os.getenv("LAB_AGENT_ENROLLMENT_SECRET", ""),
            power_dry_run=os.getenv("LAB_POWER_DRY_RUN", "true").lower() in {"1", "true", "yes"},
        )
