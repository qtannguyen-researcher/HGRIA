"""Tests for NoiseFilter and TemporalFilter."""

import pytest
from backend.core.models import Prediction
from backend.pipeline.filter import NoiseFilter, TemporalFilter
from tests.fixtures import build_frame, build_landmark, build_prediction


# ===== Test: NoiseFilter =====

class TestNoiseFilter:
    """Tests for the noise filter."""

    def test_blur_reject(self):
        """Frame with low blur_score is filtered."""
        lm = build_landmark()
        frame = build_frame(blur_score=50.0)  # Below default threshold of 100
        pred = build_prediction("open_palm", 0.9)

        # Create a mock config
        class MockConfig:
            class GestureRecognition:
                noise_filter_blur_threshold = 100
            gesture_recognition = GestureRecognition()

        nf = NoiseFilter(MockConfig())
        result = nf.filter(pred, lm, frame)

        assert result.is_filtered is True
        assert "blurry_frame" in result.filter_reason

    def test_landmark_count_reject(self):
        """Prediction with too many low-confidence landmarks is filtered."""
        lm = build_landmark({
            "low_confidence_indices": [0, 1, 2, 3, 4],  # 5 > 3
        })
        frame = build_frame(blur_score=200.0)
        pred = build_prediction("open_palm", 0.9)

        class MockConfig:
            class GestureRecognition:
                noise_filter_blur_threshold = 100
            gesture_recognition = GestureRecognition()

        nf = NoiseFilter(MockConfig())
        result = nf.filter(pred, lm, frame)

        assert result.is_filtered is True
        assert "low_confidence" in result.filter_reason

    def test_hand_too_small_reject(self):
        """Prediction with tiny bounding box is filtered."""
        from backend.core.models import BoundingBox

        lm = build_landmark({
            "bounding_box": BoundingBox(x_min=0.4, y_min=0.4, x_max=0.41, y_max=0.41),  # area = 0.0001 < 0.05
        })
        frame = build_frame(blur_score=200.0)
        pred = build_prediction("open_palm", 0.9)

        class MockConfig:
            class GestureRecognition:
                noise_filter_blur_threshold = 100
            gesture_recognition = GestureRecognition()

        nf = NoiseFilter(MockConfig())
        result = nf.filter(pred, lm, frame)

        assert result.is_filtered is True
        assert "hand_too_small" in result.filter_reason

    def test_pass_through(self):
        """Good quality prediction passes through unchanged."""
        lm = build_landmark()
        frame = build_frame(blur_score=200.0)
        pred = build_prediction("open_palm", 0.9)

        class MockConfig:
            class GestureRecognition:
                noise_filter_blur_threshold = 100
            gesture_recognition = GestureRecognition()

        nf = NoiseFilter(MockConfig())
        result = nf.filter(pred, lm, frame)

        assert result.is_filtered is False
        assert result.filter_reason == ""


# ===== Test: TemporalFilter =====

class TestTemporalFilter:
    """Tests for the temporal (majority-vote) filter."""

    def test_majority_vote_found(self):
        """Majority of identical gestures is returned."""
        class MockConfig:
            class GestureRecognition:
                smoothing_window_size = 5
            gesture_recognition = GestureRecognition()

        tf = TemporalFilter(MockConfig())

        for _ in range(3):
            pred = build_prediction("open_palm", 0.9)
            result = tf.update(pred)

        assert result == "open_palm"

    def test_no_majority_returns_unknown(self):
        """No majority of any gesture returns UNKNOWN."""
        class MockConfig:
            class GestureRecognition:
                smoothing_window_size = 5
            gesture_recognition = GestureRecognition()

        tf = TemporalFilter(MockConfig())

        # Add 3 different gestures
        for gesture in ["open_palm", "closed_fist", "point_left"]:
            pred = build_prediction(gesture, 0.9)
            tf.update(pred)

        # Only 2 more to fill window of 5, no majority yet
        tf.update(build_prediction("point_right", 0.9))
        tf.update(build_prediction("thumb_up", 0.9))

        result = tf.update(build_prediction("victory", 0.9))
        assert result == "UNKNOWN"

    def test_window_respects_size(self):
        """Window size is respected."""
        class MockConfig:
            class GestureRecognition:
                smoothing_window_size = 3
            gesture_recognition = GestureRecognition()

        tf = TemporalFilter(MockConfig())
        assert tf.window_size == 3

    def test_reset_clears_buffer(self):
        """reset() clears the buffer."""
        class MockConfig:
            class GestureRecognition:
                smoothing_window_size = 5
            gesture_recognition = GestureRecognition()

        tf = TemporalFilter(MockConfig())

        for _ in range(5):
            pred = build_prediction("open_palm", 0.9)
            tf.update(pred)

        tf.reset()

        # After reset, should return UNKNOWN until new majority forms
        result = tf.update(build_prediction("closed_fist", 0.9))
        assert result == "UNKNOWN"


# ===== Test: TemporalFilter determinism =====

class TestTemporalFilterDeterminism:
    """Property 3: Identical sequence always gives same result."""

    def test_stable_gesture_always_returns(self):
        """Same gesture repeated window_size times always returns that gesture."""
        class MockConfig:
            class GestureRecognition:
                smoothing_window_size = 5
            gesture_recognition = GestureRecognition()

        tf = TemporalFilter(MockConfig())

        for _ in range(5):
            pred = build_prediction("thumb_up", 0.9)
            result = tf.update(pred)

        assert result == "thumb_up"
