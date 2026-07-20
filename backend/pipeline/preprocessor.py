"""Frame preprocessor for the HGRIA pipeline."""

from typing import TYPE_CHECKING, Any

import cv2
import numpy as np

if TYPE_CHECKING:
    from backend.core.models import Frame
    from backend.core.configuration import ConfigurationManager


class FramePreprocessor:
    """Preprocesses frames for MediaPipe inference."""

    BRIGHTNESS_THRESHOLD = 60

    def __init__(self, config: "ConfigurationManager") -> None:
        """
        Initialize the preprocessor.

        Args:
            config: Configuration object
        """
        self._config = config
        self._clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))

    def process(self, frame: "Frame") -> "Frame":
        """
        Convert frame from BGR to RGB and optionally apply CLAHE.

        Args:
            frame: The Frame object with bgr_data

        Returns:
            The same Frame object with rgb_data populated (mutates in-place)
        """
        if frame.bgr_data is None:
            return frame

        # Convert BGR to RGB
        frame.rgb_data = cv2.cvtColor(frame.bgr_data, cv2.COLOR_BGR2RGB)

        # Optionally apply CLAHE when frame is too dark
        should_apply_clahe = self._should_apply_clahe(frame)
        if should_apply_clahe:
            frame.rgb_data = self._apply_clahe(frame.rgb_data)

        return frame

    def _should_apply_clahe(self, frame: "Frame") -> bool:
        """Determine if CLAHE should be applied based on brightness."""
        if self._config.debug.show_landmark_overlay:
            return True

        if frame.bgr_data is None:
            return False

        gray = cv2.cvtColor(frame.bgr_data, cv2.COLOR_BGR2GRAY)
        mean_brightness = float(np.mean(gray))

        return mean_brightness < self.BRIGHTNESS_THRESHOLD

    def _apply_clahe(self, rgb_data: np.ndarray) -> np.ndarray:
        """Apply CLAHE to the RGB image (on the luminance channel)."""
        lab = cv2.cvtColor(rgb_data, cv2.COLOR_RGB2LAB)
        l_channel, a_channel, b_channel = cv2.split(lab)
        l_clahe = self._clahe.apply(l_channel)
        lab_clahe = cv2.merge([l_clahe, a_channel, b_channel])
        return cv2.cvtColor(lab_clahe, cv2.COLOR_LAB2RGB)
