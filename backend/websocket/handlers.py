"""WebSocket event handlers for the HGRIA system."""

from typing import Any


def register_handlers(
    sio: Any,
    session: Any,
    state_manager: Any,
    config: Any,
) -> None:
    """
    Register all SocketIO event handlers.

    Args:
        sio: Flask-SocketIO instance
        session: Session object
        state_manager: StateManager instance
        config: Configuration object
    """

    @sio.on("connect")
    def on_connect():
        """Handle client connection."""
        sio.emit("server_info", {
            "session_id": session.session_id,
            "version": "1.0.0",
            "config": config.public_dict(),
        })
        state_manager.transition("client_connected")

    @sio.on("disconnect")
    def on_disconnect():
        """Handle client disconnection."""
        state_manager.transition("client_disconnected")

    @sio.on("client_ready")
    def on_client_ready(data: dict):
        """Handle client ready event with payload validation."""
        allowed_keys = {"client_id", "user_agent"}
        if not isinstance(data, dict):
            return
        if not set(data.keys()).issubset(allowed_keys):
            return  # silently ignore malformed events

    @sio.on("pause_pipeline")
    def on_pause_pipeline():
        """Handle pause pipeline event."""
        state_manager.transition("stop_gesture")

    @sio.on("resume_pipeline")
    def on_resume_pipeline():
        """Handle resume pipeline event (toggle pause)."""
        state_manager.transition("stop_gesture")

    @sio.on("ping")
    def on_ping(data: dict):
        """Handle ping event and respond with pong."""
        timestamp = data.get("timestamp") if isinstance(data, dict) else None
        sio.emit("pong", {"timestamp": timestamp})
