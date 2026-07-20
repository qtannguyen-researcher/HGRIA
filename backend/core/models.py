"""Core data models for the HGRIA hand gesture recognition system."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
import uuid


@dataclass
class LandmarkPoint:
    """A single hand landmark point from MediaPipe Hands."""
    index: int                      # 0–20 (MediaPipe landmark index)
    x: float                        # Normalized [0.0, 1.0]
    y: float                        # Normalized [0.0, 1.0]
    z: float                        # Relative depth
    px: int                         # Pixel x coordinate
    py: int                         # Pixel y coordinate
    low_confidence: bool = False


@dataclass
class BoundingBox:
    """Axis-aligned bounding box enclosing all hand landmarks."""
    x_min: float
    y_min: float
    x_max: float
    y_max: float

    def width(self) -> float:
        return self.x_max - self.x_min

    def height(self) -> float:
        return self.y_max - self.y_min

    def diagonal(self) -> float:
        return (self.width() ** 2 + self.height() ** 2) ** 0.5

    def area(self) -> float:
        return self.width() * self.height()


@dataclass
class Landmark:
    """Complete hand landmark set with 21 MediaPipe points."""
    hand_id: str                            # UUID4
    handedness: str                         # 'Left' or 'Right'
    detection_confidence: float
    points: List[LandmarkPoint]             # Always 21 points
    bounding_box: BoundingBox
    palm_center: Tuple[float, float]
    low_confidence_indices: List[int] = field(default_factory=list)

    def get_point(self, index: int) -> LandmarkPoint:
        """Return the landmark point at the given index."""
        return self.points[index]

    def distance(self, idx_a: int, idx_b: int) -> float:
        """Compute Euclidean distance between two landmark points."""
        a, b = self.points[idx_a], self.points[idx_b]
        return ((a.x - b.x) ** 2 + (a.y - b.y) ** 2) ** 0.5

    def is_finger_extended(self, tip_idx: int, pip_idx: int) -> bool:
        """Return True if the finger at tip_idx is extended above pip_idx."""
        return self.points[tip_idx].y < self.points[pip_idx].y


@dataclass
class Frame:
    """A single video frame with metadata."""
    frame_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    bgr_data=None  # Will be set to np.ndarray at runtime
    rgb_data=None  # Will be set to np.ndarray at runtime
    timestamp: datetime = field(default_factory=datetime.utcnow)
    width: int = 640
    height: int = 480
    blur_score: float = 0.0      # Laplacian variance; higher = sharper

    def is_valid(self) -> bool:
        """Return False when bgr_data is None or blur_score <= 0."""
        return self.bgr_data is not None and self.blur_score > 0


@dataclass
class Prediction:
    """A gesture classification result."""
    prediction_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    gesture_name: str = "UNKNOWN"
    confidence: float = 0.0
    raw_scores: Dict[str, float] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.utcnow)
    is_filtered: bool = False
    filter_reason: str = ""


@dataclass
class Command:
    """A command to be transmitted to the frontend."""
    command_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str = ""
    gesture_name: str = ""
    command_type: str = "NONE"  # MOVE | ACTION | UI | SYSTEM | CUSTOM | NONE
    command_value: dict = field(default_factory=dict)
    confidence: float = 0.0
    timestamp: datetime = field(default_factory=datetime.utcnow)
    transmitted_at: Optional[datetime] = None

    def to_dict(self) -> dict:
        """Serialize to a JSON-safe dict with ISO-8601 UTC timestamp."""
        return {
            "command_id": self.command_id,
            "session_id": self.session_id,
            "gesture_name": self.gesture_name,
            "command_type": self.command_type,
            "command_value": self.command_value,
            "confidence": self.confidence,
            "timestamp": self.timestamp.isoformat() + "Z",
        }


@dataclass
class Session:
    """Session tracking and statistics."""
    session_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    started_at: datetime = field(default_factory=datetime.utcnow)
    commands_sent: int = 0
    gesture_counts: Dict[str, int] = field(default_factory=dict)
    avg_latency_ms: float = 0.0
    pipeline_state: str = "Idle"

    def record_command(self, cmd: Command) -> None:
        """Increment commands_sent and update gesture_counts."""
        self.commands_sent += 1
        self.gesture_counts[cmd.gesture_name] = \
            self.gesture_counts.get(cmd.gesture_name, 0) + 1
