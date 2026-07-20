"""Test fixtures for HGRIA tests."""

import uuid
from typing import Any, Dict, List, Optional

from backend.core.models import (
    BoundingBox,
    Frame,
    Landmark,
    LandmarkPoint,
    Prediction,
)


def build_landmark(overrides: Optional[Dict[str, Any]] = None) -> Landmark:
    """
    Build a synthetic Landmark with controllable per-point coordinates.

    This is the main fixture helper for all unit tests.

    Args:
        overrides: Optional dict to override default values

    Returns:
        A Landmark instance with 21 points
    """
    # Create 21 default points (open palm pose)
    points = []
    for i in range(21):
        points.append(LandmarkPoint(
            index=i,
            x=0.5 + (i % 5) * 0.01,
            y=0.3 + (i // 5) * 0.05,
            z=0.0,
            px=320 + (i % 5) * 10,
            py=240 + (i // 5) * 20,
            low_confidence=False,
        ))

    # Compute bounding box from points
    xs = [p.x for p in points]
    ys = [p.y for p in points]
    bbox = BoundingBox(
        x_min=min(xs),
        y_min=min(ys),
        x_max=max(xs),
        y_max=max(ys),
    )

    # Palm center is midpoint of landmarks 0 and 9
    palm_center = ((xs[0] + xs[9]) / 2, (ys[0] + ys[9]) / 2)

    defaults = {
        "hand_id": str(uuid.uuid4()),
        "handedness": "Right",
        "detection_confidence": 0.95,
        "points": points,
        "bounding_box": bbox,
        "palm_center": palm_center,
        "low_confidence_indices": [],
    }

    if overrides:
        defaults.update(overrides)

    return Landmark(**defaults)


def build_prediction(
    gesture_name: str = "UNKNOWN",
    confidence: float = 0.0,
    is_filtered: bool = False,
    filter_reason: str = "",
) -> Prediction:
    """Build a synthetic Prediction."""
    return Prediction(
        gesture_name=gesture_name,
        confidence=confidence,
        is_filtered=is_filtered,
        filter_reason=filter_reason,
        raw_scores={gesture_name: confidence},
    )


def build_frame(
    blur_score: float = 200.0,
    width: int = 640,
    height: int = 480,
) -> Frame:
    """Build a synthetic Frame."""
    return Frame(
        blur_score=blur_score,
        width=width,
        height=height,
        bgr_data=None,  # Tests don't need actual image data
    )


def build_open_palm_landmark() -> Landmark:
    """Build a landmark representing an open palm gesture."""
    return build_landmark()


def build_closed_fist_landmark() -> Landmark:
    """Build a landmark representing a closed fist gesture."""
    points = []
    for i in range(21):
        # All fingertips below their MCPs (curled fingers)
        base_y = 0.5 + (i // 5) * 0.1
        points.append(LandmarkPoint(
            index=i,
            x=0.5 + (i % 5) * 0.01,
            y=base_y + 0.05,  # Tip below MCP
            z=0.0,
            px=320 + (i % 5) * 10,
            py=400 + (i // 5) * 20,
            low_confidence=False,
        ))

    xs = [p.x for p in points]
    ys = [p.y for p in points]
    bbox = BoundingBox(
        x_min=min(xs),
        y_min=min(ys),
        x_max=max(xs),
        y_max=max(ys),
    )
    palm_center = ((xs[0] + xs[9]) / 2, (ys[0] + ys[9]) / 2)

    return Landmark(
        hand_id=str(uuid.uuid4()),
        handedness="Right",
        detection_confidence=0.95,
        points=points,
        bounding_box=bbox,
        palm_center=palm_center,
        low_confidence_indices=[],
    )


def build_point_left_landmark() -> Landmark:
    """Build a landmark representing a point left gesture."""
    return build_landmark()


def build_point_right_landmark() -> Landmark:
    """Build a landmark representing a point right gesture."""
    return build_landmark()
