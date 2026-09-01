"""Screen capture and compression for remote viewing."""

import base64
import io
import logging
import os
from dataclasses import dataclass

from PIL import Image, ImageGrab

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ScreenCaptureConfig:
    """Configuration for screen capture behavior."""

    capture_interval: float = 0.5  # seconds between captures (2 FPS)
    image_quality: int = 70  # JPEG quality (1-95)
    max_width: int = 1920  # maximum screen width to capture
    max_height: int = 1080  # maximum screen height to capture
    max_frame_rate: float = 2.0  # maximum frames per second

    @classmethod
    def from_environment(cls) -> "ScreenCaptureConfig":
        """Build configuration from environment variables."""
        return cls(
            capture_interval=float(
                os.getenv("LAB_SCREEN_CAPTURE_INTERVAL", str(cls.capture_interval))
            ),
            image_quality=int(
                os.getenv("LAB_SCREEN_IMAGE_QUALITY", str(cls.image_quality))
            ),
            max_width=int(
                os.getenv("LAB_SCREEN_MAX_WIDTH", str(cls.max_width))
            ),
            max_height=int(
                os.getenv("LAB_SCREEN_MAX_HEIGHT", str(cls.max_height))
            ),
            max_frame_rate=float(
                os.getenv("LAB_SCREEN_MAX_FRAME_RATE", str(cls.max_frame_rate))
            ),
        )


def capture_screen() -> bytes | None:
    """
    Capture the current screen and return as JPEG bytes.
    
    Returns:
        Compressed JPEG image as bytes, or None if capture fails.
    """
    try:
        # Capture the screen
        screenshot = ImageGrab.grab()
        
        # Resize if necessary
        config = ScreenCaptureConfig.from_environment()
        if screenshot.width > config.max_width or screenshot.height > config.max_height:
            screenshot.thumbnail((config.max_width, config.max_height), Image.Resampling.LANCZOS)
        
        # Compress to JPEG
        buffer = io.BytesIO()
        screenshot.save(buffer, format="JPEG", quality=config.image_quality, optimize=True)
        return buffer.getvalue()
    except Exception as exc:
        logger.error("Failed to capture screen: %s", exc)
        return None


def encode_frame(image_bytes: bytes) -> str:
    """Encode image bytes as base64 for transmission."""
    return base64.b64encode(image_bytes).decode("utf-8")


def decode_frame(encoded: str) -> bytes:
    """Decode base64-encoded frame back to image bytes."""
    return base64.b64decode(encoded)
