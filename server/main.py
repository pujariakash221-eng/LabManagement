"""FastAPI application entry point for the lab management server."""

import hmac
import hashlib
import logging
import secrets
import asyncio
import ipaddress
import time
import uuid
from datetime import datetime, timezone
from threading import Lock
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect, status
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.sessions import SessionMiddleware
from pydantic import BaseModel, Field, field_validator

from server.discovery import DiscoveredDevice, discover_devices
from server.config import ServerConfig
from server.auth import AuthService, User, require_admin, require_operator, require_viewer
from server.database import Database
from server.audit import audit_log

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)
SERVER_CONFIG = ServerConfig.from_environment()
OFFLINE_TIMEOUT_SECONDS = SERVER_CONFIG.offline_timeout


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security headers to all HTTP responses."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        if SERVER_CONFIG.secure_cookies:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response


class AgentRegistration(BaseModel):
    """Information supplied by an agent when it registers."""

    agent_id: str = Field(min_length=36, max_length=36)
    hostname: str = Field(min_length=1, max_length=255)
    ip_address: str = Field(min_length=3, max_length=45)
    operating_system: str = Field(min_length=1, max_length=255)

    @field_validator("agent_id")
    @classmethod
    def validate_agent_id(cls, value: str) -> str:
        return str(uuid.UUID(value))

    @field_validator("ip_address")
    @classmethod
    def validate_ip_address(cls, value: str) -> str:
        return str(ipaddress.ip_address(value))


class Agent(AgentRegistration):
    """An agent currently known to this server, including its status."""

    status: str
    first_seen: datetime
    last_seen: datetime


discovery_results: list[DiscoveredDevice] = []
discovery_lock = Lock()

# Screen streaming: maps agent_id to active screen stream metadata
screen_streams: dict[str, dict] = {}
screen_streams_lock = Lock()
pending_power_commands: dict[str, dict] = {}
power_commands_lock = Lock()

app = FastAPI(title="Lab Management Server")
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(SessionMiddleware, secret_key=SERVER_CONFIG.app_secret, session_cookie="lab_session", max_age=SERVER_CONFIG.session_max_age, same_site="lax", https_only=SERVER_CONFIG.secure_cookies)
app.state.database = Database(SERVER_CONFIG.database_path, SERVER_CONFIG.audit_max_entries)
app.state.auth = AuthService(SERVER_CONFIG, app.state.database)
dashboard_directory = Path(__file__).resolve().parent.parent / "dashboard"
app.mount("/static", StaticFiles(directory=dashboard_directory), name="static")


@app.get("/", include_in_schema=False, response_model=None)
def dashboard(request: Request):
    """Serve the operator dashboard application."""
    if not app.state.auth.session_active(request.session.get("id")):
        return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)
    return FileResponse(dashboard_directory / "index.html")


@app.get("/login", include_in_schema=False, response_model=None)
def login_page(request: Request):
    if app.state.auth.session_active(request.session.get("id")):
        return RedirectResponse("/", status_code=status.HTTP_303_SEE_OTHER)
    return FileResponse(dashboard_directory / "login.html")


@app.get("/api/health")
def health_check() -> dict[str, str]:
    """Report whether the central server is running."""
    return {"status": "running"}


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=1, max_length=1024)


class PowerAcknowledgement(BaseModel):
    command_id: str = Field(min_length=16, max_length=64)
    result: str = Field(min_length=1, max_length=16)


@app.post("/api/auth/login")
def login(credentials: LoginRequest, request: Request) -> dict[str, str]:
    user = app.state.auth.authenticate(credentials.username, credentials.password)
    if user is None:
        audit_log(app.state.database, "login", credentials.username, result="failed")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    request.session.clear()
    request.session.update({"id": app.state.auth.create_session(), "username": user.username, "role": user.role})
    audit_log(app.state.database, "login", user.username)
    return {"username": user.username, "role": user.role}


@app.post("/api/auth/logout")
def logout(request: Request) -> dict[str, str]:
    username = request.session.get("username")
    app.state.auth.revoke_session(request.session.get("id"))
    request.session.clear()
    audit_log(app.state.database, "logout", username)
    return {"status": "logged out"}


@app.get("/api/auth/session")
def session_info(user: User = Depends(require_viewer)) -> dict[str, str]:
    return {"username": user.username, "role": user.role}


@app.get("/api/admin/status")
def admin_status(_: User = Depends(require_admin)) -> dict[str, str]:
    """Reserved administrative endpoint that demonstrates ADMIN enforcement."""
    audit_log(app.state.database, "administrative_action", _.username, result="success", metadata={"action": "view_admin_status"})
    return {"status": "admin access granted"}


