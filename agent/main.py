"""Command entry point for registering this computer with the server."""

import logging
import subprocess
import threading
import time

from agent.client import AgentRegistrationError, acknowledge_power_command, fetch_power_command, register_agent, send_heartbeat
from agent.config import AgentConfig
from agent.power import execute_power_action
from agent.screen_stream import run_screen_stream
from agent.system_info import collect_system_info

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def register(config: AgentConfig | None = None) -> dict[str, str]:
    """Collect local information and register this agent with the server."""
    config = config or AgentConfig.from_environment()
    agent_info = collect_system_info(config.agent_id_path)
    return register_agent(config.server_url, agent_info, config.enrollment_secret)


def run(config: AgentConfig | None = None) -> None:
    """Register this agent and keep sending heartbeats until interrupted."""
    config = config or AgentConfig.from_environment()
    agent_info = collect_system_info(config.agent_id_path)
    logger.info("Starting Lab Management Agent for '%s' (Server: %s, Dry-Run: %s)", agent_info.get("hostname"), config.server_url, config.power_dry_run)

    while True:
        try:
            response = register_agent(config.server_url, agent_info, config.enrollment_secret)
            logger.info("Successfully registered agent %s (%s)", response["agent_id"], agent_info.get("hostname"))
            break
        except AgentRegistrationError as exc:
            logger.warning("Registration failed: %s; retrying in %.1fs", exc, config.heartbeat_interval)
            time.sleep(config.heartbeat_interval)

    # Start screen streaming in a separate daemon thread
    agent_id = agent_info["agent_id"]
    screen_thread = threading.Thread(
        target=run_screen_stream,
        args=(config.server_url, agent_id, config.enrollment_secret),
        daemon=True,
        name="ScreenStream",
    )
    screen_thread.start()
    logger.info("Screen streaming thread started for agent %s", agent_id)

    while True:
        time.sleep(config.heartbeat_interval)
        try:
            send_heartbeat(config.server_url, agent_info["agent_id"], config.enrollment_secret)
            command = fetch_power_command(config.server_url, agent_info["agent_id"], config.enrollment_secret)
            if command:
                command_id, action = command.get("id"), command.get("action")
                logger.info("Received power command '%s' (id: %s, dry_run=%s)", action, command_id, config.power_dry_run)
                try:
                    result = execute_power_action(action, config.power_dry_run)
                    logger.info("Power action '%s' executed with result: %s", action, result)
                except (ValueError, RuntimeError, OSError, subprocess.SubprocessError) as exc:
                    logger.error("Power action '%s' failed: %s", action, exc)
                    result = "failure"
                if command_id:
                    acknowledge_power_command(config.server_url, agent_info["agent_id"], config.enrollment_secret, command_id, result)
                    logger.info("Acknowledged power command %s (result=%s)", command_id, result)
        except AgentRegistrationError as exc:
            logger.warning("Heartbeat failed: %s; attempting re-registration", exc)
            try:
                register_agent(config.server_url, agent_info, config.enrollment_secret)
                logger.info("Re-registration successful for agent %s", agent_info["agent_id"])
            except AgentRegistrationError as registration_error:
                logger.warning("Registration retry failed: %s", registration_error)


if __name__ == "__main__":
    try:
        run()
    except KeyboardInterrupt:
        logger.info("Agent stopped by user")
