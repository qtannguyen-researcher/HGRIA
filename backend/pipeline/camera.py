"""Camera module with strategy pattern for local and Colab execution modes."""

import threading
from typing import TYPE_CHECKING, Any, List, Optional, Tuple

import cv2
import numpy as np

if TYPE_CHECKING:
    from backend.core.models import Frame
    from backend.core.configuration import ConfigurationManager

from backend.core.errors import CameraInitializationError
from backend.utils.instrumentation import (
    SERVER_FRAME_IDS,
    mono_now,
    normalize_frame_id,
)


class CaptureStrategy:
    """Protocol for camera capture strategies."""

    def read(self) -> Optional[np.ndarray]:
        """Read a frame. Returns None if no frame available."""
        ...

    def release(self) -> None:
        """Release camera resources."""
        ...


class OpenCVCaptureStrategy(CaptureStrategy):
    """Capture strategy using OpenCV VideoCapture for local execution."""

    def __init__(self, config: "ConfigurationManager") -> None:
        self._cap = cv2.VideoCapture(config.camera.index)
        if not self._cap.isOpened():
            raise CameraInitializationError(
                f"Cannot open camera at index {config.camera.index}"
            )
        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, config.camera.frame_width)
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, config.camera.frame_height)
        self._cap.set(cv2.CAP_PROP_FPS, config.camera.target_fps)

    def read(self) -> Optional[np.ndarray]:
        """Read a frame from the camera."""
        ok, frame = self._cap.read()
        return frame if ok else None

    def release(self) -> None:
        """Release the camera."""
        if self._cap:
            self._cap.release()


class ColabCaptureStrategy(CaptureStrategy):
    """Capture strategy receiving JPEG base64 frames POSTed from the browser."""

    def __init__(self, frame_store: "FrameStore") -> None:
        self._store = frame_store

    def read(self) -> Optional[np.ndarray]:
        """Consume and return the latest frame, or None if no new frame is ready.

        Uses consume semantics (read-and-clear) so the pipeline processes each
        browser frame exactly once instead of re-running MediaPipe on stale data
        thousands of times per second.
        """
        return self._store.consume()

    def release(self) -> None:
        """No-op for Colab mode."""
        pass


class FrameStore:
    """Thread-safe singleton store for the latest frame received from the browser."""

    _instance: Optional["FrameStore"] = None
    _lock = threading.Lock()

    def __new__(cls) -> "FrameStore":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._frame = None
                    cls._instance._pending_frame_id = None
                    cls._instance._pending_t_received = None
                    cls._instance._last_consumed_id = None
                    cls._instance._last_consumed_t_received = None
                    cls._instance._dropped_frames = 0
                    cls._instance._store_lock = threading.Lock()
        return cls._instance

    def _ensure_fields(self) -> None:
        """Initialise instrumentation fields on a pre-existing singleton."""
        if not hasattr(self, "_pending_frame_id"):
            self._pending_frame_id = None
        if not hasattr(self, "_pending_t_received"):
            self._pending_t_received = None
        if not hasattr(self, "_last_consumed_id"):
            self._last_consumed_id = None
        if not hasattr(self, "_last_consumed_t_received"):
            self._last_consumed_t_received = None
        if not hasattr(self, "_dropped_frames"):
            self._dropped_frames = 0

    def put(self, bgr: np.ndarray, frame_id: Any = None) -> None:
        """Store a new frame (last-write-wins).

        If an unread frame is already present it is overwritten and the
        dropped-frame counter is incremented. Behaviour is otherwise unchanged.
        """
        t_received = mono_now()
        with self._store_lock:
            self._ensure_fields()
            if self._frame is not None:
                self._dropped_frames += 1
            self._frame = bgr
            self._pending_frame_id = normalize_frame_id(frame_id)
            self._pending_t_received = t_received

    def consume(self) -> Optional[np.ndarray]:
        """Atomically read and clear the stored frame.

        Returns the frame (or None) and immediately clears the slot so the
        pipeline will block on the next call until a new frame arrives from
        the browser.  This ensures each JPEG is processed exactly once.
        """
        with self._store_lock:
            self._ensure_fields()
            frame = self._frame
            self._last_consumed_id = self._pending_frame_id
            self._last_consumed_t_received = self._pending_t_received
            self._frame = None
            self._pending_frame_id = None
            self._pending_t_received = None
            return frame

    def last_consumed_meta(self) -> Tuple[Any, Optional[float]]:
        """Return ``(frame_id, t_server_received)`` from the last consume()."""
        with self._store_lock:
            self._ensure_fields()
            return self._last_consumed_id, self._last_consumed_t_received

    @property
    def dropped_frames(self) -> int:
        """Number of unread frames overwritten by a later put()."""
        with self._store_lock:
            self._ensure_fields()
            return self._dropped_frames

    def get_latest(self) -> Optional[np.ndarray]:
        """Peek at the latest frame without consuming it (used by /api/debug)."""
        with self._store_lock:
            return self._frame

    def clear(self) -> None:
        """Clear the stored frame (does not reset the dropped-frame counter)."""
        with self._store_lock:
            self._ensure_fields()
            self._frame = None
            self._pending_frame_id = None
            self._pending_t_received = None

    def reset_instrumentation(self) -> None:
        """Clear stored frame, last-consumed meta, and dropped-frame counter.

        Intended for tests. Does not change last-write-wins put() behaviour.
        """
        with self._store_lock:
            self._ensure_fields()
            self._frame = None
            self._pending_frame_id = None
            self._pending_t_received = None
            self._last_consumed_id = None
            self._last_consumed_t_received = None
            self._dropped_frames = 0