@app.get("/api/admin/agents", response_model=list[Agent])
def persistent_agents(_: User = Depends(require_admin)) -> list[Agent]:
    """ADMIN-only view of the persistent managed-agent inventory."""
    return [Agent(**record) for record in app.state.database.list_agents()]


def queue_power_command(agent_id: str, action: str, user: User) -> dict[str, str]:
    if action not in {"shutdown", "restart"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid power action")
    managed = app.state.database.get_managed_agent(agent_id)
    if managed is None:
        audit_log(app.state.database, f"POWER_{action.upper()}_FAILURE", user.username, agent_id, "failed", {"reason": "unknown_agent"})
        raise HTTPException(status_code=404, detail="Agent not found")
    if not managed["enabled"]:
        audit_log(app.state.database, f"POWER_{action.upper()}_FAILURE", user.username, agent_id, "failed", {"reason": "disabled_agent"})
        raise HTTPException(status_code=409, detail="Agent is disabled")
    agent = refresh_status(Agent(**{key: value for key, value in managed.items() if key != "enabled"}), current_time())
    if agent.status != "ONLINE":
        audit_log(app.state.database, f"POWER_{action.upper()}_FAILURE", user.username, agent_id, "failed", {"reason": "offline_agent"})
        raise HTTPException(status_code=409, detail="Agent is offline")
    with power_commands_lock:
        existing = pending_power_commands.get(agent_id)
        if existing and time.monotonic() - existing["created_at"] < 120:
            raise HTTPException(status_code=409, detail="A power command is already pending")
        command = {"id": secrets.token_urlsafe(18), "action": action, "operator": user.username, "created_at": time.monotonic()}
        pending_power_commands[agent_id] = command
    audit_log(app.state.database, f"POWER_{action.upper()}_REQUEST", user.username, agent_id, "queued", {"dry_run": SERVER_CONFIG.power_dry_run})
    return {"status": "queued", "action": action}


@app.post("/api/agents/{agent_id}/shutdown", status_code=status.HTTP_202_ACCEPTED)
def shutdown_agent(agent_id: str, user: User = Depends(require_operator)) -> dict[str, str]:
    return queue_power_command(agent_id, "shutdown", user)


@app.post("/api/agents/{agent_id}/restart", status_code=status.HTTP_202_ACCEPTED)
def restart_agent(agent_id: str, user: User = Depends(require_operator)) -> dict[str, str]:
    return queue_power_command(agent_id, "restart", user)


@app.get("/api/agents/{agent_id}/power-command")
def get_power_command(agent_id: str, request: Request) -> dict:
    require_agent_credential(request.headers.get("X-Agent-Token"))
    if app.state.database.get_agent(agent_id) is None:
        raise HTTPException(status_code=404, detail="Agent not registered")
    with power_commands_lock:
        command = pending_power_commands.get(agent_id)
        if command and time.monotonic() - command["created_at"] >= 120:
            del pending_power_commands[agent_id]
            audit_log(app.state.database, f"POWER_{command['action'].upper()}_FAILURE", command["operator"], agent_id, "expired")
            command = None
    return {"command": {"id": command["id"], "action": command["action"]} if command else None}


@app.post("/api/agents/{agent_id}/power-command/ack")
def acknowledge_power_command(agent_id: str, acknowledgement: PowerAcknowledgement, request: Request) -> dict[str, str]:
    require_agent_credential(request.headers.get("X-Agent-Token"))
    if acknowledgement.result not in {"dry_run", "executed", "failure"}:
        raise HTTPException(status_code=400, detail="Invalid command result")
    with power_commands_lock:
        command = pending_power_commands.get(agent_id)
        if not command or not hmac.compare_digest(command["id"], acknowledgement.command_id):
            raise HTTPException(status_code=404, detail="Command not found")
        del pending_power_commands[agent_id]
    outcome = "SUCCESS" if acknowledgement.result in {"dry_run", "executed"} else "FAILURE"
    audit_log(app.state.database, f"POWER_{command['action'].upper()}_{outcome}", command["operator"], agent_id, acknowledgement.result, {"dry_run": acknowledgement.result == "dry_run"})
    return {"status": "acknowledged"}


@app.get("/api/audit")
def recent_audit(_: User = Depends(require_admin)) -> list[dict]:
    return app.state.database.recent_audit()


def require_agent_credential(token: str | None) -> None:
    if not token or not hmac.compare_digest(token, SERVER_CONFIG.agent_enrollment_secret):
        audit_log(app.state.database, "agent_authentication", result="failed")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid agent credential")


def current_time() -> datetime:
    """Return a timezone-aware UTC timestamp for registry records."""
    return datetime.now(timezone.utc)


def refresh_status(agent: Agent, now: datetime) -> Agent:
    """Mark an agent offline when its heartbeat exceeds the timeout."""
    if (now - agent.last_seen).total_seconds() > OFFLINE_TIMEOUT_SECONDS:
        if agent.status != "OFFLINE":
            logger.info("Agent %s became offline", agent.agent_id)
        agent.status = "OFFLINE"
        app.state.database.update_status(agent.agent_id, "OFFLINE")
    return agent


@app.post("/api/agents/register", response_model=Agent)
def register_agent(registration: AgentRegistration, request: Request) -> Agent:
    """Register an agent or update its existing information."""
    require_agent_credential(request.headers.get("X-Agent-Token"))
    managed = app.state.database.get_managed_agent(registration.agent_id)
    if managed and not managed["enabled"]:
        audit_log(app.state.database, "agent_registration", target_agent=registration.agent_id, result="rejected", metadata={"reason": "disabled_agent"})
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Agent is disabled")
    record = app.state.database.upsert_agent(registration.model_dump(), hashlib.sha256(SERVER_CONFIG.agent_enrollment_secret.encode()).hexdigest())
    agent = Agent(**record)
    audit_log(app.state.database, "agent_registration", target_agent=agent.agent_id, metadata={"hostname": agent.hostname})
    logger.info("Agent registered: %s (%s)", agent.agent_id, agent.hostname)
    return agent


@app.post("/api/agents/{agent_id}/heartbeat", response_model=Agent)
def receive_heartbeat(agent_id: str, request: Request) -> Agent:
    """Record a heartbeat and mark the known agent online."""
    require_agent_credential(request.headers.get("X-Agent-Token"))
    record = app.state.database.heartbeat(agent_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Agent not registered")
    was_offline = record.pop("was_offline", False)
    agent = Agent(**record)
    if was_offline:
        audit_log(app.state.database, "agent_heartbeat", target_agent=agent_id, metadata={"event": "agent_reconnected"})
    logger.info("Heartbeat received from agent %s", agent_id)
    return agent


@app.get("/api/agents", response_model=list[Agent])
def list_agents(_: User = Depends(require_viewer)) -> list[Agent]:
    """Return all agents currently registered with this server."""
    now = current_time()
    return [refresh_status(Agent(**record), now) for record in app.state.database.list_agents()]


@app.get("/api/agents/{agent_id}", response_model=Agent)
def get_agent(agent_id: str, _: User = Depends(require_viewer)) -> Agent:
    """Return one registered agent with its current status."""
    record = app.state.database.get_agent(agent_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    return refresh_status(Agent(**record), current_time())


@app.get("/api/discovery", response_model=list[DiscoveredDevice])
def get_discovery_results(_: User = Depends(require_viewer)) -> list[DiscoveredDevice]:
    """Return the latest manually discovered devices."""
    with discovery_lock:
        return list(discovery_results)


@app.post("/api/discovery/scan", response_model=list[DiscoveredDevice])
def scan_network(_: User = Depends(require_viewer)) -> list[DiscoveredDevice]:
    """Run one manual local-network discovery scan."""
    results = discover_devices()
    with discovery_lock:
        discovery_results.clear()
        discovery_results.extend(results)
    audit_log(app.state.database, "discovery_scan", _.username, metadata={"devices_found": len(results)})
    return results


@app.websocket("/ws/agents/{agent_id}/screen")
async def screen_stream(websocket: WebSocket, agent_id: str) -> None:
    """
    WebSocket endpoint for live screen streaming.
    
    Can be used by:
    1. Agent to send screen frames: sends JSON {"type": "frame", "data": "<base64>"}
    2. Browser to receive frames: receives the same frame messages
    
    Only registered agents are allowed to connect.
    """
    # Check if agent is registered
    if app.state.database.get_agent(agent_id) is None:
        await websocket.close(code=4004, reason="Agent not registered")
        return
    
    await websocket.accept()
    # Role selection is followed by server-side credential validation.
    try:
        # Wait for initial handshake
        init_msg = await asyncio.wait_for(websocket.receive_json(), timeout=5)
        role = init_msg.get("role", "viewer")  # "viewer" or "source"
    except Exception as exc:
        logger.warning("Failed to receive handshake from %s: %s", agent_id, exc)
        await websocket.close(code=4000, reason="Invalid handshake")
        return

    if role == "source":
        token = websocket.headers.get("X-Agent-Token")
        if not token or not hmac.compare_digest(token, SERVER_CONFIG.agent_enrollment_secret):
            audit_log(app.state.database, "agent_authentication", target_agent=agent_id, result="failed")
            await websocket.close(code=4401, reason="Unauthorized agent")
            return
    elif role == "viewer":
        session = websocket.scope.get("session", {})
        if not app.state.auth.session_active(session.get("id")) or session.get("role") not in {"VIEWER", "OPERATOR", "ADMIN"}:
            await websocket.close(code=4401, reason="Authentication required")
            return
        audit_log(app.state.database, "screen_view_started", session.get("username"), target_agent=agent_id)
    else:
        await websocket.close(code=4000, reason="Invalid role")
        return
    logger.info("Authorized screen stream connection opened for agent %s", agent_id)
    
    if role == "source":
        # Agent is sending screen frames
        with screen_streams_lock:
            if agent_id in screen_streams:
                await websocket.close(code=4009, reason="Screen source already connected")
                return
            screen_streams[agent_id] = {
                "source_ws": websocket,
                "viewers": [],
                "latest_frame": None,
            }
        
        try:
            while True:
                try:
                    msg = await asyncio.wait_for(websocket.receive_json(), timeout=60)
                except asyncio.TimeoutError:
                    logger.info("Screen source frame receive timeout for agent %s", agent_id)
                    await websocket.close(code=1000, reason="Idle timeout")
                    return
                if not isinstance(msg, dict):
                    await websocket.close(code=4000, reason="Invalid frame message")
                    return
                frame_type = msg.get("type")
                
                if frame_type == "frame":
                    # Received screen frame from agent
                    frame_data = msg.get("data")
                    if not isinstance(frame_data, str) or len(frame_data) > 5_000_000:
                        await websocket.close(code=1009, reason="Invalid frame size")
                        return
                    
                    # Store and broadcast to all viewers
                    with screen_streams_lock:
                        stream = screen_streams.get(agent_id)
                        if stream:
                            stream["latest_frame"] = frame_data
                            # Send to all connected viewers
                            viewers_to_remove = []
                            for viewer_ws in stream["viewers"]:
                                try:
                                    await viewer_ws.send_json({"type": "frame", "data": frame_data})
                                except Exception:
                                    viewers_to_remove.append(viewer_ws)
                            
                            # Clean up disconnected viewers
                            for viewer_ws in viewers_to_remove:
                                stream["viewers"].remove(viewer_ws)
        
        except WebSocketDisconnect:
            logger.info("Screen source disconnected for agent %s", agent_id)
        except Exception as exc:
            logger.error("Screen stream error for agent %s: %s", agent_id, exc)
        finally:
            with screen_streams_lock:
                stream = screen_streams.get(agent_id)
                if stream and stream["source_ws"] is websocket:
                    # Close all viewer connections
                    for viewer_ws in stream["viewers"]:
                        try:
                            await viewer_ws.close(code=1000, reason="Source disconnected")
                        except Exception:
                            pass
                    del screen_streams[agent_id]
            logger.info("Screen stream closed for agent %s", agent_id)
    
    else:
        # Browser is viewing screen
        with screen_streams_lock:
            stream = screen_streams.get(agent_id)
            if stream is None:
                await websocket.close(code=4003, reason="No active screen source")
                return
            
            stream["viewers"].append(websocket)
            # Send latest frame if available
            if stream["latest_frame"]:
                try:
                    await websocket.send_json({"type": "frame", "data": stream["latest_frame"]})
                except Exception:
                    pass
        
        try:
            # Keep connection alive and relay frames
            while True:
                # Receive keepalive pings or control messages
                try:
                    msg = await asyncio.wait_for(websocket.receive_json(), timeout=300)
                except asyncio.TimeoutError:
                    logger.info("Screen viewer idle timeout for agent %s", agent_id)
                    await websocket.close(code=1000, reason="Idle timeout")
                    return
                if not isinstance(msg, dict):
                    await websocket.close(code=4000, reason="Invalid viewer message")
                    return
                msg_type = msg.get("type")
                
                if msg_type == "ping":
                    await websocket.send_json({"type": "pong"})
        
        except WebSocketDisconnect:
            logger.info("Screen viewer disconnected from agent %s", agent_id)
        except Exception as exc:
            logger.debug("Screen viewer error for agent %s: %s", agent_id, exc)
        finally:
            with screen_streams_lock:
                stream = screen_streams.get(agent_id)
                if stream and websocket in stream["viewers"]:
                    stream["viewers"].remove(websocket)
            audit_log(app.state.database, "screen_view_stopped", session.get("username"), target_agent=agent_id)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=SERVER_CONFIG.host, port=SERVER_CONFIG.port)
