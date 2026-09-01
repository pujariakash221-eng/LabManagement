"""Local identity and system information collected by the agent."""

import platform
import socket
import uuid
from pathlib import Path


def get_hostname() -> str:
    """Return this computer's network hostname."""
    return socket.gethostname()


def get_local_ip() -> str:
    """Find the preferred local IP without sending application data."""
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("8.8.8.8", 80))
        return probe.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        probe.close()


def get_operating_system() -> str:
    """Return a readable operating system description."""
    return platform.platform()


def get_agent_id(path: Path) -> str:
    """Read or create a stable UUID for this computer."""
    try:
        agent_id = path.read_text(encoding="utf-8").strip()
        if agent_id:
            return agent_id
    except FileNotFoundError:
        pass

    agent_id = str(uuid.uuid4())
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(agent_id, encoding="utf-8")
    return agent_id


def collect_system_info(agent_id_path: Path) -> dict[str, str]:
    """Collect the fields expected by the server registration endpoint."""
    return {
        "agent_id": get_agent_id(agent_id_path),
        "hostname": get_hostname(),
        "ip_address": get_local_ip(),
        "operating_system": get_operating_system(),
    }