class CameraModule:
    """Main camera module that selects the appropriate capture strategy."""

    def __init__(self, config: "ConfigurationManager") -> None:
        """
        Initialize the camera module.

        Args:
            config: Configuration object with camera.* fields
        """
        self._config = config
        self._frame_store = FrameStore()

        browser_source = False
        try:
            if hasattr(config, "is_browser_source"):
                browser_source = bool(config.is_browser_source())
            else:
                browser_source = bool(getattr(config.camera, "browser_source", False))
        except AttributeError:
            browser_source = False

        if config.camera.colab_mode or browser_source:
            # browser_source uses the same FrameStore path as Colab but does
            # not set colab_mode / colab_fallback (not a silent fallback).
            self._strategy: CaptureStrategy = ColabCaptureStrategy(self._frame_store)
        else:
            self._strategy = self._open_local_or_fallback(config)

    def _open_local_or_fallback(self, config: "ConfigurationManager") -> CaptureStrategy:
        """Try to open the local camera; fall back to browser mode if unavailable.

        This handles the common case where the camera is already in use by
        another process (e.g. a Jupyter/Colab notebook) and the browser needs
        to supply frames instead.

        When ``evaluation.strict_camera`` is true the exception is re-raised
        so a measurement process cannot silently become a Colab/browser run.
        On fallback, ``camera.colab_mode`` and ``camera.colab_fallback`` are
        both set true so ``GET /api/debug`` can report the actual path.
        """
        try:
            return OpenCVCaptureStrategy(config)
        except CameraInitializationError as exc:
            strict = False
            try:
                if hasattr(config, "is_strict_camera"):
                    strict = bool(config.is_strict_camera())
            except AttributeError:
                strict = False
            if strict:
                raise
            import warnings
            warnings.warn(
                f"Local camera unavailable ({exc}). "
                "Falling back to browser-camera mode — frames must be POSTed to /api/frame. "
                "This process is NOT a valid local OpenCV baseline (colab_mode=true).",
                RuntimeWarning,
                stacklevel=3,
            )
            # Patch the live config so the /api/frame endpoint becomes active
            # and so /api/debug can report that fallback occurred.
            config._data["camera"]["colab_mode"] = True
            config._data["camera"]["colab_fallback"] = True
            return ColabCaptureStrategy(self._frame_store)

    def capture(self) -> Optional["Frame"]:
        """
        Capture a frame from the camera.

        Returns:
            A Frame object with blur_score computed, or None if no frame available.
        """
        from backend.core.models import Frame

        t_capture = mono_now()
        bgr = self._strategy.read()
        if bgr is None:
            return None

        # Compute blur score using Laplacian variance
        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
        blur_score = float(cv2.Laplacian(gray, cv2.CV_64F).var())

        frame_id = None
        t_server_received = t_capture
        if isinstance(self._strategy, ColabCaptureStrategy):
            meta_id, meta_t = self._frame_store.last_consumed_meta()
            if meta_id is not None:
                frame_id = meta_id
            if meta_t is not None:
                t_server_received = meta_t
        if frame_id is None:
            frame_id = SERVER_FRAME_IDS.next_id()

        frame = Frame(
            frame_id=str(frame_id) if not isinstance(frame_id, (int, str)) else frame_id,
            bgr_data=bgr,
            width=bgr.shape[1] if len(bgr.shape) >= 2 else 640,
            height=bgr.shape[0] if len(bgr.shape) >= 2 else 480,
            blur_score=blur_score,
        )
        # Monotonic timestamps for pipeline instrumentation (not wall clock).
        frame.t_capture = t_capture
        frame.t_server_received = t_server_received
        return frame

    def release(self) -> None:
        """Release camera resources."""
        self._strategy.release()

    def get_frame_store(self) -> FrameStore:
        """Get the shared FrameStore instance for Colab mode."""
        return self._frame_store
