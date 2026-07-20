"""Session management endpoints."""

from flask import Blueprint, current_app, jsonify

from backend.core.models import Session


session_bp = Blueprint("session", __name__, url_prefix="/api")


@session_bp.route("/session", methods=["GET"])
def get_session():
    """Get session metadata."""
    session: Session = current_app.config.get("HG_SESSION")
    if session is None:
        return jsonify({"error": "Session not available"}), 500

    return jsonify({
        "session_id": session.session_id,
        "commands_sent": session.commands_sent,
        "gesture_counts": session.gesture_counts,
        "avg_latency_ms": session.avg_latency_ms,
    }), 200


@session_bp.route("/session", methods=["DELETE"])
def reset_session():
    """Reset session counters."""
    session: Session = current_app.config.get("HG_SESSION")
    if session is None:
        return jsonify({"error": "Session not available"}), 500

    session.commands_sent = 0
    session.gesture_counts = {}
    session.avg_latency_ms = 0.0

    return "", 204
