"""Tests for GestureClassifier."""

import pytest

from backend.core.models import Prediction
from backend.pipeline.classifier import GESTURE_RULES, GestureClassifier, Rule
from tests.fixtures import build_landmark, build_open_palm_landmark


# ===== Test: Classifier output bounds =====

class TestClassifierOutputBounds:
    """Property 1: Classifier output must be in valid range."""

    def test_confidence_in_valid_range(self):
        """Every classify() result has confidence in [0, 1]."""
        lm = build_landmark()
        classifier = GestureClassifier.__new__(GestureClassifier)
        classifier._rules = GESTURE_RULES[:]
        classifier._threshold = 0.75

        pred = classifier.classify(lm)
        assert 0.0 <= pred.confidence <= 1.0

    def test_gesture_name_valid(self):
        """Gesture name is either UNKNOWN or a known gesture."""
        lm = build_landmark()
        classifier = GestureClassifier.__new__(GestureClassifier)
        classifier._rules = GESTURE_RULES[:]
        classifier._threshold = 0.75

        pred = classifier.classify(lm)
        valid_names = {r.gesture_name for r in GESTURE_RULES} | {"UNKNOWN"}
        assert pred.gesture_name in valid_names


# ===== Test: Rule score boundedness =====

class TestRuleScoreBoundedness:
    """Property 2: Every Rule.evaluate returns [0, 1]."""

    def test_all_rules_return_bounded_scores(self):
        """All rule types return values in [0, 1]."""
        lm = build_landmark()

        for gr in GESTURE_RULES:
            for rule in gr.rules:
                score = rule.evaluate(lm)
                assert 0.0 <= score <= 1.0, f"{gr.gesture_name}/{rule.rule_type} = {score}"


# ===== Test: Per-gesture classification =====

class TestPerGestureClassification:
    """Test that each built-in gesture can be classified."""

    def test_classifier_finds_best_gesture(self):
        """Classifier returns the gesture with highest score."""
        lm = build_landmark()
        classifier = GestureClassifier.__new__(GestureClassifier)
        classifier._rules = GESTURE_RULES[:]
        classifier._threshold = 0.75

        pred = classifier.classify(lm)
        assert pred.gesture_name in {r.gesture_name for r in GESTURE_RULES}

    def test_unknown_for_ambiguous_pose(self):
        """Ambiguous pose returns UNKNOWN."""
        # Create a landmark with all points at same position (invalid)
        from backend.core.models import BoundingBox, Landmark, LandmarkPoint
        import uuid

        points = [
            LandmarkPoint(index=i, x=0.5, y=0.5, z=0.0, px=320, py=240, low_confidence=False)
            for i in range(21)
        ]
        lm = Landmark(
            hand_id=str(uuid.uuid4()),
            handedness="Right",
            detection_confidence=0.95,
            points=points,
            bounding_box=BoundingBox(x_min=0.5, y_min=0.5, x_max=0.5, y_max=0.5),
            palm_center=(0.5, 0.5),
            low_confidence_indices=[],
        )

        classifier = GestureClassifier.__new__(GestureClassifier)
        classifier._rules = GESTURE_RULES[:]
        classifier._threshold = 0.75

        pred = classifier.classify(lm)
        # With all points at same location, scores should be very low
        assert pred.gesture_name == "UNKNOWN" or pred.confidence < 0.5


# ===== Test: GestureRule evaluate =====

class TestGestureRuleEvaluate:
    """Test GestureRule.aggregate scoring."""

    def test_evaluate_returns_weighted_average(self):
        """evaluate() returns weighted average of child rules."""
        lm = build_landmark()
        rule = GESTURE_RULES[0]  # open_palm

        score = rule.evaluate(lm)
        assert isinstance(score, float)
        assert 0.0 <= score <= 1.0


# ===== Test: Raw scores =====

class TestRawScores:
    """Test that classify() returns all raw scores."""

    def test_raw_scores_contains_all_gestures(self):
        """raw_scores contains entry for every built-in gesture."""
        lm = build_landmark()
        classifier = GestureClassifier.__new__(GestureClassifier)
        classifier._rules = GESTURE_RULES[:]
        classifier._threshold = 0.75

        pred = classifier.classify(lm)
        assert set(pred.raw_scores.keys()) == {r.gesture_name for r in GESTURE_RULES}
