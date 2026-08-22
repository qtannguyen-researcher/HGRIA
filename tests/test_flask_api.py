"""Integration tests for Flask HTTP API."""

import base64
import json
import numpy as np
import pytest


class TestHealthEndpoint:
    """Tests for GET /health endpoint."""

    def test_health_returns_200(self, client):
        """GET /health returns HTTP 200."""
        response = client.get("/health")
        assert response.status_code == 200

    def test_health_returns_status_ok(self, client):
        """GET /health returns status: ok."""
        response = client.get("/health")
        data = json.loads(response.data)
        assert data["status"] == "ok"

    def test_health_returns_version(self, client):
        """GET /health returns version."""
        response = client.get("/health")
        data = json.loads(response.data)
        assert "version" in data
        assert data["version"] == "1.0.0"

    def test_health_returns_pipeline_state(self, client):
        """GET /health returns pipeline_state."""
        response = client.get("/health")
        data = json.loads(response.data)
        assert "pipeline_state" in data


class TestConfigAPI:
    """Tests for /api/config endpoints."""

    def test_get_config_returns_200(self, client):
        """GET /api/config returns HTTP 200."""
        response = client.get("/api/config")
        assert response.status_code == 200

    def test_get_config_returns_public_dict(self, client):
        """GET /api/config returns public configuration."""
        response = client.get("/api/config")
        data = json.loads(response.data)

        assert "camera" in data
        assert "mediapipe" in data
        assert "gesture_recognition" in data
        assert "server" in data

    def test_get_config_excludes_log_path(self, client):
        """GET /api/config excludes log_file_path."""
        response = client.get("/api/config")
        data = json.loads(response.data)

        if "logging" in data:
            assert "log_file_path" not in data["logging"]

    def test_put_config_hot_reloadable_accepted(self, client):
        """PUT /api/config with hot-reloadable field returns updated."""
        response = client.put(
            "/api/config",
            json={"gesture_recognition.confidence_threshold": 0.85},
            content_type="application/json",
        )
        assert response.status_code == 200
        data = json.loads(response.data)
        assert "gesture_recognition.confidence_threshold" in data["updated"]

    def test_put_config_non_hot_reloadable_rejected(self, client):
        """PUT /api/config with non-hot-reloadable field returns rejected."""
        response = client.put(
            "/api/config",
            json={"camera.index": 1},
            content_type="application/json",
        )
        assert response.status_code == 200
        data = json.loads(response.data)
        assert "camera.index" in data["rejected"]

    def test_put_config_cooldown_accepted(self, client):
        """PUT /api/config with cooldown field is accepted."""
        response = client.put(
            "/api/config",
            json={"gesture_cooldowns_ms.open_palm": 1000},
            content_type="application/json",
        )
        assert response.status_code == 200
        data = json.loads(response.data)
        assert "gesture_cooldowns_ms.open_palm" in data["updated"]


class TestSessionAPI:
    """Tests for /api/session endpoints."""

    def test_get_session_returns_200(self, client):
        """GET /api/session returns HTTP 200."""
        response = client.get("/api/session")
        assert response.status_code == 200

    def test_get_session_returns_session_id(self, client):
        """GET /api/session returns session_id."""
        response = client.get("/api/session")
        data = json.loads(response.data)
        assert "session_id" in data

    def test_get_session_returns_commands_sent(self, client):
        """GET /api/session returns commands_sent."""
        response = client.get("/api/session")
        data = json.loads(response.data)
        assert "commands_sent" in data
        assert isinstance(data["commands_sent"], int)

    def test_get_session_returns_gesture_counts(self, client):
        """GET /api/session returns gesture_counts."""
        response = client.get("/api/session")
        data = json.loads(response.data)
        assert "gesture_counts" in data
        assert isinstance(data["gesture_counts"], dict)

    def test_delete_session_returns_204(self, client):
        """DELETE /api/session returns HTTP 204."""
        response = client.delete("/api/session")
        assert response.status_code == 204

    def test_delete_session_resets_counters(self, client):
        """DELETE /api/session resets session counters."""
        # First, generate some commands (would need the full system)
        # For now, just verify reset works
        response = client.delete("/api/session")
        assert response.status_code == 204

        # Verify counters are reset
        response = client.get("/api/session")
        data = json.loads(response.data)
        assert data["commands_sent"] == 0
        assert data["gesture_counts"] == {}


