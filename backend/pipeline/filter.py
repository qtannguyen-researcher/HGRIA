"""Noise filter and temporal filter for gesture predictions."""

import collections
from typing import TYPE_CHECKING, Deque

if TYPE_CHECKING:
    from backend.core.models import Frame, Landmark, Prediction
    from backend.core.configuration import ConfigurationManager


class NoiseFilter:
    """Filters out low-quality predictions based on landmark and frame quality."""

    MAX_LOW_CONFIDENCE = 3
    MIN_BBOX_AREA = 0.005

    def __init__(self, config: "ConfigurationManager", logger: "any" = None) -> None:
        """
        Initialize the noise filter.

        Args:
            config: Configuration object
            logger: Optional logger
        """
        self._blur_threshold = config.gesture_recognition.noise_filter_blur_threshold
        self._logger = logger

    def filter(self, pred: "Prediction", lm: "Landmark", frame: "Frame") -> "Prediction":
        """
        Apply noise filtering to a prediction.

        Args:
            pred: The prediction to filter
            lm: The landmark data
            frame: The frame data

        Returns:
            The same prediction object (mutated if filtered)
        """
        # Check for too many low-confidence landmarks
        if len(lm.low_confidence_indices) > self.MAX_LOW_CONFIDENCE:
            pred.is_filtered = True
            pred.filter_reason = f"low_confidence_landmarks ({len(lm.low_confidence_indices)})"
            self._log_rejection(pred.filter_reason)
            return pred

        # Check for blurry frame
        if frame.blur_score < self._blur_threshold:
            pred.is_filtered = True
            pred.filter_reason = f"blurry_frame (score={frame.blur_score:.1f})"
            self._log_rejection(pred.filter_reason)
            return pred

        # Check for hand too small
        bbox_area = lm.bounding_box.area()
        if bbox_area < self.MIN_BBOX_AREA:
            pred.is_filtered = True
            pred.filter_reason = f"hand_too_small (area={bbox_area:.3f})"
            self._log_rejection(pred.filter_reason)
            return pred

        return pred

    def _log_rejection(self, reason: str) -> None:
        """Log a filtering rejection at DEBUG level."""
        if self._logger:
            self._logger.debug(
                "prediction_filtered",
                reason=reason,
                module="noise_filter"
            )


class TemporalFilter:
    """Majority-vote sliding window over the last N predictions."""

    def __init__(self, config: "ConfigurationManager") -> None:
        """
        Initialize the temporal filter.

        Args:
            config: Configuration object with smoothing_window_size
        """
        self._window_size = config.gesture_recognition.smoothing_window_size
        self._buffer: Deque[str] = collections.deque(maxlen=self._window_size)

    def update(self, pred: "Prediction") -> str:
        """
        Update the temporal filter with a new prediction.

        Args:
            pred: The prediction to add

        Returns:
            The stable gesture name, or "UNKNOWN" if no majority yet
        """
        self._buffer.append(pred.gesture_name)
        counts = collections.Counter(self._buffer)
        most_common, count = counts.most_common(1)[0]
        majority_threshold = self._window_size // 2 + 1

        if count >= majority_threshold:
            return most_common
        return "UNKNOWN"

    def reset(self) -> None:
        """Reset the temporal filter buffer."""
        self._buffer.clear()

    @property
    def window_size(self) -> int:
        """Get the current window size."""
        return self._window_size
