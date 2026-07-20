"""Camera module with strategy pattern for local and Colab execution modes."""

import threading
from typing import TYPE_CHECKING, Any, List, Optional

import cv2
import numpy as np

if TYPE_CHECKING:
    from backend.core.models import Frame
    from backend.core.configuration import ConfigurationManager

from backend.core.errors import CameraInitializationError


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
        """Get the latest frame from the shared store."""
        return self._store.get_latest()

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
                    cls._instance._store_lock = threading.Lock()
        return cls._instance

    def put(self, bgr: np.ndarray) -> None:
        """Store a new frame."""
        with self._store_lock:
            self._frame = bgr

    def get_latest(self) -> Optional[np.ndarray]:
        """Get the latest frame, or None if no new frame available."""
        with self._store_lock:
            return self._frame

    def clear(self) -> None:
        """Clear the stored frame."""
        with self._store_lock:
            self._frame = None


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

        if config.camera.colab_mode:
            self._strategy: CaptureStrategy = ColabCaptureStrategy(self._frame_store)
        else:
            self._strategy = OpenCVCaptureStrategy(config)

    def capture(self) -> Optional["Frame"]:
        """
        Capture a frame from the camera.

        Returns:
            A Frame object with blur_score computed, or None if no frame available.
        """
        from backend.core.models import Frame

        bgr = self._strategy.read()
        if bgr is None:
            return None

        # Compute blur score using Laplacian variance
        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
        blur_score = float(cv2.Laplacian(gray, cv2.CV_64F).var())

        return Frame(
            bgr_data=bgr,
            width=bgr.shape[1] if len(bgr.shape) >= 2 else 640,
            height=bgr.shape[0] if len(bgr.shape) >= 2 else 480,
            blur_score=blur_score,
        )

    def release(self) -> None:
        """Release camera resources."""
        self._strategy.release()

    def get_frame_store(self) -> FrameStore:
        """Get the shared FrameStore instance for Colab mode."""
        return self._frame_store
