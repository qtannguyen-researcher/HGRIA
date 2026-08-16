"""Command generator and transmitter for the HGRIA system."""

import queue
import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from backend.core.errors import UnmappedGestureError
from backend.core.models import Command, Session


# Gesture → Command mapping
# Includes both static (MediaPipe-based) and dynamic (OC-SORT + ONNX) gestures.
COMMAND_MAP: Dict[str, Dict[str, Any]] = {
    # ── Static gestures ────────────────────────────────────────────────────
    "open_palm":   {"command_type": "MOVE",   "command_value": {"direction": "stop"}},
    "closed_fist": {"command_type": "ACTION", "command_value": {"action": "speed_boost"}},
    "point_left":  {"command_type": "MOVE",   "command_value": {"direction": "left"}},
    "point_right": {"command_type": "MOVE",   "command_value": {"direction": "right"}},
    "thumb_up":    {"command_type": "ACTION", "command_value": {"action": "jump"}},
    "victory":     {"command_type": "UI",     "command_value": {"action": "select"}},
    "stop":        {"command_type": "SYSTEM", "command_value": {"action": "pause"}},
    "pinch":       {"command_type": "UI",     "command_value": {"action": "zoom_in"}},
    "ok":          {"command_type": "UI",     "command_value": {"action": "confirm"}},

    # ── Dynamic gestures: single-finger swipes ──────────────────────────────
    "SWIPE_LEFT":        {"command_type": "MOVE",   "command_value": {"direction": "left"}},
    "SWIPE_RIGHT":       {"command_type": "MOVE",   "command_value": {"direction": "right"}},
    "SWIPE_UP":          {"command_type": "MOVE",   "command_value": {"direction": "up"}},
    "SWIPE_DOWN":        {"command_type": "MOVE",   "command_value": {"direction": "down"}},

    # ── Dynamic gestures: two-finger swipes (thumb variant) ────────────────
    "SWIPE_LEFT2":       {"command_type": "MOVE",   "command_value": {"direction": "left",  "fingers": 2}},
    "SWIPE_RIGHT2":      {"command_type": "MOVE",   "command_value": {"direction": "right", "fingers": 2}},
    "SWIPE_UP2":         {"command_type": "MOVE",   "command_value": {"direction": "up",    "fingers": 2}},
    "SWIPE_DOWN2":       {"command_type": "MOVE",   "command_value": {"direction": "down",  "fingers": 2}},

    # ── Dynamic gestures: three-finger swipes ──────────────────────────────
    "SWIPE_LEFT3":       {"command_type": "MOVE",   "command_value": {"direction": "left",  "fingers": 3}},
    "SWIPE_RIGHT3":      {"command_type": "MOVE",   "command_value": {"direction": "right", "fingers": 3}},
    "SWIPE_UP3":         {"command_type": "MOVE",   "command_value": {"direction": "up",    "fingers": 3}},
    "SWIPE_DOWN3":       {"command_type": "MOVE",   "command_value": {"direction": "down",  "fingers": 3}},

    # ── Dynamic gestures: fast swipes ──────────────────────────────────────
    "FAST_SWIPE_UP":     {"command_type": "ACTION", "command_value": {"action": "fast_up"}},
    "FAST_SWIPE_DOWN":   {"command_type": "ACTION", "command_value": {"action": "fast_down"}},

    # ── Dynamic gestures: zoom ──────────────────────────────────────────────
    "ZOOM_IN":           {"command_type": "UI",     "command_value": {"action": "zoom_in"}},
    "ZOOM_OUT":          {"command_type": "UI",     "command_value": {"action": "zoom_out"}},

    # ── Dynamic gestures: drag & drop ──────────────────────────────────────
    "DRAG":              {"command_type": "ACTION", "command_value": {"action": "drag"}},
    "DROP":              {"command_type": "ACTION", "command_value": {"action": "drop"}},
    "DRAG2":             {"command_type": "ACTION", "command_value": {"action": "drag",  "variant": 2}},
    "DROP2":             {"command_type": "ACTION", "command_value": {"action": "drop",  "variant": 2}},
    "DRAG3":             {"command_type": "ACTION", "command_value": {"action": "drag",  "variant": 3}},
    "DROP3":             {"command_type": "ACTION", "command_value": {"action": "drop",  "variant": 3}},

    # ── Dynamic gestures: tap ───────────────────────────────────────────────
    "TAP":               {"command_type": "UI",     "command_value": {"action": "tap"}},
    "DOUBLE_TAP":        {"command_type": "UI",     "command_value": {"action": "double_tap"}},
}


