"""Strict platform-specific power operations for authorized agent commands."""

import platform
import subprocess

ALLOWED_ACTIONS = {"shutdown", "restart"}


def execute_power_action(action: str, dry_run: bool) -> str:
    """Execute one fixed power operation; never accepts shell command text."""
    if action not in ALLOWED_ACTIONS:
        raise ValueError("Unsupported power action")
    if dry_run:
        return "dry_run"

    system = platform.system()
    commands = {
        "Windows": {"shutdown": ["shutdown", "/s", "/t", "0"], "restart": ["shutdown", "/r", "/t", "0"]},
        "Linux": {"shutdown": ["systemctl", "poweroff"], "restart": ["systemctl", "reboot"]},
        "Darwin": {"shutdown": ["shutdown", "-h", "now"], "restart": ["shutdown", "-r", "now"]},
    }
    if system not in commands:
        raise RuntimeError(f"Unsupported operating system: {system}")
    subprocess.run(commands[system][action], check=True, timeout=15, shell=False)
    return "executed"
