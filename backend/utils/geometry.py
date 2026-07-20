"""Geometric helper functions for gesture classification."""

import math
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from backend.core.models import Landmark


def finger_distance(lm: "Landmark", a: int, b: int) -> float:
    """
    Compute the Euclidean distance between two landmark points.

    Args:
        lm: Landmark object
        a: Index of first point
        b: Index of second point

    Returns:
        Distance in normalized coordinates
    """
    return lm.distance(a, b)


def finger_angle(lm: "Landmark", a: int, b: int, c: int) -> float:
    """
    Compute the angle at landmark b formed by points a-b-c.

    Args:
        lm: Landmark object
        a: Index of first point
        b: Index of vertex point
        c: Index of third point

    Returns:
        Angle in degrees
    """
    ax, ay = lm.points[a].x, lm.points[a].y
    bx, by = lm.points[b].x, lm.points[b].y
    cx, cy = lm.points[c].x, lm.points[c].y

    # Vectors from b to a and b to c
    ba_x, ba_y = ax - bx, ay - by
    bc_x, bc_y = cx - bx, cy - by

    # Dot product and magnitudes
    dot = ba_x * bc_x + ba_y * bc_y
    mag_ba = math.sqrt(ba_x * ba_x + ba_y * ba_y)
    mag_bc = math.sqrt(bc_x * bc_x + bc_y * bc_y)

    if mag_ba == 0 or mag_bc == 0:
        return 0.0

    cos_angle = dot / (mag_ba * mag_bc)
    cos_angle = max(-1.0, min(1.0, cos_angle))

    return math.degrees(math.acos(cos_angle))


def is_finger_extended(lm: "Landmark", tip_idx: int, pip_idx: int, margin: float = 0.02) -> bool:
    """
    Check if a finger is extended based on tip vs PIP y-position.

    Args:
        lm: Landmark object
        tip_idx: Index of the fingertip
        pip_idx: Index of the PIP joint
        margin: Tolerance margin

    Returns:
        True if finger is extended (tip above PIP)
    """
    return lm.points[tip_idx].y < (lm.points[pip_idx].y - margin)


def is_finger_curled(lm: "Landmark", tip_idx: int, mcp_idx: int, margin: float = 0.02) -> bool:
    """
    Check if a finger is curled based on tip vs MCP y-position.

    Args:
        lm: Landmark object
        tip_idx: Index of the fingertip
        mcp_idx: Index of the MCP joint
        margin: Tolerance margin

    Returns:
        True if finger is curled (tip below MCP)
    """
    return lm.points[tip_idx].y > (lm.points[mcp_idx].y + margin)


def spread_ratio(lm: "Landmark") -> float:
    """
    Compute the spread ratio of the hand.

    Returns:
        Ratio of |INDEX_TIP.x - PINKY_TIP.x| to bounding box width
    """
    index_tip_x = lm.points[8].x
    pinky_tip_x = lm.points[20].x
    spread = abs(index_tip_x - pinky_tip_x)
    bbox_w = lm.bounding_box.width()
    return spread / bbox_w if bbox_w > 0 else 0.0


def pinch_distance(lm: "Landmark", thumb_idx: int = 4, finger_idx: int = 8) -> float:
    """
    Compute normalized pinch distance between thumb and finger.

    Args:
        lm: Landmark object
        thumb_idx: Index of thumb tip (default 4)
        finger_idx: Index of finger tip (default 8 = index)

    Returns:
        Normalized pinch distance
    """
    dist = lm.distance(thumb_idx, finger_idx)
    bbox_diag = lm.bounding_box.diagonal()
    return dist / bbox_diag if bbox_diag > 0 else 1.0