class CommandGenerator:
    """Generates Command objects from gesture predictions."""

    def __init__(self, config: Any, session: Session) -> None:
        """
        Initialize the command generator.

        Args:
            config: Configuration object with custom_gestures
            session: Session object for tracking
        """
        self._map: Dict[str, Dict[str, Any]] = {**COMMAND_MAP}

        # Merge custom gestures from config
        for cg in config.custom_gestures:
            self._map[cg["name"]] = {
                "command_type": cg["command_type"],
                "command_value": cg["command_value"],
            }
        self._session = session

    def generate(self, partial: Dict[str, Any]) -> Command:
        """
        Generate a Command from a partial prediction dict.

        Args:
            partial: Dict with gesture_name and confidence

        Returns:
            Full Command object

        Raises:
            UnmappedGestureError: If gesture is not in the command map
        """
        gesture = partial["gesture_name"]
        if gesture not in self._map:
            raise UnmappedGestureError(f"Unknown gesture: {gesture}")

        mapping = self._map[gesture]
        cmd = Command(
            session_id=self._session.session_id,
            gesture_name=gesture,
            command_type=mapping["command_type"],
            command_value=mapping["command_value"],
            confidence=partial["confidence"],
        )

        # Record in session
        self._session.record_command(cmd)

        return cmd


class CommandTransmitter:
    """Transmits commands from the queue to connected WebSocket clients."""

    BUFFER_SIZE = 10
    BUFFER_TTL_SECONDS = 5.0

    def __init__(self, socketio: Any, command_queue: queue.Queue, logger: Any = None) -> None:
        """
        Initialize the command transmitter.

        Args:
            socketio: Flask-SocketIO instance
            command_queue: Queue of Command objects
            logger: Optional logger
        """
        self._sio = socketio
        self._queue = command_queue
        self._logger = logger
        self._buffer: List[tuple] = []  # List of (timestamp, Command)
        self._running = True
        self._thread: Optional[threading.Thread] = None
        self._connected = False

    def start(self) -> None:
        """Start the transmitter background thread."""
        self._running = True
        self._thread = threading.Thread(target=self._drain_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Stop the transmitter background thread."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)

    def _drain_loop(self) -> None:
        """Background loop that drains the command queue."""
        while self._running:
            try:
                cmd: Command = self._queue.get(timeout=0.05)
                self._transmit(cmd)
                self._queue.task_done()
            except queue.Empty:
                self._cleanup_buffer()
                continue

    def _transmit(self, cmd: Command) -> None:
        """Transmit a command via SocketIO."""
        cmd.transmitted_at = datetime.now(timezone.utc)

        # Calculate latency if possible
        latency_ms = None
        if cmd.timestamp:
            latency_ms = (cmd.transmitted_at - cmd.timestamp).total_seconds() * 1000

        if self._logger:
            self._logger.debug(
                "command_transmitted",
                command_id=cmd.command_id,
                gesture_name=cmd.gesture_name,
                latency_ms=round(latency_ms, 2) if latency_ms else None,
                module="command_transmitter"
            )

        self._sio.emit("gesture_command", cmd.to_dict())

    def _cleanup_buffer(self) -> None:
        """Remove expired commands from the buffer."""
        now = time.monotonic()
        self._buffer = [
            (ts, cmd) for ts, cmd in self._buffer
            if now - ts < self.BUFFER_TTL_SECONDS
        ]

    def on_connect(self) -> None:
        """Called when a client connects."""
        self._connected = True
        # Flush buffered commands to new client
        for _, cmd in self._buffer:
            self._transmit(cmd)
        self._buffer.clear()

    def on_disconnect(self) -> None:
        """Called when a client disconnects."""
        self._connected = False

    def set_connected(self, connected: bool) -> None:
        """Set connection state."""
        self._connected = connected
