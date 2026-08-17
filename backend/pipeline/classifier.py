"""Gesture classifier with geometric rules for the HGRIA system."""

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from backend.core.models import Landmark, Prediction
    from backend.core.configuration import ConfigurationManager


# Landmark index constants
WRIST = 0
THUMB_CMC = 1
THUMB_MCP = 2
THUMB_IP = 3
THUMB_TIP = 4
INDEX_MCP = 5
INDEX_PIP = 6
INDEX_DIP = 7
INDEX_TIP = 8
MIDDLE_MCP = 9
MIDDLE_PIP = 10
MIDDLE_DIP = 11
MIDDLE_TIP = 12
RING_MCP = 13
RING_PIP = 14
RING_DIP = 15
RING_TIP = 16
PINKY_MCP = 17
PINKY_PIP = 18
PINKY_DIP = 19
PINKY_TIP = 20


@dataclass
class Rule:
    """One geometric constraint that evaluates to a score in [0, 1]."""
    rule_id: str
    rule_type: str
    parameters: Dict[str, Any]
    weight: float = 1.0

    def evaluate(self, lm: "Landmark") -> float:
        """
        Evaluate this rule against a landmark.

        Returns:
            Score in [0.0, 1.0]
        """
        if self.rule_type == "finger_extended":
            tip = self.parameters["tip"]
            pip = self.parameters["pip"]
            margin = self.parameters.get("margin", 0.02)
            diff = lm.points[pip].y - lm.points[tip].y
            return min(max((diff + margin) / (2 * margin), 0.0), 1.0)

        elif self.rule_type == "finger_curled":
            tip = self.parameters["tip"]
            mcp = self.parameters["mcp"]
            margin = self.parameters.get("margin", 0.02)
            diff = lm.points[tip].y - lm.points[mcp].y
            return min(max((diff + margin) / (2 * margin), 0.0), 1.0)

        elif self.rule_type == "spread_ratio":
            spread = abs(lm.points[INDEX_TIP].x - lm.points[PINKY_TIP].x)
            bbox_w = lm.bounding_box.width()
            ratio = spread / bbox_w if bbox_w > 0 else 0.0
            target = self.parameters["target"]
            tolerance = self.parameters.get("tolerance", 0.05)
            return max(0.0, 1.0 - abs(ratio - target) / tolerance)

        elif self.rule_type == "pinch_distance":
            dist = lm.distance(THUMB_TIP, INDEX_TIP)
            bbox_diag = lm.bounding_box.diagonal()
            norm_dist = dist / bbox_diag if bbox_diag > 0 else 1.0
            threshold = self.parameters.get("threshold", 0.05)
            return max(0.0, 1.0 - norm_dist / threshold)

        elif self.rule_type == "horizontal_direction":
            tip = self.parameters["tip"]
            mcp = self.parameters["mcp"]
            direction = self.parameters["direction"]
            threshold = self.parameters.get("threshold", 0.08)
            diff = lm.points[tip].x - lm.points[mcp].x
            if direction == "left":
                return min(max(-diff / threshold, 0.0), 1.0)
            else:
                return min(max(diff / threshold, 0.0), 1.0)

        elif self.rule_type == "thumb_up":
            diff = lm.points[4].y - lm.points[3].y
            margin = self.parameters.get("margin", 0.03)
            above_wrist = lm.points[WRIST].y - lm.points[THUMB_TIP].y
            score = min(max(diff / margin, 0.0), 1.0)
            wrist_score = 1.0 if above_wrist > 0 else 0.0
            return score * wrist_score

        elif self.rule_type == "victory_spread_angle":
            ix, iy = lm.points[INDEX_TIP].x, lm.points[INDEX_TIP].y
            mx, my = lm.points[MIDDLE_TIP].x, lm.points[MIDDLE_TIP].y
            base_x, base_y = lm.points[INDEX_MCP].x, lm.points[INDEX_MCP].y
            angle_i = math.atan2(iy - base_y, ix - base_x)
            angle_m = math.atan2(my - base_y, mx - base_x)
            spread_deg = abs(math.degrees(angle_m - angle_i))
            min_angle = self.parameters.get("min_angle", 15.0)
            return min(spread_deg / min_angle, 1.0)

        return 0.0


