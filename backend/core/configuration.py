"""Configuration manager for the HGRIA system.

Loads config.json, validates all fields against a schema, merges environment
variable overrides, and exposes the result as a frozen nested namespace.
"""

import copy
import json
import os
from typing import Any, Dict, List, Tuple, Union


# Validation schema: field -> (type, min, max)
SCHEMA: Dict[str, Tuple[type, Union[int, float], Union[int, float]]] = {
    "camera.index":                              (int,    0,    9),
    "camera.frame_width":                        (int,    160,  1920),
    "camera.frame_height":                       (int,    120,  1080),
    "camera.target_fps":                         (int,    5,    60),
    "mediapipe.min_detection_confidence":        (float,  0.5,  1.0),
    "mediapipe.min_tracking_confidence":         (float,  0.3,  1.0),
    "mediapipe.max_num_hands":                   (int,    1,    2),
    "mediapipe.model_complexity":                (int,    0,    1),
    "gesture_recognition.confidence_threshold":  (float,  0.5,  1.0),
    "gesture_recognition.smoothing_window_size":(int,    1,    10),
    "server.port":                               (int,    1024, 65535),
}

DEFAULTS: Dict[str, Any] = {
    "camera": {
        "index": 0,
        "frame_width": 640,
        "frame_height": 480,
        "target_fps": 30,
        "colab_mode": False,
        # Set at runtime if OpenCV capture fails and the process falls back
        # to browser JPEG POST. A measurement run with this true is invalid
        # as an OpenCV baseline (see /api/debug and measurement_readiness.md).
        "colab_fallback": False,
        # Explicit local browser JPEG POST path. Distinct from Colab fallback:
        # does not set colab_mode or colab_fallback. Default false keeps the
        # Phase 3A OpenCV capture path unchanged.
        "browser_source": False,
    },
    "mediapipe": {
        # Aligned with config/config.json (baseline source of truth).
        "min_detection_confidence": 0.5,
        "min_tracking_confidence": 0.5,
        "max_num_hands": 1,
        "model_complexity": 0,
    },
    "gesture_recognition": {
        "confidence_threshold": 0.75,
        # Aligned with config/config.json (baseline source of truth).
        "smoothing_window_size": 3,
        "noise_filter_blur_threshold": 30,
        "dominant_hand": "Right",
    },
    "gesture_cooldowns_ms": {
        "open_palm": 500,
        "closed_fist": 500,
        "point_left": 300,
        "point_right": 300,
        "thumb_up": 500,
        "victory": 500,
        "stop": 1000,
        "pinch": 400,
        "ok": 500,
        # Dynamic gesture cooldowns
        "SWIPE_LEFT": 400,
        "SWIPE_RIGHT": 400,
        "SWIPE_UP": 400,
        "SWIPE_DOWN": 400,
        "SWIPE_LEFT2": 400,
        "SWIPE_RIGHT2": 400,
        "SWIPE_UP2": 400,
        "SWIPE_DOWN2": 400,
        "SWIPE_LEFT3": 400,
        "SWIPE_RIGHT3": 400,
        "SWIPE_UP3": 400,
        "SWIPE_DOWN3": 400,
        "FAST_SWIPE_UP": 300,
        "FAST_SWIPE_DOWN": 300,
        "ZOOM_IN": 500,
        "ZOOM_OUT": 500,
        "DRAG": 0,
        "DROP": 0,
        "DRAG2": 0,
        "DROP2": 0,
        "DRAG3": 0,
        "DROP3": 0,
        "TAP": 300,
        "DOUBLE_TAP": 500,
    },
    "dynamic_gestures": {
        "enabled": False,
        "detection_model_path": "dynamic_gestures/models/hand_detector.onnx",
        "classification_model_path": "dynamic_gestures/models/crops_classifier.onnx",
        "max_age": 30,
        "min_hits": 3,
        "iou_threshold": 0.3,
        "maxlen": 30,
        "min_frames": 20,
    },
    "server": {
        "host": "0.0.0.0",
        "port": 5000,
        "websocket_path": "/socket.io/",
        "cors_origins": "*",
        "command_buffer_size": 10,
        "command_buffer_ttl_seconds": 5,
    },
    "logging": {
        "level": "INFO",
        "log_to_file": True,
        # Relative to process CWD (typically the repo root). Machine-specific
        # and Colab Drive paths are not reproducible across checkouts.
        "log_file_path": "logs/",
        "log_raw_landmarks": False,
        "max_log_file_size_mb": 10,
        "max_log_files": 5,
    },
    "debug": {
        "debug_mode": False,
        "show_landmark_overlay": False,
        "log_pipeline_latency": False,
    },
    "evaluation": {
        "mode": False,
        # Demo/default: emit JPEG preview (~10 Hz). Measurement: set false so
        # preview encode/emit is absent from the processing path.
        "preview_enabled": True,
        # When true, CameraModule does not silently fall back to Colab/browser
        # capture if the local OpenCV camera fails to open.
        "strict_camera": False,
    },
    # Phase 2: server-side instrumentation. Relative path only — do not put
    # a machine-specific absolute path here.
    "instrumentation": {
        "enabled": True,
        "jsonl_path": "logs/instrumentation.jsonl",
        "resource_sample_interval_s": 1.0,
        # Empty string means generate a UUID at pipeline start. Prefer an
        # explicit value (or HGRIA_INSTRUMENTATION_RUN_ID) for measurement.
        "run_id": "",
        "client_jsonl_path": "logs/client_instrumentation.jsonl",
    },
    "custom_gestures": [],
}

