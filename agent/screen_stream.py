"""WebSocket client for streaming screen frames to the server."""

import asyncio
import json
import logging
import time
from urllib.parse import quote, urlsplit, urlunsplit

import websockets

from agent.screen_capture import ScreenCaptureConfig, capture_screen, encode_frame

logger = logging.getLogger(__name__)


def screen_websocket_url(server_url: str, agent_id: str) -> str:
    """Build the agent screen-stream endpoint from an HTTP(S) server URL."""
    parsed = urlsplit(server_url.strip())
    websocket_scheme = {"http": "ws", "https": "wss"}.get(parsed.scheme)
    if websocket_scheme is None or not parsed.netloc:
        raise ValueError("LAB_SERVER_URL must be an absolute http:// or https:// URL")

    base_path = parsed.path.rstrip("/")
    stream_path = f"{base_path}/ws/agents/{quote(agent_id, safe='')}/screen"
    return urlunsplit((websocket_scheme, parsed.netloc, stream_path, "", ""))


async def stream_screen(server_url: str, agent_id: str, enrollment_secret: str) -> None:
    """
    Connect to the server and continuously send screen frames via WebSocket.
    
    Args:
        server_url: Base server URL (e.g., "http://127.0.0.1:8000")
        agent_id: The agent's unique ID
    """
    config = ScreenCaptureConfig.from_environment()
    
    ws_url = screen_websocket_url(server_url, agent_id)
    
    last_frame_time = 0
    min_frame_interval = 1.0 / config.max_frame_rate
    
    while True:
        try:
            logger.info("Connecting to screen stream: %s", ws_url)
            if not enrollment_secret:
                raise ValueError("LAB_AGENT_ENROLLMENT_SECRET is not configured")
            async with websockets.connect(ws_url, extra_headers={"X-Agent-Token": enrollment_secret}) as websocket:
                # Send handshake identifying as source
                await websocket.send(json.dumps({"role": "source"}))
                logger.info("Screen stream connected for agent %s", agent_id)
                
                # Stream screen frames
                while True:
                    now = time.time()
                    elapsed = now - last_frame_time
                    
                    # Respect max frame rate
                    if elapsed < min_frame_interval:
                        await asyncio.sleep(min_frame_interval - elapsed)
                        now = time.time()
                    
                    # Capture screen
                    frame_bytes = capture_screen()
                    if frame_bytes:
                        encoded = encode_frame(frame_bytes)
                        await websocket.send(json.dumps({"type": "frame", "data": encoded}))
                        last_frame_time = time.time()
                    
                    # Respect capture interval
                    await asyncio.sleep(config.capture_interval)
        
        except websockets.exceptions.WebSocketException as exc:
            logger.warning("WebSocket connection failed: %s; will retry", exc)
            await asyncio.sleep(5)
        except Exception as exc:
            logger.error("Unexpected error in screen stream: %s; will retry", exc)
            await asyncio.sleep(5)


def run_screen_stream(server_url: str, agent_id: str, enrollment_secret: str) -> None:
    """
    Run the screen streaming loop in the asyncio event loop.
    
    This is a wrapper for use with threading or direct invocation.
    """
    asyncio.run(stream_screen(server_url, agent_id, enrollment_secret))
