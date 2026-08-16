"""Flask application factory for the HGRIA server."""

import logging
import queue
from typing import Any, Optional

from flask import Flask, jsonify, request
from flask_cors import CORS
from flask_socketio import SocketIO
from werkzeug.middleware.proxy_fix import ProxyFix

from backend.core.models import Session
from backend.core.state_manager import StateManager


def _silence_noisy_loggers() -> None:
    """Suppress werkzeug access log, Flask startup banner, and engine.io chatter.

    Werkzeug logs every HTTP request at INFO level — at 30 fps this floods
    the notebook output.  We keep ERROR so real server errors still surface.
    The 'flask.app' logger emits "* Serving Flask app" and "* Debug mode: off",
    which are also noise in a notebook context.
    """
    logging.getLogger("werkzeug").setLevel(logging.ERROR)
    logging.getLogger("flask.app").setLevel(logging.ERROR)
    logging.getLogger("engineio").setLevel(logging.ERROR)
    logging.getLogger("socketio").setLevel(logging.ERROR)


def create_app(
    config: Any,
    session: Session,
    state_manager: StateManager,
    command_queue: queue.Queue,
    logger: Any = None,
) -> tuple:
    """
    Create and configure the Flask application.

    Args:
        config: Configuration object
        session: Session object
        state_manager: StateManager instance
        command_queue: Queue for commands
        logger: Optional logger

    Returns:
        Tuple of (Flask app, SocketIO instance)
    """
    _silence_noisy_loggers()

    app = Flask(__name__, static_folder="../frontend", static_url_path="")

    # Enable CORS
    cors_origins = config.server.cors_origins
    CORS(app, origins=cors_origins)

    # Create SocketIO instance
    socketio = SocketIO(
        app,
        async_mode="threading",
        cors_allowed_origins=cors_origins,
        max_http_buffer_size=65536,
    )

    # Store references for routes
    app.config["HG_SESSION"] = session
    app.config["HG_CONFIG"] = config
    app.config["HG_STATE_MANAGER"] = state_manager
    app.config["HG_COMMAND_QUEUE"] = command_queue
    app.config["HG_LOGGER"] = logger

    # Apply ProxyFix for ngrok (reverse proxy)
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    # Register blueprints
    from backend.routes.health import health_bp
    from backend.routes.config_api import config_bp
    from backend.routes.session import session_bp

    app.register_blueprint(health_bp)
    app.register_blueprint(config_bp)
    app.register_blueprint(session_bp)

    # Register frame endpoint for Colab mode
    @app.route("/api/frame", methods=["POST"])
    def receive_frame():
        """Receive base64 JPEG frame from browser (Colab mode)."""
        if not config.camera.colab_mode:
            return "", 204

        data = request.get_json(silent=True) or {}
        b64 = data.get("image", "")
        if not b64:
            return jsonify({"error": "Missing image data"}), 400

        try:
            import base64
            import cv2
            import numpy as np
            from backend.pipeline.camera import FrameStore

            # Decode base64 JPEG → numpy BGR
            jpg_bytes = base64.b64decode(b64.split(",")[-1])
            arr = np.frombuffer(jpg_bytes, dtype=np.uint8)
            bgr = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            if bgr is not None:
                FrameStore().put(bgr)
            return "", 204
        except Exception as e:
            if logger:
                logger.error("frame_decode_error", error=str(e), module="frame_endpoint")
            return jsonify({"error": "Failed to decode frame"}), 400

    # Register WebSocket handlers
    from backend.websocket.handlers import register_handlers
    register_handlers(socketio, session, state_manager, config)

    # Start command transmitter drain loop in background thread
    from backend.pipeline.commander import CommandTransmitter
    transmitter = CommandTransmitter(socketio, command_queue, logger)
    socketio.start_background_task(transmitter.start)

    # Security headers
    @app.after_request
    def add_security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self' https://cdn.socket.io; "
            "style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
            "connect-src 'self' https://*.ngrok-free.app wss://*.ngrok-free.app https://*; worker-src 'self'"
        )
        return response

    # Input sanitisation middleware
    @app.before_request
    def sanitise_request():
        """Sanitise incoming request data."""
        if request.content_type == "application/json":
            data = request.get_json(silent=True) or {}
            for key, val in data.items():
                if isinstance(val, str) and len(val) > 512:
                    return jsonify({
                        "error": {
                            "code": "INPUT_TOO_LONG",
                            "field": key,
                            "message": "String values must be 512 characters or less"
                        }
                    }), 400

    return app, socketio
