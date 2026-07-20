"""Configuration API endpoints."""

from flask import Blueprint, current_app, jsonify, request

from backend.core.configuration import HOT_RELOAD_FIELDS


config_bp = Blueprint("config_api", __name__, url_prefix="/api")


@config_bp.route("/config", methods=["GET"])
def get_config():
    """Get public configuration (without sensitive fields)."""
    config = current_app.config.get("HG_CONFIG")
    if config is None:
        return jsonify({"error": "Configuration not available"}), 500

    return jsonify(config.public_dict()), 200


@config_bp.route("/config", methods=["PUT"])
def update_config():
    """Update hot-reloadable configuration fields."""
    config = current_app.config.get("HG_CONFIG")
    if config is None:
        return jsonify({"error": "Configuration not available"}), 500

    data = request.get_json(silent=True) or {}
    updated = []
    rejected = []

    for field, value in data.items():
        # Check if it's a hot-reloadable field
        is_hot_reloadable = (
            field in HOT_RELOAD_FIELDS or
            field.startswith("gesture_cooldowns_ms.")
        )

        if is_hot_reloadable:
            if config.update(field, value):
                updated.append(field)
            else:
                rejected.append(field)
        else:
            rejected.append(field)

    return jsonify({
        "updated": updated,
        "rejected": rejected,
    }), 200
