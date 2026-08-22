"""Tests for ConfigurationManager."""

import json
import os
import tempfile

import pytest

from backend.core.configuration import (
    DEFAULTS,
    ConfigurationManager,
    SCHEMA,
)


class TestConfigurationManager:
    """Tests for the configuration manager."""

    def test_missing_file_falls_back_to_defaults(self):
        """Missing config.json uses DEFAULTS."""
        cm = ConfigurationManager("/nonexistent/path/config.json")

        assert cm.camera.index == DEFAULTS["camera"]["index"]
        assert cm.camera.frame_width == DEFAULTS["camera"]["frame_width"]

    def test_out_of_range_value_replaced_with_default(self):
        """Out-of-range values are replaced with defaults."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({
                "camera": {
                    "index": 999,  # Out of range (0-9)
                    "frame_width": 9999,  # Out of range (160-1920)
                },
                "mediapipe": {
                    "min_detection_confidence": 9.9,  # Out of range (0.5-1.0)
                },
            }, f)
            f.flush()

            cm = ConfigurationManager(f.name)
            assert cm.camera.index == DEFAULTS["camera"]["index"]
            assert cm.camera.frame_width == DEFAULTS["camera"]["frame_width"]
            assert cm.mediapipe.min_detection_confidence == DEFAULTS["mediapipe"]["min_detection_confidence"]

            os.unlink(f.name)

    def test_valid_values_preserved(self):
        """Valid config values are preserved."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({
                "camera": {
                    "index": 1,
                    "frame_width": 1280,
                },
            }, f)
            f.flush()

            cm = ConfigurationManager(f.name)
            assert cm.camera.index == 1
            assert cm.camera.frame_width == 1280

            os.unlink(f.name)

    def test_deep_merge_nested_dicts(self):
        """Partial overrides merge deeply."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({
                "camera": {
                    "index": 2,
                    # frame_width omitted, should use default
                },
            }, f)
            f.flush()

            cm = ConfigurationManager(f.name)
            assert cm.camera.index == 2
            assert cm.camera.frame_width == DEFAULTS["camera"]["frame_width"]

            os.unlink(f.name)

    def test_env_var_override(self, monkeypatch):
        """Environment variables with HGRIA_ prefix override config."""
        monkeypatch.setenv("HGRIA_CAMERA_INDEX", "5")
        monkeypatch.setenv("HGRIA_LOGGING_LEVEL", "DEBUG")

        cm = ConfigurationManager()

        assert cm.camera.index == 5
        # Note: env vars are applied at init time

    def test_hot_reload_fields_updated(self):
        """update() modifies hot-reloadable fields."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({}, f)
            f.flush()

            cm = ConfigurationManager(f.name)

            result = cm.update("gesture_recognition.confidence_threshold", 0.85)
            assert result is True
            assert cm.gesture_recognition.confidence_threshold == 0.85

            os.unlink(f.name)

    def test_non_hot_reload_rejected(self):
        """update() rejects non-hot-reloadable fields."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({}, f)
            f.flush()

            cm = ConfigurationManager(f.name)

            result = cm.update("camera.index", 3)
            assert result is False

            os.unlink(f.name)

    def test_gesture_cooldowns_hot_reload(self):
        """Cooldown fields are hot-reloadable."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({}, f)
            f.flush()

            cm = ConfigurationManager(f.name)

            result = cm.update("gesture_cooldowns_ms.open_palm", 1000)
            assert result is True

            os.unlink(f.name)

    def test_public_dict_removes_sensitive_fields(self):
        """public_dict() removes log_file_path."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({}, f)
            f.flush()

            cm = ConfigurationManager(f.name)
            public = cm.public_dict()

            assert "log_file_path" not in public.get("logging", {})

            os.unlink(f.name)

    def test_attribute_access(self):
        """Nested attributes are accessible."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({}, f)
            f.flush()

            cm = ConfigurationManager(f.name)

            assert hasattr(cm, "camera")
            assert hasattr(cm.camera, "index")
            assert hasattr(cm, "mediapipe")
            assert hasattr(cm, "gesture_recognition")

            os.unlink(f.name)


class TestBaselineConfiguration:
    """config.json is the experiment source of truth; DEFAULTS must not drift."""

    def test_dynamic_gestures_disabled_in_committed_config(self):
        """Baseline freezes the static path: dynamic_gestures.enabled is false."""
        cm = ConfigurationManager("config/config.json")
        assert cm.dynamic_gestures.enabled is False
        assert cm.is_dynamic_gestures_enabled() is False

    def test_dynamic_enabled_flag_not_section_presence(self):
        """Section presence must not enable the dynamic path."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"dynamic_gestures": {"enabled": False}}, f)
            f.flush()
            cm = ConfigurationManager(f.name)
            os.unlink(f.name)
        assert cm.is_dynamic_gestures_enabled() is False

    def test_dynamic_enabled_true_is_respected(self):
        """enabled=true is still readable without changing dynamic implementation."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"dynamic_gestures": {"enabled": True}}, f)
            f.flush()
            cm = ConfigurationManager(f.name)
            os.unlink(f.name)
        assert cm.is_dynamic_gestures_enabled() is True

    def test_baseline_fields_match_config_and_defaults(self):
        """Committed config and DEFAULTS agree on baseline-critical fields."""
        cm = ConfigurationManager("config/config.json")
        assert cm.mediapipe.min_detection_confidence == 0.5
        assert DEFAULTS["mediapipe"]["min_detection_confidence"] == 0.5
        assert cm.gesture_recognition.smoothing_window_size == 3
        assert DEFAULTS["gesture_recognition"]["smoothing_window_size"] == 3
        assert cm.gesture_recognition.noise_filter_blur_threshold == 30
        assert DEFAULTS["gesture_recognition"]["noise_filter_blur_threshold"] == 30
        assert cm.logging.log_file_path == "logs/"
        assert DEFAULTS["logging"]["log_file_path"] == "logs/"
        assert DEFAULTS["dynamic_gestures"]["enabled"] is False

    def test_evaluation_mode_default_off(self):
        """Demo/dev default is evaluation.mode=false."""
        cm = ConfigurationManager("config/config.json")
        assert cm.evaluation.mode is False
        assert cm.is_evaluation_mode() is False

    def test_evaluation_mode_true(self):
        """evaluation.mode=true is readable for eval runs."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"evaluation": {"mode": True}}, f)
            f.flush()
            cm = ConfigurationManager(f.name)
            os.unlink(f.name)
        assert cm.is_evaluation_mode() is True


# ===== Property 7: Configuration validation =====

class TestConfigurationValidation:
    """Property 7: Config validation completeness."""

    def test_schema_fields_all_have_defaults(self):
        """Every schema field has a corresponding default."""
        for dotted in SCHEMA.keys():
            section, param = dotted.split(".", 1)
            assert section in DEFAULTS
            assert param in DEFAULTS[section]

    def test_invalid_type_rejected(self):
        """Wrong type is replaced with default."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({
                "camera": {
                    "index": "not_an_int",  # Should be int
                },
            }, f)
            f.flush()

            cm = ConfigurationManager(f.name)
            assert cm.camera.index == DEFAULTS["camera"]["index"]

            os.unlink(f.name)
