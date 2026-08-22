"""Server-side instrumentation for the static recognition pipeline.

Timing uses ``time.perf_counter()`` (monotonic, high-resolution) for every
duration. Wall-clock ISO-8601 values are recorded only for log correlation
and must not be used to compute latencies.

This module does not change recognition behaviour. It times existing calls
and writes observations.
"""

from __future__ import annotations

import hashlib
import json
import os
import resource
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

# Per-frame decision labels recorded at the pipeline branch that ended
# processing. Do not infer these later from timing fields.
EXIT_REASONS = (
    "no_hand",
    "noise",
    "temporal",
    "cooldown",
    "unmapped",
    "command",
)


def mono_now() -> float:
    """Monotonic high-resolution clock. Use for all duration calculations."""
    return time.perf_counter()


def wall_iso() -> str:
    """UTC wall-clock timestamp for log correlation only (not for durations)."""
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def ms_since(start_mono: float, end_mono: Optional[float] = None) -> float:
    """Elapsed milliseconds between two monotonic timestamps."""
    end = mono_now() if end_mono is None else end_mono
    return (end - start_mono) * 1000.0


def time_call(fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Tuple[Any, float, float]:
    """Call ``fn`` and return ``(result, elapsed_ms, t_done_mono)``.

    The function is invoked exactly once with the given arguments. Timing
    is taken around the call and does not alter arguments or result.
    """
    t0 = mono_now()
    result = fn(*args, **kwargs)
    t1 = mono_now()
    return result, (t1 - t0) * 1000.0, t1


class FrameIdSequence:
    """Process-wide incrementing frame IDs for server-generated captures."""

    def __init__(self) -> None:
        self._n = 0
        self._lock = threading.Lock()

    def next_id(self) -> int:
        with self._lock:
            self._n += 1
            return self._n


# Shared by OpenCV capture and any server-side fallback that needs an ID.
SERVER_FRAME_IDS = FrameIdSequence()


def normalize_frame_id(value: Any) -> Optional[Any]:
    """Preserve a client-provided frame_id; reject empty / missing values.

    Integers stay integers. Numeric strings become integers so JSONL and
    command payloads can correlate on the same type. Other non-empty strings
    are kept as-is.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        if text.isdigit() or (text.startswith("-") and text[1:].isdigit()):
            return int(text)
        return text
    return str(value)


@dataclass
class FrameTiming:
    """Per-frame monotonic timestamps and derived stage durations.

    All ``t_*`` fields are ``time.perf_counter()`` readings (seconds).
    All ``*_ms`` fields are durations in milliseconds derived from those
    readings. Missing stages stay ``None`` (the stage did not run).
    """

    frame_id: Any = None
    # Monotonic timestamps
    t_capture: Optional[float] = None
    t_server_received: Optional[float] = None
    t_preprocess_done: Optional[float] = None
    t_mediapipe_done: Optional[float] = None
    t_classification_done: Optional[float] = None
    t_command_generated: Optional[float] = None
    t_command_emitted: Optional[float] = None
    # Stage durations (ms)
    capture_ms: Optional[float] = None
    preprocess_ms: Optional[float] = None
    mediapipe_ms: Optional[float] = None
    landmark_extraction_ms: Optional[float] = None
    classification_ms: Optional[float] = None
    noise_filter_ms: Optional[float] = None
    temporal_filter_ms: Optional[float] = None
    command_generation_ms: Optional[float] = None
    total_server_ms: Optional[float] = None
    # Recognition snapshot (rule score, not a calibrated probability)
    gesture: Optional[str] = None
    score: Optional[float] = None
    command_emitted: bool = False
    dropped_frames: int = 0
    # Why this frame's processing ended. Null only if an exception aborted
    # the try-block before a decision (see measurement_readiness.md).
    exit_reason: Optional[str] = None
    run_id: Optional[str] = None
    # Wall clock for log correlation only
    timestamp: str = field(default_factory=wall_iso)
    # Optional 1 Hz resource snapshot (copied, not sampled per frame)
    cpu_percent: Optional[float] = None
    rss_mb: Optional[float] = None

    def finish(self, end_mono: Optional[float] = None) -> None:
        """Set ``total_server_ms`` from ``t_server_received`` to ``end_mono``."""
        if self.t_server_received is None:
            return
        self.total_server_ms = ms_since(self.t_server_received, end_mono)

    def monotonic_timestamps(self) -> List[float]:
        """Present monotonic timestamps in pipeline order (skipping None)."""
        ordered = [
            self.t_capture,
            self.t_server_received,
            self.t_preprocess_done,
            self.t_mediapipe_done,
            self.t_classification_done,
            self.t_command_generated,
            self.t_command_emitted,
        ]
        return [t for t in ordered if t is not None]

    def stage_durations_ms(self) -> Dict[str, float]:
        """Present stage durations (None omitted)."""
        names = (
            "capture_ms",
            "preprocess_ms",
            "mediapipe_ms",
            "landmark_extraction_ms",
            "classification_ms",
            "noise_filter_ms",
            "temporal_filter_ms",
            "command_generation_ms",
            "total_server_ms",
        )
        return {name: getattr(self, name) for name in names if getattr(self, name) is not None}

    def to_jsonl_record(self) -> Dict[str, Any]:
        """JSON-serialisable observation for one processed frame."""
        return {
            "frame_id": self.frame_id,
            "timestamp": self.timestamp,
            "t_capture": self.t_capture,
            "t_server_received": self.t_server_received,
            "t_preprocess_done": self.t_preprocess_done,
            "t_mediapipe_done": self.t_mediapipe_done,
            "t_classification_done": self.t_classification_done,
            "t_command_generated": self.t_command_generated,
            "t_command_emitted": self.t_command_emitted,
            "capture_ms": self.capture_ms,
            "preprocess_ms": self.preprocess_ms,
            "mediapipe_ms": self.mediapipe_ms,
            "landmark_extraction_ms": self.landmark_extraction_ms,
            "classification_ms": self.classification_ms,
            "noise_filter_ms": self.noise_filter_ms,
            "temporal_filter_ms": self.temporal_filter_ms,
            "command_generation_ms": self.command_generation_ms,
            "total_server_ms": self.total_server_ms,
            "gesture": self.gesture,
            "score": self.score,
            "command_emitted": self.command_emitted,
            "exit_reason": self.exit_reason,
            "run_id": self.run_id,
            "dropped_frames": self.dropped_frames,
            "cpu_percent": self.cpu_percent,
            "rss_mb": self.rss_mb,
        }

    def debug_snapshot(self) -> Dict[str, Any]:
        """Latest timing for the live debug endpoint (no percentiles)."""
        return {
            "frame_id": self.frame_id,
            "capture_ms": self.capture_ms,
            "preprocess_ms": self.preprocess_ms,
            "mediapipe_ms": self.mediapipe_ms,
            "landmark_extraction_ms": self.landmark_extraction_ms,
            "classification_ms": self.classification_ms,
            "noise_filter_ms": self.noise_filter_ms,
            "temporal_filter_ms": self.temporal_filter_ms,
            "command_generation_ms": self.command_generation_ms,
            "total_server_ms": self.total_server_ms,
            "gesture": self.gesture,
            "score": self.score,
            "command_emitted": self.command_emitted,
            "exit_reason": self.exit_reason,
            "run_id": self.run_id,
            "timestamp": self.timestamp,
        }


class ExperimentLogger:
    """Append-only JSONL writer for experiment observations.

    One JSON object per line. Path is configurable and must not be a
    machine-specific absolute default. The writer is process-safe via a lock
    (the pipeline is single-threaded; the lock covers tests and future use).
    """

    def __init__(self, path: str, enabled: bool = True) -> None:
        if not path:
            raise ValueError("ExperimentLogger path must be a non-empty string")
        self._path = path
        self._enabled = bool(enabled)
        self._lock = threading.Lock()
        self._prepared = False

    @property
    def path(self) -> str:
        return self._path

    @property
    def enabled(self) -> bool:
        return self._enabled

    def write(self, record: Dict[str, Any]) -> None:
        """Append one JSON object as a single line. No-op when disabled."""
        if not self._enabled:
            return
        line = json.dumps(record, ensure_ascii=False, allow_nan=False)
        with self._lock:
            self._ensure_parent()
            with open(self._path, "a", encoding="utf-8") as handle:
                handle.write(line)
                handle.write("\n")

    def _ensure_parent(self) -> None:
        if self._prepared:
            return
        parent = os.path.dirname(self._path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        self._prepared = True


class ResourceSampler:
    """Process CPU % and RSS, sampled at most once per interval.

    ``cpu_percent`` is **this process** (user + system time via
    ``time.process_time()``), not system-wide CPU. On a multi-core host the
    value can exceed 100 if the process uses more than one core.

    ``rss_mb`` is the current resident set size of this process in MiB
    (Linux ``/proc/self/statm`` or ``resource.ru_maxrss`` fallback).
    """

    def __init__(self, interval_s: float = 1.0) -> None:
        self._interval_s = max(0.1, float(interval_s))
        self._lock = threading.Lock()
        self._last_mono: Optional[float] = None
        self._last_cpu: Optional[float] = None
        self._latest: Dict[str, Any] = {
            "cpu_percent": None,
            "rss_mb": None,
            "cpu_scope": "process",
        }

    @property
    def latest(self) -> Dict[str, Any]:
        return dict(self._latest)

    def maybe_sample(self) -> Dict[str, Any]:
        """Return the latest sample, refreshing if the interval has elapsed."""
        now = mono_now()
        with self._lock:
            if (
                self._last_mono is not None
                and (now - self._last_mono) < self._interval_s
            ):
                return dict(self._latest)

            cpu_now = time.process_time()
            rss_mb = _process_rss_mb()
            cpu_percent: Optional[float] = None
            if self._last_mono is not None and self._last_cpu is not None:
                wall = now - self._last_mono
                if wall > 0:
                    cpu_percent = ((cpu_now - self._last_cpu) / wall) * 100.0

            self._last_mono = now
            self._last_cpu = cpu_now
            self._latest = {
                "cpu_percent": cpu_percent,
                "rss_mb": rss_mb,
                "cpu_scope": "process",
            }
            return dict(self._latest)


def _process_rss_mb() -> Optional[float]:
    """Current process RSS in MiB, or None if unavailable."""
    try:
        with open("/proc/self/statm", encoding="utf-8") as handle:
            parts = handle.read().split()
        if len(parts) >= 2:
            # statm fields are in pages; field 1 is resident pages.
            page_bytes = os.sysconf("SC_PAGE_SIZE")
            return (int(parts[1]) * page_bytes) / (1024.0 * 1024.0)
    except (OSError, ValueError):
        pass

    try:
        usage = resource.getrusage(resource.RUSAGE_SELF)
        # Linux: ru_maxrss is kilobytes (peak, not current).
        return float(usage.ru_maxrss) / 1024.0
    except (OSError, AttributeError, ValueError):
        return None


def instrumentation_config(config: Any) -> Dict[str, Any]:
    """Read instrumentation settings from a ConfigurationManager-like object."""
    enabled = True
    jsonl_path = "logs/instrumentation.jsonl"
    interval_s = 1.0
    try:
        if hasattr(config, "is_instrumentation_enabled"):
            enabled = bool(config.is_instrumentation_enabled())
        else:
            section = getattr(config, "instrumentation", None)
            if section is not None:
                enabled = bool(getattr(section, "enabled", True))
    except AttributeError:
        enabled = True

    try:
        section = getattr(config, "instrumentation", None)
        if section is not None:
            jsonl_path = getattr(section, "jsonl_path", jsonl_path) or jsonl_path
            interval_s = float(getattr(section, "resource_sample_interval_s", interval_s))
    except (AttributeError, TypeError, ValueError):
        pass

    run_id = ""
    try:
        if hasattr(config, "run_id"):
            run_id = str(config.run_id() or "")
        else:
            section = getattr(config, "instrumentation", None)
            if section is not None:
                run_id = str(getattr(section, "run_id", "") or "")
    except (AttributeError, TypeError):
        run_id = ""

    return {
        "enabled": enabled,
        "jsonl_path": jsonl_path,
        "resource_sample_interval_s": interval_s,
        "run_id": run_id,
    }


def build_experiment_logger(config: Any) -> ExperimentLogger:
    """Construct an ExperimentLogger from config (relative default path)."""
    cfg = instrumentation_config(config)
    return ExperimentLogger(path=cfg["jsonl_path"], enabled=cfg["enabled"])


def resolve_run_id(config: Any) -> str:
    """Return an explicit run_id or generate a UUID.

    Preference: ``instrumentation.run_id`` (including ``HGRIA_INSTRUMENTATION_RUN_ID``)
    if non-empty; otherwise a new UUID4. Generated IDs are not written back
    into config.
    """
    configured = ""
    try:
        if hasattr(config, "run_id"):
            configured = str(config.run_id() or "")
        else:
            section = getattr(config, "instrumentation", None)
            if section is not None:
                configured = str(getattr(section, "run_id", "") or "")
    except (AttributeError, TypeError):
        configured = ""
    configured = configured.strip()
    return configured or str(uuid.uuid4())


def sidecar_path_for(jsonl_path: str) -> str:
    """Derive the run-metadata sidecar path from the JSONL path."""
    root, _ext = os.path.splitext(jsonl_path)
    return root + ".run.json"


def write_run_sidecar(path: str, metadata: Dict[str, Any]) -> None:
    """Write (overwrite) the run metadata sidecar as pretty-printed JSON."""
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(metadata, handle, indent=2, ensure_ascii=False, sort_keys=True)
        handle.write("\n")


def _git_sha() -> Optional[str]:
    """Best-effort git SHA of the current checkout. None if unavailable."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
        if result.returncode == 0:
            sha = (result.stdout or "").strip()
            return sha or None
    except (OSError, subprocess.TimeoutExpired):
        return None
    return None


def _config_sha256(config: Any) -> Optional[str]:
    """SHA-256 of the live configuration dict (canonical JSON)."""
    try:
        data = getattr(config, "_data", None)
        if data is None and hasattr(config, "public_dict"):
            data = config.public_dict()
        if data is None:
            return None
        blob = json.dumps(data, sort_keys=True, default=str).encode("utf-8")
        return hashlib.sha256(blob).hexdigest()
    except (TypeError, ValueError):
        return None


def _package_version(name: str) -> Optional[str]:
    try:
        from importlib.metadata import PackageNotFoundError, version
    except ImportError:
        return None
    try:
        return version(name)
    except PackageNotFoundError:
        return None


def opencv_snapshot() -> Dict[str, Any]:
    """Report which OpenCV distributions are installed and which cv2 loaded."""
    snapshot: Dict[str, Any] = {
        "cv2_version": None,
        "cv2_file": None,
        "distributions": {
            "opencv-python": _package_version("opencv-python"),
            "opencv-python-headless": _package_version("opencv-python-headless"),
            "opencv-contrib-python": _package_version("opencv-contrib-python"),
        },
    }
    try:
        import cv2

        snapshot["cv2_version"] = getattr(cv2, "__version__", None)
        snapshot["cv2_file"] = getattr(cv2, "__file__", None)
    except Exception:
        pass
    return snapshot


def collect_run_metadata(
    config: Any,
    run_id: str,
    jsonl_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Static run identity for the sidecar (not a performance result)."""
    preview_enabled = True
    evaluation_mode = False
    strict_camera = False
    colab_mode = False
    colab_fallback = False
    dynamic_enabled = False
    instrumentation_enabled = True
    try:
        if hasattr(config, "is_preview_enabled"):
            preview_enabled = bool(config.is_preview_enabled())
        if hasattr(config, "is_evaluation_mode"):
            evaluation_mode = bool(config.is_evaluation_mode())
        if hasattr(config, "is_strict_camera"):
            strict_camera = bool(config.is_strict_camera())
        if hasattr(config, "is_dynamic_gestures_enabled"):
            dynamic_enabled = bool(config.is_dynamic_gestures_enabled())
        if hasattr(config, "is_instrumentation_enabled"):
            instrumentation_enabled = bool(config.is_instrumentation_enabled())
        camera = getattr(config, "camera", None)
        if camera is not None:
            colab_mode = bool(getattr(camera, "colab_mode", False))
            colab_fallback = bool(getattr(camera, "colab_fallback", False))
    except AttributeError:
        pass

    return {
        "schema": "hgria.run_metadata.v1",
        "run_id": run_id,
        "created_at": wall_iso(),
        "git_sha": _git_sha(),
        "config_sha256": _config_sha256(config),
        "python": sys.version.split()[0],
        "cwd": os.getcwd(),
        "jsonl_path": jsonl_path,
        "deployment_path": "local_opencv_server",
        "preview_enabled": preview_enabled,
        "evaluation_mode": evaluation_mode,
        "strict_camera": strict_camera,
        "colab_mode": colab_mode,
        "colab_fallback": colab_fallback,
        "dynamic_gestures_enabled": dynamic_enabled,
        "instrumentation_enabled": instrumentation_enabled,
        "opencv": opencv_snapshot(),
        "packages": {
            "mediapipe": _package_version("mediapipe"),
            "numpy": _package_version("numpy"),
            "scipy": _package_version("scipy"),
            "onnxruntime": _package_version("onnxruntime"),
            "flask": _package_version("flask"),
        },
        "validity": {
            "opencv_baseline_invalid_if_colab_mode": True,
            "note": (
                "A copied log is identified by run_id + this sidecar. "
                "If colab_mode is true the run is not a local OpenCV baseline."
            ),
        },
    }