@dataclass
class GestureRule:
    """A collection of rules that together define a gesture."""
    gesture_name: str
    rules: List[Rule]
    confidence_threshold: float = 0.75
    cooldown_ms: int = 500

    def evaluate(self, lm: "Landmark") -> float:
        """
        Evaluate all rules and return weighted average.

        Returns:
            Weighted average score in [0.0, 1.0]
        """
        total_weight = sum(r.weight for r in self.rules)
        if total_weight == 0:
            return 0.0
        weighted_sum = sum(r.evaluate(lm) * r.weight for r in self.rules)
        return weighted_sum / total_weight


# Built-in gesture rule definitions
GESTURE_RULES: List[GestureRule] = [
    GestureRule(
        "open_palm",
        confidence_threshold=0.80,
        rules=[
            Rule("r_op_thumb", "finger_extended", {"tip": 4, "pip": 3}),
            Rule("r_op_index", "finger_extended", {"tip": 8, "pip": 6}),
            Rule("r_op_middle", "finger_extended", {"tip": 12, "pip": 10}),
            Rule("r_op_ring", "finger_extended", {"tip": 16, "pip": 14}),
            Rule("r_op_pinky", "finger_extended", {"tip": 20, "pip": 18}),
            Rule("r_op_spread", "spread_ratio", {"target": 0.45, "tolerance": 0.10}),
        ],
    ),
    GestureRule(
        "closed_fist",
        confidence_threshold=0.82,
        rules=[
            Rule("r_cf_index", "finger_curled", {"tip": 8, "mcp": 5}),
            Rule("r_cf_middle", "finger_curled", {"tip": 12, "mcp": 9}),
            Rule("r_cf_ring", "finger_curled", {"tip": 16, "mcp": 13}),
            Rule("r_cf_pinky", "finger_curled", {"tip": 20, "mcp": 17}),
        ],
    ),
    GestureRule(
        "point_left",
        confidence_threshold=0.78,
        cooldown_ms=300,
        rules=[
            Rule("r_pl_extended", "finger_extended", {"tip": 8, "pip": 6}),
            Rule("r_pl_middle", "finger_curled", {"tip": 12, "mcp": 9}),
            Rule("r_pl_ring", "finger_curled", {"tip": 16, "mcp": 13}),
            Rule("r_pl_pinky", "finger_curled", {"tip": 20, "mcp": 17}),
            Rule("r_pl_dir", "horizontal_direction", {"tip": 8, "mcp": 5, "direction": "left", "threshold": 0.08}, weight=2.0),
        ],
    ),
    GestureRule(
        "point_right",
        confidence_threshold=0.78,
        cooldown_ms=300,
        rules=[
            Rule("r_pr_extended", "finger_extended", {"tip": 8, "pip": 6}),
            Rule("r_pr_middle", "finger_curled", {"tip": 12, "mcp": 9}),
            Rule("r_pr_ring", "finger_curled", {"tip": 16, "mcp": 13}),
            Rule("r_pr_pinky", "finger_curled", {"tip": 20, "mcp": 17}),
            Rule("r_pr_dir", "horizontal_direction", {"tip": 8, "mcp": 5, "direction": "right", "threshold": 0.08}, weight=2.0),
        ],
    ),
    GestureRule(
        "thumb_up",
        confidence_threshold=0.80,
        rules=[
            Rule("r_tu_thumb", "thumb_up", {"margin": 0.03}, weight=2.0),
            Rule("r_tu_index", "finger_curled", {"tip": 8, "mcp": 5}),
            Rule("r_tu_middle", "finger_curled", {"tip": 12, "mcp": 9}),
            Rule("r_tu_ring", "finger_curled", {"tip": 16, "mcp": 13}),
            Rule("r_tu_pinky", "finger_curled", {"tip": 20, "mcp": 17}),
        ],
    ),
    GestureRule(
        "victory",
        confidence_threshold=0.80,
        rules=[
            Rule("r_vc_index", "finger_extended", {"tip": 8, "pip": 6}),
            Rule("r_vc_middle", "finger_extended", {"tip": 12, "pip": 10}),
            Rule("r_vc_ring", "finger_curled", {"tip": 16, "mcp": 13}),
            Rule("r_vc_pinky", "finger_curled", {"tip": 20, "mcp": 17}),
            Rule("r_vc_angle", "victory_spread_angle", {"min_angle": 15.0}, weight=2.0),
        ],
    ),
    GestureRule(
        "stop",
        confidence_threshold=0.78,
        cooldown_ms=1000,
        rules=[
            Rule("r_st_index", "finger_extended", {"tip": 8, "pip": 6}),
            Rule("r_st_middle", "finger_extended", {"tip": 12, "pip": 10}),
            Rule("r_st_ring", "finger_extended", {"tip": 16, "pip": 14}),
            Rule("r_st_pinky", "finger_extended", {"tip": 20, "pip": 18}),
            Rule("r_st_spread", "spread_ratio", {"target": 0.45, "tolerance": 0.10}, weight=2.0),
        ],
    ),
    GestureRule(
        "pinch",
        confidence_threshold=0.82,
        cooldown_ms=400,
        rules=[
            Rule("r_pc_pinch", "pinch_distance", {"threshold": 0.06}, weight=3.0),
        ],
    ),
    GestureRule(
        "ok",
        confidence_threshold=0.82,
        rules=[
            Rule("r_ok_pinch", "pinch_distance", {"threshold": 0.06}, weight=2.0),
            Rule("r_ok_middle", "finger_extended", {"tip": 12, "pip": 10}),
            Rule("r_ok_ring", "finger_extended", {"tip": 16, "pip": 14}),
            Rule("r_ok_pinky", "finger_extended", {"tip": 20, "pip": 18}),
        ],
    ),
]


