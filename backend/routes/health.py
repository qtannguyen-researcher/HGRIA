"""Health check endpoint."""

from flask import Blueprint, current_app, jsonify


health_bp = Blueprint("health", __name__)


@health_bp.route("/health", methods=["GET"])
def health_check():
    """Health check endpoint returning server status."""
    state_manager = current_app.config.get("HG_STATE_MANAGER")
    state = state_manager.state.value if state_manager else "unknown"

    return jsonify({
        "status": "ok",
        "version": "1.0.0",
        "pipeline_state": state,
    }), 200
