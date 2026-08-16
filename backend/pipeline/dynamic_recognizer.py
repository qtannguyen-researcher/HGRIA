"""Dynamic gesture recognizer that wraps the OC-SORT + ONNX pipeline.

Provides a single ``DynamicGestureRecognizer`` that accepts a BGR numpy frame
and returns an optional ``DynamicPrediction`` with the detected event name.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Optional
import uuid

import numpy as np

if TYPE_CHECKING:
    from backend.core.configuration import ConfigurationManager


@dataclass
class DynamicPrediction:
    """Result of a dynamic gesture recognition pass."""

    prediction_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    event_name: str = "UNKNOWN"   # e.g. "SWIPE_LEFT", "ZOOM_IN", …
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def is_valid(self) -> bool:
        return self.event_name != "UNKNOWN"


class DynamicGestureRecognizer:
    """Wraps MainController for use inside the HGRIA pipeline.

    Accepts a BGR numpy array (``frame.bgr_data``) and returns an optional
    ``DynamicPrediction`` when a dynamic event is detected.

    The underlying OC-SORT tracker is stateful: call ``process_frame`` once
    per pipeline tick, regardless of whether a command will be generated.
    """

    def __init__(self, config: "ConfigurationManager") -> None:
        """
        Initialise models and tracker.

        Args:
            config: HGRIA configuration – reads the ``dynamic_gestures``
                    section that must be present in ``config.json``.
        """
        dg_cfg = config.dynamic_gestures
        detection_model = dg_cfg.detection_model_path
        classification_model = dg_cfg.classification_model_path

        if not os.path.exists(detection_model):
            raise FileNotFoundError(
                f"Dynamic gesture detection model not found: {detection_model}"
            )
        if not os.path.exists(classification_model):
            raise FileNotFoundError(
                f"Dynamic gesture classification model not found: {classification_model}"
            )

        from backend.pipeline.dynamic.main_controller import MainController

        self._controller = MainController(
            detection_model=detection_model,
            classification_model=classification_model,
            max_age=dg_cfg.max_age,
            min_hits=dg_cfg.min_hits,
            iou_threshold=dg_cfg.iou_threshold,
            maxlen=dg_cfg.maxlen,
            min_frames=dg_cfg.min_frames,
        )

    def process_frame(self, bgr_frame: np.ndarray) -> Optional[DynamicPrediction]:
        """Process one BGR frame and return a prediction if an event fired.

        Args:
            bgr_frame: Raw BGR numpy array from the camera.

        Returns:
            ``DynamicPrediction`` when an event is detected, ``None`` otherwise.
        """
        # MainController.__call__ returns (bboxes, ids, labels) or (None, None, None)
        _bboxes, _ids, _labels = self._controller(bgr_frame)

        event = self._collect_events()
        if event is None:
            return None

        return DynamicPrediction(event_name=event.name)

    def _collect_events(self) -> Optional[object]:
        """Poll all active tracks for a newly fired event and consume it.

        For drag-type events (DRAG, DRAG2, DRAG3) the action persists until a
        matching DROP fires, so we only emit the event once per state change by
        tracking what was last emitted per track.

        Returns:
            The first ``Event`` enum value found, or ``None``.
        """
        from backend.pipeline.dynamic.utils import Event

        # One-shot events: consume immediately by resetting to None.
        ONE_SHOT_EVENTS = {
            Event.SWIPE_LEFT, Event.SWIPE_RIGHT, Event.SWIPE_UP, Event.SWIPE_DOWN,
            Event.SWIPE_LEFT2, Event.SWIPE_RIGHT2, Event.SWIPE_UP2, Event.SWIPE_DOWN2,
            Event.SWIPE_LEFT3, Event.SWIPE_RIGHT3, Event.SWIPE_UP3, Event.SWIPE_DOWN3,
            Event.FAST_SWIPE_UP, Event.FAST_SWIPE_DOWN,
            Event.ZOOM_IN, Event.ZOOM_OUT,
            Event.DROP, Event.DROP2, Event.DROP3,
            Event.TAP, Event.DOUBLE_TAP,
        }
        # Continuous events: emit once when state enters, then wait for DROP.
        CONTINUOUS_EVENTS = {Event.DRAG, Event.DRAG2, Event.DRAG3}

        if not hasattr(self, "_last_emitted"):
            self._last_emitted: dict = {}

        for i, track in enumerate(self._controller.tracks):
            deque = track["hands"]
            action = deque.action
            if action is None or action == Event.UNKNOWN:
                self._last_emitted.pop(i, None)
                continue

            if action in ONE_SHOT_EVENTS:
                deque.action = None
                return action

            if action in CONTINUOUS_EVENTS:
                if self._last_emitted.get(i) != action:
                    self._last_emitted[i] = action
                    return action
                # Already emitted this drag state – wait for drop

        return None