class GestureClassifier:
    """Classifies hand gestures using geometric rules."""

    def __init__(self, config: "ConfigurationManager") -> None:
        """
        Initialize the gesture classifier.

        Args:
            config: Configuration object
        """
        self._rules = GESTURE_RULES[:]
        self._threshold = config.gesture_recognition.confidence_threshold

        # Merge custom gestures from config
        for cg in config.custom_gestures:
            self._rules.append(self._parse_custom(cg))

    def _parse_custom(self, gesture_def: Dict[str, Any]) -> GestureRule:
        """Parse a custom gesture definition from config."""
        rules = []
        for rule_def in gesture_def.get("rules", []):
            rules.append(Rule(
                rule_id=rule_def.get("id", "custom"),
                rule_type=rule_def["type"],
                parameters=rule_def.get("parameters", {}),
                weight=rule_def.get("weight", 1.0),
            ))
        return GestureRule(
            gesture_name=gesture_def["name"],
            rules=rules,
            confidence_threshold=gesture_def.get("confidence_threshold", 0.75),
            cooldown_ms=gesture_def.get("cooldown_ms", 500),
        )

    def classify(self, lm: "Landmark") -> "Prediction":
        """
        Classify a hand gesture from landmark data.

        Args:
            lm: Landmark object

        Returns:
            Prediction with gesture_name and confidence
        """
        from backend.core.models import Prediction

        raw_scores: Dict[str, float] = {}
        for rule in self._rules:
            raw_scores[rule.gesture_name] = rule.evaluate(lm)

        best_name = max(raw_scores, key=raw_scores.get)
        best_score = raw_scores[best_name]

        per_gesture_threshold = next(
            (r.confidence_threshold for r in self._rules if r.gesture_name == best_name),
            self._threshold
        )

        if best_score < per_gesture_threshold:
            return Prediction(gesture_name="UNKNOWN", raw_scores=raw_scores)

        return Prediction(
            gesture_name=best_name,
            confidence=best_score,
            raw_scores=raw_scores,
        )
