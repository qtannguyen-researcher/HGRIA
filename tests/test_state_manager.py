"""Tests for StateManager."""

import pytest

from backend.core.state_manager import (
    SystemState,
    StateManager,
    TRANSITION_TABLE,
)


class TestStateManager:
    """Tests for the state manager."""

    def test_initial_state_is_idle(self):
        """StateManager starts in IDLE state."""
        sm = StateManager(None, None)
        assert sm.state == SystemState.IDLE

    def test_valid_transition_accepted(self):
        """Valid transition changes state and returns True."""
        sm = StateManager(None, None)

        result = sm.transition("client_connected")
        assert result is True
        assert sm.state == SystemState.SEARCHING

    def test_invalid_transition_rejected(self):
        """Invalid transition returns False and state unchanged."""
        logger = MockLogger()
        sm = StateManager(None, logger)

        original_state = sm.state
        result = sm.transition("invalid_event")
        assert result is False
        assert sm.state == original_state
        assert logger.warning_logged

    def test_listener_notified_on_transition(self):
        """Registered listener is called on valid transition."""
        sm = StateManager(None, None)

        notifications = []
        def listener(old, new):
            notifications.append((old, new))

        sm.register_listener(listener)
        sm.transition("client_connected")

        assert len(notifications) == 1
        assert notifications[0] == (SystemState.IDLE, SystemState.SEARCHING)

    def test_multiple_listeners_notified(self):
        """All registered listeners are called."""
        sm = StateManager(None, None)

        calls = []
        sm.register_listener(lambda old, new: calls.append(1))
        sm.register_listener(lambda old, new: calls.append(2))

        sm.transition("client_connected")

        assert len(calls) == 2
        assert 1 in calls
        assert 2 in calls

    def test_all_valid_events_from_idle(self):
        """IDLE state has correct valid events."""
        sm = StateManager(None, None)
        valid_events = sm.get_valid_events()

        assert "client_connected" in valid_events
        assert "shutdown" in valid_events
        assert "hand_detected" not in valid_events  # Invalid from IDLE


# ===== Test all 21 transitions =====

class TestAllTransitions:
    """Test all 21 defined transitions."""

    def test_transitions_table_completeness(self):
        """TRANSITION_TABLE has exactly 21 entries."""
        assert len(TRANSITION_TABLE) == 21

    def test_idle_transitions(self):
        """IDLE state transitions work correctly."""
        sm = StateManager(None, None)

        sm.transition("client_connected")
        assert sm.state == SystemState.SEARCHING

        sm2 = StateManager(None, None)
        sm2.transition("shutdown")
        assert sm2.state == SystemState.SHUTDOWN

    def test_searching_transitions(self):
        """SEARCHING state transitions work correctly."""
        sm = StateManager(None, None)
        sm.transition("client_connected")  # IDLE -> SEARCHING

        sm.transition("hand_detected")
        assert sm.state == SystemState.TRACKING

        sm2 = StateManager(None, None)
        sm2.transition("client_connected")
        sm2.transition("client_disconnected")
        assert sm2.state == SystemState.DISCONNECTED

    def test_tracking_transitions(self):
        """TRACKING state transitions work correctly."""
        sm = StateManager(None, None)
        # Navigate to TRACKING
        sm.transition("client_connected")
        sm.transition("hand_detected")

        sm.transition("no_hand_detected")
        assert sm.state == SystemState.SEARCHING

        sm.transition("gesture_stable")
        assert sm.state == SystemState.RECOGNIZING

        sm.transition("stop_gesture")
        assert sm.state == SystemState.PAUSED

    def test_recognizing_transitions(self):
        """RECOGNIZING state transitions work correctly."""
        sm = StateManager(None, None)
        sm.transition("client_connected")
        sm.transition("hand_detected")
        sm.transition("gesture_stable")

        sm.transition("command_emitted")
        assert sm.state == SystemState.EXECUTING

    def test_executing_transitions(self):
        """EXECUTING state transitions work correctly."""
        sm = StateManager(None, None)
        sm.transition("client_connected")
        sm.transition("hand_detected")
        sm.transition("gesture_stable")
        sm.transition("command_emitted")

        sm.transition("command_processed")
        assert sm.state == SystemState.TRACKING

        sm.transition("stop_gesture")
        assert sm.state == SystemState.PAUSED

    def test_paused_toggle(self):
        """PAUSED state toggles back to TRACKING on stop_gesture."""
        sm = StateManager(None, None)
        sm.transition("client_connected")
        sm.transition("hand_detected")
        sm.transition("gesture_stable")
        sm.transition("stop_gesture")  # TRACKING -> PAUSED

        sm.transition("stop_gesture")  # PAUSED -> TRACKING (toggle)
        assert sm.state == SystemState.TRACKING

    def test_disconnected_reconnects(self):
        """DISCONNECTED can reconnect to SEARCHING."""
        sm = StateManager(None, None)
        sm.transition("client_connected")
        sm.transition("hand_detected")
        sm.transition("no_hand_detected")
        sm.transition("client_disconnected")

        assert sm.state == SystemState.DISCONNECTED

        sm.transition("client_connected")
        assert sm.state == SystemState.SEARCHING


class MockLogger:
    """Mock logger for testing."""

    def __init__(self):
        self.warning_logged = False
        self.info_logged = False

    def warning(self, event, **kwargs):
        if event == "invalid_transition":
            self.warning_logged = True

    def info(self, event, **kwargs):
        self.info_logged = True
