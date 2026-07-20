"""Custom exception hierarchy and error handler for the HGRIA system."""

import traceback
from typing import Any, Optional


class HGRIAError(Exception):
    """Base exception for all HGRIA system errors."""


class CameraInitializationError(HGRIAError):
    """Raised when the camera cannot be opened within the timeout."""


class ServerStartupError(HGRIAError):
    """Raised when Flask cannot bind to any port after retries."""


class UnmappedGestureError(HGRIAError):
    """Raised by CommandGenerator for gestures not in COMMAND_MAP."""


class ConfigurationError(HGRIAError):
    """Raised when required configuration is missing and has no default."""


class InvalidStateTransitionError(HGRIAError):
    """Raised when an invalid state transition is attempted."""


class MediaPipeError(HGRIAError):
    """Raised when MediaPipe inference raises an unexpected exception."""


class ErrorHandler:
    """Centralized error handler for the HGRIA system."""

    def __init__(self, logger: Any, socketio: Any, state_manager: Any) -> None:
        """
        Initialize the error handler.

        Args:
            logger: StructuredLogger instance
            socketio: Flask-SocketIO instance
            state_manager: StateManager instance
        """
        self._log = logger
        self._sio = socketio
        self._sm = state_manager

    def handle(self, exc: Exception) -> None:
        """
        Handle an exception by classifying it and taking appropriate action.

        Args:
            exc: The exception to handle
        """
        if isinstance(exc, CameraInitializationError):
            self._recoverable(
                exc, "camera_unavailable",
                "Camera feed lost. Reconnecting..."
            )
        elif isinstance(exc, MediaPipeError):
            self._recoverable(
                exc, "mediapipe_error",
                "AI model error — reinitializing"
            )
        elif isinstance(exc, UnmappedGestureError):
            self._log.warning(
                "unmapped_gesture",
                gesture=str(exc),
                module="error_handler"
            )
        elif isinstance(exc, InvalidStateTransitionError):
            self._log.warning(
                "invalid_state_transition",
                error=str(exc),
                module="error_handler"
            )
        else:
            self._non_recoverable(exc)

    def _recoverable(self, exc: Exception, code: str, user_msg: str) -> None:
        """Handle a recoverable error by logging and emitting to client."""
        tb = traceback.format_exc()
        self._log.error(
            code,
            error=str(exc),
            traceback=tb,
            module="error_handler"
        )
        if self._sio:
            self._sio.emit("system_error", {
                "error_code": code,
                "message": user_msg,
                "recoverable": True
            })

    def _non_recoverable(self, exc: Exception) -> None:
        """Handle a non-recoverable error by logging, emitting, and shutting down."""
        tb = traceback.format_exc()
        state = self._sm.state if self._sm else "unknown"
        self._log.critical(
            "unhandled_exception",
            error=str(exc),
            traceback=tb,
            state=state,
            module="error_handler"
        )
        if self._sio:
            self._sio.emit("system_error", {
                "error_code": "FATAL",
                "message": "Server error — session ended",
                "recoverable": False
            })
        if self._sm:
            self._sm.transition("shutdown")
