"""HTTP client for communicating with the lab management server."""

import httpx


class AgentRegistrationError(RuntimeError):
    """Raised when the agent cannot register successfully."""


def _agent_headers(enrollment_secret: str) -> dict[str, str]:
    if not enrollment_secret:
        raise AgentRegistrationError("LAB_AGENT_ENROLLMENT_SECRET is not configured")
    return {"X-Agent-Token": enrollment_secret}


def register_agent(server_url: str, agent_info: dict[str, str], enrollment_secret: str) -> dict[str, str]:
    """Register an agent and return the server's validated response."""
    endpoint = f"{server_url.rstrip('/')}/api/agents/register"
    try:
        response = httpx.post(endpoint, json=agent_info, headers=_agent_headers(enrollment_secret), timeout=5.0)
        response.raise_for_status()
        result = response.json()
    except httpx.HTTPStatusError as exc:
        raise AgentRegistrationError(
            f"server rejected registration with HTTP {exc.response.status_code}"
        ) from exc
    except httpx.RequestError as exc:
        raise AgentRegistrationError(f"server unavailable: {exc}") from exc
    except ValueError as exc:
        raise AgentRegistrationError("server returned an invalid JSON response") from exc

    if not isinstance(result, dict):
        raise AgentRegistrationError("server returned an invalid registration response")
    return result


def send_heartbeat(server_url: str, agent_id: str, enrollment_secret: str) -> dict[str, str]:
    """Send one heartbeat and return the server's response."""
    endpoint = f"{server_url.rstrip('/')}/api/agents/{agent_id}/heartbeat"
    try:
        response = httpx.post(endpoint, headers=_agent_headers(enrollment_secret), timeout=5.0)
        response.raise_for_status()
        result = response.json()
    except httpx.HTTPStatusError as exc:
        raise AgentRegistrationError(
            f"server rejected heartbeat with HTTP {exc.response.status_code}"
        ) from exc
    except httpx.RequestError as exc:
        raise AgentRegistrationError(f"server unavailable: {exc}") from exc
    except ValueError as exc:
        raise AgentRegistrationError("server returned an invalid JSON response") from exc

    if not isinstance(result, dict):
        raise AgentRegistrationError("server returned an invalid heartbeat response")
    return result


def fetch_power_command(server_url: str, agent_id: str, enrollment_secret: str) -> dict | None:
    """Fetch at most one structured power command for this trusted agent."""
    endpoint = f"{server_url.rstrip('/')}/api/agents/{agent_id}/power-command"
    try:
        response = httpx.get(endpoint, headers=_agent_headers(enrollment_secret), timeout=5.0)
        response.raise_for_status()
        result = response.json()
    except (httpx.RequestError, httpx.HTTPStatusError, ValueError) as exc:
        raise AgentRegistrationError(f"power command check failed: {exc}") from exc
    return result.get("command") if isinstance(result, dict) else None


def acknowledge_power_command(server_url: str, agent_id: str, enrollment_secret: str, command_id: str, result: str) -> None:
    """Report the outcome without including credentials or command text."""
    endpoint = f"{server_url.rstrip('/')}/api/agents/{agent_id}/power-command/ack"
    try:
        response = httpx.post(endpoint, headers=_agent_headers(enrollment_secret), json={"command_id": command_id, "result": result}, timeout=5.0)
        response.raise_for_status()
    except (httpx.RequestError, httpx.HTTPStatusError) as exc:
        raise AgentRegistrationError(f"power command acknowledgement failed: {exc}") from exc
