"""Tests for StateManager."""

import pytest

from backend.core.state_manager import (
    SystemState,
    StateManager,
    TRANSITION_TABLE,
)


class MockLogger:
    """Mock logger for testing. Production always supplies a logger."""

    def __init__(self):
        self.warning_logged = False
        self.info_logged = False

    def warning(self, event, **kwargs):
        if event == "invalid_transition":
            self.warning_logged = True

    def info(self, event, **kwargs):
        self.info_logged = True


def _sm():
    return StateManager(None, MockLogger())


class TestStateManager:
    """Tests for the state manager."""

    def test_initial_state_is_idle(self):
        """StateManager starts in IDLE state."""
        sm = _sm()
        assert sm.state == SystemState.IDLE

    def test_valid_transition_accepted(self):
        """Valid transition changes state and returns True."""
        sm = _sm()

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
        sm = _sm()

        notifications = []
        def listener(old, new):
            notifications.append((old, new))

        sm.register_listener(listener)
        sm.transition("client_connected")

        assert len(notifications) == 1
        assert notifications[0] == (SystemState.IDLE, SystemState.SEARCHING)

    def test_multiple_listeners_notified(self):
        """All registered listeners are called."""
        sm = _sm()

        calls = []
        sm.register_listener(lambda old, new: calls.append(1))
        sm.register_listener(lambda old, new: calls.append(2))

        sm.transition("client_connected")

        assert len(calls) == 2
        assert 1 in calls
        assert 2 in calls

    def test_all_valid_events_from_idle(self):
        """IDLE state has correct valid events for the current table."""
        sm = _sm()
        valid_events = sm.get_valid_events()

        assert "client_connected" in valid_events
        assert "shutdown" in valid_events
        # Pipeline may emit hand_detected before a client connects; IDLE stays IDLE.
        assert "hand_detected" in valid_events
        assert "no_hand_detected" in valid_events


# ===== Test all defined transitions =====

class TestAllTransitions:
    """Test all currently defined FSM transitions."""

    def test_transitions_table_completeness(self):
        """TRANSITION_TABLE matches the current 8-state FSM (not a stale count).

        The original suite asserted exactly 21 entries. The table now includes
        stay-in-state events (hand_detected, gesture_stable, no_hand_detected)
        used by the live pipeline. Assert the actual key set so accidental
        removals still fail, without requiring a magic number.
        """
        expected = {
            (SystemState.IDLE,         "client_connected"),
            (SystemState.IDLE,         "no_hand_detected"),
            (SystemState.IDLE,         "hand_detected"),
            (SystemState.IDLE,         "shutdown"),
            (SystemState.SEARCHING,    "hand_detected"),
            (SystemState.SEARCHING,    "no_hand_detected"),
            (SystemState.SEARCHING,    "client_disconnected"),
            (SystemState.SEARCHING,    "shutdown"),
            (SystemState.TRACKING,     "hand_detected"),
            (SystemState.TRACKING,     "no_hand_detected"),
            (SystemState.TRACKING,     "gesture_stable"),
            (SystemState.TRACKING,     "stop_gesture"),
            (SystemState.TRACKING,     "client_disconnected"),
            (SystemState.TRACKING,     "shutdown"),
            (SystemState.RECOGNIZING,  "hand_detected"),
            (SystemState.RECOGNIZING,  "gesture_stable"),
            (SystemState.RECOGNIZING,  "gesture_changed"),
            (SystemState.RECOGNIZING,  "command_emitted"),
            (SystemState.RECOGNIZING,  "stop_gesture"),
            (SystemState.RECOGNIZING,  "no_hand_detected"),
            (SystemState.RECOGNIZING,  "client_disconnected"),
            (SystemState.EXECUTING,    "command_processed"),
            (SystemState.EXECUTING,    "stop_gesture"),
            (SystemState.EXECUTING,    "hand_detected"),
            (SystemState.PAUSED,       "stop_gesture"),
            (SystemState.PAUSED,       "client_disconnected"),
            (SystemState.PAUSED,       "shutdown"),
            (SystemState.DISCONNECTED, "client_connected"),
            (SystemState.DISCONNECTED, "max_retries_exceeded"),
        }
        assert set(TRANSITION_TABLE.keys()) == expected

    def test_idle_transitions(self):
        """IDLE state transitions work correctly."""
        sm = _sm()

        sm.transition("client_connected")
        assert sm.state == SystemState.SEARCHING

        sm2 = _sm()
        sm2.transition("shutdown")
        assert sm2.state == SystemState.SHUTDOWN

    def test_searching_transitions(self):
        """SEARCHING state transitions work correctly."""
        sm = _sm()
        sm.transition("client_connected")  # IDLE -> SEARCHING

        sm.transition("hand_detected")
        assert sm.state == SystemState.TRACKING

        sm2 = _sm()
        sm2.transition("client_connected")
        sm2.transition("client_disconnected")
        assert sm2.state == SystemState.DISCONNECTED

    def test_tracking_transitions(self):
        """TRACKING state transitions work correctly (independent instances)."""
        sm = _sm()
        sm.transition("client_connected")
        sm.transition("hand_detected")
        sm.transition("no_hand_detected")
        assert sm.state == SystemState.SEARCHING

        sm2 = _sm()
        sm2.transition("client_connected")
        sm2.transition("hand_detected")
        sm2.transition("gesture_stable")
        assert sm2.state == SystemState.RECOGNIZING

        sm3 = _sm()
        sm3.transition("client_connected")
        sm3.transition("hand_detected")
        sm3.transition("stop_gesture")
        assert sm3.state == SystemState.PAUSED

    def test_recognizing_transitions(self):
        """RECOGNIZING state transitions work correctly."""
        sm = _sm()
        sm.transition("client_connected")
        sm.transition("hand_detected")
        sm.transition("gesture_stable")

        sm.transition("command_emitted")
        assert sm.state == SystemState.EXECUTING

    def test_executing_transitions(self):
        """EXECUTING state transitions work correctly."""
        sm = _sm()
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
        sm = _sm()
        sm.transition("client_connected")
        sm.transition("hand_detected")
        sm.transition("stop_gesture")  # TRACKING -> PAUSED

        sm.transition("stop_gesture")  # PAUSED -> TRACKING (toggle)
        assert sm.state == SystemState.TRACKING

    def test_disconnected_reconnects(self):
        """DISCONNECTED can reconnect to SEARCHING."""
        sm = _sm()
        sm.transition("client_connected")
        sm.transition("hand_detected")
        sm.transition("no_hand_detected")
        sm.transition("client_disconnected")

        assert sm.state == SystemState.DISCONNECTED

        sm.transition("client_connected")
        assert sm.state == SystemState.SEARCHING