# Hot-reloadable field names
HOT_RELOAD_FIELDS: set = {
    "gesture_recognition.confidence_threshold",
    "gesture_recognition.smoothing_window_size",
    "gesture_recognition.dominant_hand",
    "logging.level",
    "debug.debug_mode",
    "debug.show_landmark_overlay",
    "debug.log_pipeline_latency",
}
# All gesture_cooldowns_ms.* fields are also hot-reloadable


class _Namespace:
    """Allows attribute-style access: config.camera.target_fps"""

    def __init__(self, d: Dict[str, Any]):
        self.__dict__.update(d)
        # Make nested dicts also into namespaces
        for k, v in d.items():
            if isinstance(v, dict) and k != "gesture_cooldowns_ms":
                setattr(self, k, _Namespace(v))

    def __repr__(self) -> str:
        return f"_Namespace({self.__dict__})"

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)
        if name in self.__dict__:
            return self.__dict__[name]
        raise AttributeError(f"No attribute: {name}")


class ConfigurationManager:
    """Main configuration manager class."""

    DEFAULTS = DEFAULTS
    SCHEMA = SCHEMA
    HOT_RELOAD_FIELDS = HOT_RELOAD_FIELDS

    def __init__(self, config_path: str = "config/config.json") -> None:
        self._data = self._deep_merge(DEFAULTS, self._load_file(config_path))
        self._apply_env_overrides()
        self._validate()
        self._original = copy.deepcopy(self._data)

    def _load_file(self, path: str) -> Dict[str, Any]:
        """Load configuration from JSON file. Returns empty dict if missing."""
        if not os.path.exists(path):
            return {}
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    def _deep_merge(self, base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
        """Deep merge override dict into base dict."""
        result = {**base}
        for k, v in override.items():
            if isinstance(v, dict) and k in result and isinstance(result[k], dict):
                result[k] = self._deep_merge(result[k], v)
            else:
                result[k] = v
        return result

    def _get_nested(self, section: str, param: str) -> Any:
        """Get a nested config value."""
        return self._data.get(section, {}).get(param)

    def _set_nested(self, section: str, param: str, value: Any) -> None:
        """Set a nested config value."""
        if section not in self._data:
            self._data[section] = {}
        self._data[section][param] = value

    def _coerce(self, val: str, section: str, param: str) -> Any:
        """Coerce environment variable string to appropriate type."""
        section_data = DEFAULTS.get(section, {})
        default_val = section_data.get(param)
        if default_val is None:
            return val
        if isinstance(default_val, bool):
            return val.lower() in ("true", "1", "yes")
        if isinstance(default_val, int):
            return int(val)
        if isinstance(default_val, float):
            return float(val)
        return val

    def _apply_env_overrides(self) -> None:
        """Apply environment variable overrides with HGRIA_ prefix."""
        prefix = "HGRIA_"
        for key, val in os.environ.items():
            if not key.startswith(prefix):
                continue
            parts = key[len(prefix):].lower().split("_", 1)
            if len(parts) == 2:
                section, param = parts
                if section in self._data and param in self._data[section]:
                    self._data[section][param] = self._coerce(val, section, param)

    def _validate(self) -> None:
        """Validate all config values against schema. Replace out-of-range with defaults."""
        for dotted, (typ, lo, hi) in SCHEMA.items():
            parts = dotted.split(".", 1)
            if len(parts) != 2:
                continue
            section, param = parts
            val = self._get_nested(section, param)
            if val is None:
                continue
            if not isinstance(val, typ) or not (lo <= val <= hi):
                self._set_nested(section, param, DEFAULTS[section][param])

    def update(self, field: str, value: Any) -> bool:
        """
        Hot-reload a single field. Returns False if field is not hot-reloadable.

        Args:
            field: Dot-separated field path (e.g., "logging.level")
            value: New value for the field

        Returns:
            True if update was successful, False otherwise
        """
        # Check if it's a gesture cooldown field
        is_cooldown_field = field.startswith("gesture_cooldowns_ms.")
        if field not in HOT_RELOAD_FIELDS and not is_cooldown_field:
            return False

        parts = field.split(".", 1)
        if len(parts) != 2:
            return False
        section, param = parts
        self._set_nested(section, param, value)
        return True

    def public_dict(self) -> Dict[str, Any]:
        """Returns config without sensitive fields for WebSocket transmission."""
        d = copy.deepcopy(self._data)
        if "logging" in d:
            d["logging"].pop("log_file_path", None)
        return d

    # Sections that must remain plain dicts (callers use dict methods on them).
    _PLAIN_DICT_SECTIONS = frozenset({"gesture_cooldowns_ms", "custom_gestures"})

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)
        if name in self._data:
            val = self._data[name]
            if isinstance(val, dict) and name not in self._PLAIN_DICT_SECTIONS:
                return _Namespace(val)
            return val
        raise AttributeError(f"No config section: {name}")

    def get(self, section: str, param: str, default: Any = None) -> Any:
        """Get a config value with a default."""
        return self._get_nested(section, param) or default

    def is_dynamic_gestures_enabled(self) -> bool:
        """Return True only when dynamic_gestures.enabled is explicitly true.

        Missing section or a false/absent flag both mean the static-only path.
        Uses dict lookup so a JSON ``false`` is not swallowed (unlike ``get()``).
        """
        section = self._data.get("dynamic_gestures")
        if not isinstance(section, dict):
            return False
        return bool(section.get("enabled", False))

    def is_evaluation_mode(self) -> bool:
        """Return True when evaluation.mode is enabled.

        Evaluation mode is a run-time restriction for benchmark/eval sessions:
        client UI bypass and keyboard command injection must be disabled.
        """
        section = self._data.get("evaluation")
        if not isinstance(section, dict):
            return False
        return bool(section.get("mode", False))

    def is_instrumentation_enabled(self) -> bool:
        """Return True when instrumentation.enabled is true (default True).

        Uses dict lookup so a JSON ``false`` is not swallowed (unlike ``get()``).
        A missing section means the Phase 2 default: enabled.
        """
        section = self._data.get("instrumentation")
        if not isinstance(section, dict):
            return True
        return bool(section.get("enabled", True))

    def is_preview_enabled(self) -> bool:
        """Return True when JPEG preview encode/emit should run.

        Default is True (demo unchanged). Uses dict lookup so JSON ``false``
        is not swallowed (unlike ``get()``). Missing key means enabled.
        """
        section = self._data.get("evaluation")
        if not isinstance(section, dict):
            return True
        if "preview_enabled" not in section:
            return True
        return bool(section.get("preview_enabled"))

    def is_strict_camera(self) -> bool:
        """Return True when local camera open failure must not fall back.

        Default is False (existing Colab/browser fallback remains).
        """
        section = self._data.get("evaluation")
        if not isinstance(section, dict):
            return False
        return bool(section.get("strict_camera", False))

    def is_browser_source(self) -> bool:
        """Return True when the local browser JPEG POST path is selected.

        This is an explicit Phase 3B capture source. It is not silent Colab
        fallback and does not change Phase 3A defaults.
        """
        section = self._data.get("camera")
        if not isinstance(section, dict):
            return False
        return bool(section.get("browser_source", False))

    def client_jsonl_path(self) -> str:
        """Return the client measurement JSONL path (relative default)."""
        section = self._data.get("instrumentation")
        if not isinstance(section, dict):
            return "logs/client_instrumentation.jsonl"
        value = section.get("client_jsonl_path") or "logs/client_instrumentation.jsonl"
        return str(value)

    def run_id(self) -> str:
        """Return configured instrumentation.run_id, or empty if unset.

        Empty means the pipeline should generate a UUID. Does not use
        ``get()`` so a deliberate empty string stays empty.
        """
        section = self._data.get("instrumentation")
        if not isinstance(section, dict):
            return ""
        value = section.get("run_id", "")
        if value is None:
            return ""
        return str(value)
