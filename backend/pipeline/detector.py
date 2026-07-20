"""Hand detector module wrapping MediaPipe Hands."""

from typing import TYPE_CHECKING, Any, List, Optional, Tuple

import mediapipe as mp
import numpy as np

if TYPE_CHECKING:
    from backend.core.models import Frame
    from backend.core.configuration import ConfigurationManager


class HandDetector:
    """Wrapper for MediaPipe Hands for hand landmark detection."""

    def __init__(self, config: "ConfigurationManager", logger: Any = None) -> None:
        """
        Initialize the hand detector with warmup.

        Args:
            config: Configuration object with mediapipe.* fields
            logger: Optional logger for warmup timing
        """
        self._config = config
        self._logger = logger
        self._hands = mp.solutions.hands.Hands(
            static_image_mode=False,
            max_num_hands=config.mediapipe.max_num_hands,
            min_detection_confidence=config.mediapipe.min_detection_confidence,
            min_tracking_confidence=config.mediapipe.min_tracking_confidence,
            model_complexity=config.mediapipe.model_complexity,
        )

        # Warmup inference
        self._warmup()

    def _warmup(self) -> None:
        """Run a warmup inference on a blank frame."""
        import time
        start = time.perf_counter()
        blank = np.zeros((480, 640, 3), dtype=np.uint8)
        self._hands.process(blank)
        elapsed_ms = (time.perf_counter() - start) * 1000
        if self._logger:
            self._logger.info(
                "mediapipe_warmup_complete",
                warmup_ms=round(elapsed_ms, 2),
                module="hand_detector"
            )

    def detect(self, frame: "Frame") -> List[Tuple[Any, Any]]:
        """
        Detect hands in the given frame.

        Args:
            frame: Frame object with rgb_data populated

        Returns:
            List of (mp_landmarks, handedness_info) tuples, empty if no hands detected
        """
        if frame.rgb_data is None:
            return []

        results = self._hands.process(frame.rgb_data)

        if not results.multi_hand_landmarks:
            if self._logger:
                self._logger.debug(
                    "no_hand_detected",
                    module="hand_detector"
                )
            return []

        return list(zip(
            results.multi_hand_landmarks,
            results.multi_handedness
        ))

    def close(self) -> None:
        """Close the MediaPipe Hands instance."""
        self._hands.close()