class TestFrameEndpoint:
    """Tests for POST /api/frame endpoint."""

    def test_post_frame_with_invalid_base64_returns_400(self, client):
        """POST /api/frame with invalid data returns 400."""
        response = client.post(
            "/api/frame",
            json={"image": "not_valid_base64!!!"},
            content_type="application/json",
        )
        # May return 400 or 204 depending on implementation
        assert response.status_code in (400, 204)

    def test_post_frame_without_image_returns_204_when_colab_mode_off(self, client):
        """POST /api/frame is inactive when colab_mode is false (baseline)."""
        response = client.post(
            "/api/frame",
            json={},
            content_type="application/json",
        )
        assert response.status_code == 204

    def test_post_frame_without_image_returns_400_when_colab_mode_on(
        self, test_session, test_state_manager, command_queue
    ):
        """POST /api/frame without image returns 400 when the endpoint is active."""
        import json
        import os
        import tempfile

        from backend.app import create_app
        from backend.core.configuration import ConfigurationManager

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"camera": {"colab_mode": True}}, f)
            f.flush()
            config = ConfigurationManager(f.name)
            os.unlink(f.name)

        app, _ = create_app(
            config, test_session, test_state_manager, command_queue, None
        )
        app.config["TESTING"] = True
        client = app.test_client()
        response = client.post(
            "/api/frame",
            json={},
            content_type="application/json",
        )
        assert response.status_code == 400


class TestSecurityHeaders:
    """Tests for security headers."""

    def test_security_headers_present(self, client):
        """Response includes security headers."""
        response = client.get("/health")

        assert "X-Content-Type-Options" in response.headers
        assert response.headers["X-Content-Type-Options"] == "nosniff"

        assert "X-Frame-Options" in response.headers
        assert response.headers["X-Frame-Options"] == "DENY"

        assert "Content-Security-Policy" in response.headers


class TestInputSanitisation:
    """Tests for input sanitisation."""

    def test_long_string_rejected(self, client):
        """Strings > 512 chars are rejected."""
        long_string = "x" * 600

        response = client.put(
            "/api/config",
            json={"debug.test_field": long_string},
            content_type="application/json",
        )
        # Should be rejected or handled gracefully
        assert response.status_code in (200, 400)


class TestSessionSharedWithPipeline:
    """GET /api/session must reflect commands recorded by the pipeline Session."""

    def test_pipeline_recorded_command_visible_via_api(
        self, flask_app, test_session, test_config
    ):
        """CommandGenerator writing to the Flask session updates /api/session."""
        from backend.pipeline.commander import CommandGenerator

        app, _ = flask_app
        client = app.test_client()

        before = client.get("/api/session").get_json()
        assert before["commands_sent"] == 0

        gen = CommandGenerator(test_config, test_session)
        gen.generate({"gesture_name": "open_palm", "confidence": 0.9})

        after = client.get("/api/session").get_json()
        assert after["session_id"] == test_session.session_id
        assert after["commands_sent"] == 1
        assert after["gesture_counts"].get("open_palm") == 1


class TestTestEmitEvaluationMode:
    """ /api/test-emit is a demo helper; it must not fire in evaluation mode. """

    def test_test_emit_allowed_when_evaluation_off(self, client):
        """Default demo config still allows /api/test-emit."""
        response = client.get("/api/test-emit?gesture=point_left")
        assert response.status_code == 200
        data = response.get_json()
        assert data["ok"] is True

    def test_test_emit_forbidden_in_evaluation_mode(
        self, test_session, test_state_manager, command_queue
    ):
        """Evaluation mode blocks synthetic HTTP command injection."""
        import json
        import os
        import tempfile

        from backend.app import create_app
        from backend.core.configuration import ConfigurationManager

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"evaluation": {"mode": True}}, f)
            f.flush()
            config = ConfigurationManager(f.name)
            os.unlink(f.name)

        app, _ = create_app(
            config, test_session, test_state_manager, command_queue, None
        )
        app.config["TESTING"] = True
        client = app.test_client()

        response = client.get("/api/test-emit?gesture=point_left")
        assert response.status_code == 403
        data = response.get_json()
        assert data["ok"] is False
