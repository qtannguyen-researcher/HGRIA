"""Landmark extractor for parsing MediaPipe hand landmarks."""

from typing import Any, List, Tuple

import uuid

from backend.core.models import BoundingBox, Landmark, LandmarkPoint


class LandmarkExtractor:
    """Extracts structured Landmark data from MediaPipe hand detection results."""

    PADDING_PX = 10

    def extract(self, raw: Tuple[Any, Any]) -> Landmark:
        """
        Extract a Landmark from raw MediaPipe detection results.

        Args:
            raw: Tuple of (mp_landmarks, handedness_info)

        Returns:
            Fully populated Landmark dataclass
        """
        mp_landmarks, handedness_info = raw

        h_label = handedness_info.classification[0].label
        h_conf = handedness_info.classification[0].score

        points: List[LandmarkPoint] = []
        xs: List[float] = []
        ys: List[float] = []

        for i, lm in enumerate(mp_landmarks.landmark):
            low_conf = lm.visibility < 0.5
            points.append(LandmarkPoint(
                index=i,
                x=lm.x,
                y=lm.y,
                z=lm.z,
                px=0,  # Pixel coords computed later by renderer if needed
                py=0,
                low_confidence=low_conf
            ))
            xs.append(lm.x)
            ys.append(lm.y)

        # Compute bounding box from all 21 normalized coordinates
        bbox = BoundingBox(
            x_min=min(xs),
            y_min=min(ys),
            x_max=max(xs),
            y_max=max(ys)
        )

        # Palm center is midpoint of landmarks 0 and 9 (wrist and middle MCP)
        palm_center: Tuple[float, float] = (
            (xs[0] + xs[9]) / 2,
            (ys[0] + ys[9]) / 2
        )

        # Collect indices of low confidence points
        low_conf_indices = [p.index for p in points if p.low_confidence]

        return Landmark(
            hand_id=str(uuid.uuid4()),
            handedness=h_label,
            detection_confidence=h_conf,
            points=points,
            bounding_box=bbox,
            palm_center=palm_center,
            low_confidence_indices=low_conf_indices,
        )

    def extract_all(self, raw_results: List[Tuple[Any, Any]], dominant_hand: str = "Right") -> List[Landmark]:
        """
        Extract landmarks for all detected hands.

        Args:
            raw_results: List of (mp_landmarks, handedness_info) tuples
            dominant_hand: Preferred hand ("Left" or "Right")

        Returns:
            List of Landmark objects
        """
        landmarks = [self.extract(raw) for raw in raw_results]

        # Filter to dominant hand if multiple hands detected
        dominant = [lm for lm in landmarks if lm.handedness == dominant_hand]
        if dominant:
            return dominant

        return landmarks
