"""Tests for CooldownManager."""

import time

import pytest

from backend.pipeline.cooldown import CooldownManager


class TestCooldownManager:
    """Tests for the cooldown manager."""

    def test_first_call_returns_partial(self):
        """First call for a gesture always returns the partial command."""
        class MockConfig:
            gesture_cooldowns_ms = {
                "open_palm": 500,
                "closed_fist": 500,
            }

        cm = CooldownManager(MockConfig())
        result = cm.check("open_palm", 0.9)

        assert result is not None
        assert result["gesture_name"] == "open_palm"
        assert result["confidence"] == 0.9

    def test_second_call_within_cooldown_returns_none(self):
        """Second call within cooldown period returns None."""
        class MockConfig:
            gesture_cooldowns_ms = {"open_palm": 500}

        cm = CooldownManager(MockConfig())

        # First call
        cm.check("open_palm", 0.9)

        # Immediate second call - should be blocked
        result = cm.check("open_palm", 0.9)
        assert result is None

    def test_call_after_cooldown_returns_partial(self):
        """Call after cooldown period expires returns the partial command."""
        class MockConfig:
            gesture_cooldowns_ms = {"open_palm": 100}  # 100ms cooldown

        cm = CooldownManager(MockConfig())

        # First call
        cm.check("open_palm", 0.9)

        # Wait for cooldown
        time.sleep(0.15)

        # Should pass now
        result = cm.check("open_palm", 0.85)
        assert result is not None
        assert result["gesture_name"] == "open_palm"

    def test_per_gesture_cooldown_respected(self):
        """Different gestures have independent cooldowns."""
        class MockConfig:
            gesture_cooldowns_ms = {
                "open_palm": 500,
                "closed_fist": 1000,
            }

        cm = CooldownManager(MockConfig())

        # Call open_palm
        cm.check("open_palm", 0.9)

        # closed_fist should still be available (different gesture)
        result = cm.check("closed_fist", 0.9)
        assert result is not None

    def test_unknown_gesture_uses_default_cooldown(self):
        """Unknown gesture uses 500ms default cooldown."""
        class MockConfig:
            gesture_cooldowns_ms = {"open_palm": 500}

        cm = CooldownManager(MockConfig())

        # First call for unknown gesture
        cm.check("unknown_gesture", 0.9)

        # Should be blocked immediately (default 500ms)
        result = cm.check("unknown_gesture", 0.9)
        assert result is None

    def test_reset_clears_cooldown(self):
        """reset() clears cooldown for a gesture."""
        class MockConfig:
            gesture_cooldowns_ms = {"open_palm": 500}

        cm = CooldownManager(MockConfig())

        # First call
        cm.check("open_palm", 0.9)

        # Reset
        cm.reset("open_palm")

        # Should pass now
        result = cm.check("open_palm", 0.9)
        assert result is not None


# ===== Test: Cooldown monotonicity =====

class TestCooldownMonotonicity:
    """Property 4: Cooldown is monotonic."""

    def test_no_call_within_cooldown_window(self):
        """After first emission, calls within cooldown window return None."""
        class MockConfig:
            gesture_cooldowns_ms = {"open_palm": 200}

        cm = CooldownManager(MockConfig())

        # First call passes
        first = cm.check("open_palm", 1.0)
        assert first is not None

        # Calls within 200ms window return None
        for i in range(1, 200, 20):
            time.sleep(0.02)
            result = cm.check("open_palm", 1.0)
            assert result is None, f"Call at {i}ms should be blocked"
