"""State manager implementing the 8-state FSM for the HGRIA system."""

from enum import Enum
from typing import Callable, Dict, List, Optional, Tuple, Any


class SystemState(str, Enum):
    """Enumeration of all possible system states."""
    IDLE = "Idle"
    SEARCHING = "Searching"
    TRACKING = "Tracking"
    RECOGNIZING = "Recognizing"
    EXECUTING = "Executing"
    PAUSED = "Paused"
    DISCONNECTED = "Disconnected"
    SHUTDOWN = "Shutdown"


# (current_state, event) -> next_state
TRANSITION_TABLE: Dict[Tuple[SystemState, str], SystemState] = {
    (SystemState.IDLE,         "client_connected"):     SystemState.SEARCHING,
    (SystemState.IDLE,         "no_hand_detected"):     SystemState.IDLE,
    (SystemState.IDLE,         "hand_detected"):        SystemState.IDLE,
    (SystemState.IDLE,         "shutdown"):             SystemState.SHUTDOWN,

    (SystemState.SEARCHING,    "hand_detected"):        SystemState.TRACKING,
    (SystemState.SEARCHING,    "client_disconnected"):  SystemState.DISCONNECTED,
    (SystemState.SEARCHING,    "shutdown"):             SystemState.SHUTDOWN,

    (SystemState.TRACKING,     "no_hand_detected"):     SystemState.SEARCHING,
    (SystemState.TRACKING,     "gesture_stable"):       SystemState.RECOGNIZING,
    (SystemState.TRACKING,     "stop_gesture"):         SystemState.PAUSED,
    (SystemState.TRACKING,     "client_disconnected"):  SystemState.DISCONNECTED,
    (SystemState.TRACKING,     "shutdown"):             SystemState.SHUTDOWN,

    (SystemState.RECOGNIZING,  "gesture_changed"):      SystemState.TRACKING,
    (SystemState.RECOGNIZING,  "command_emitted"):      SystemState.EXECUTING,
    (SystemState.RECOGNIZING,  "stop_gesture"):         SystemState.PAUSED,
    (SystemState.RECOGNIZING,  "client_disconnected"):  SystemState.DISCONNECTED,

    (SystemState.EXECUTING,    "command_processed"):    SystemState.TRACKING,
    (SystemState.EXECUTING,    "stop_gesture"):         SystemState.PAUSED,

    (SystemState.PAUSED,       "stop_gesture"):         SystemState.TRACKING,
    (SystemState.PAUSED,       "client_disconnected"):  SystemState.DISCONNECTED,
    (SystemState.PAUSED,       "shutdown"):             SystemState.SHUTDOWN,

    (SystemState.DISCONNECTED, "client_connected"):     SystemState.SEARCHING,
    (SystemState.DISCONNECTED, "max_retries_exceeded"): SystemState.SHUTDOWN,
}


class StateManager:
    """
    Manages system state transitions with an 8-state FSM.

    Validates events against the transition table, logs transitions,
    emits SocketIO events, and invokes registered callbacks.
    """

    def __init__(self, socketio: Any, logger: Any) -> None:
        """
        Initialize the state manager.

        Args:
            socketio: Flask-SocketIO instance
            logger: StructuredLogger instance
        """
        self._state: SystemState = SystemState.IDLE
        self._sio: Any = socketio
        self._log: Any = logger
        self._listeners: List[Callable[[SystemState, SystemState], None]] = []

    @property
    def state(self) -> SystemState:
        """Get the current system state."""
        return self._state

    def register_listener(self, cb: Callable[[SystemState, SystemState], None]) -> None:
        """
        Register a callback to be invoked on every state transition.

        Args:
            cb: Callable accepting (old_state, new_state)
        """
        self._listeners.append(cb)

    def transition(self, event: str) -> bool:
        """
        Attempt to transition to a new state based on the given event.

        Args:
            event: The triggering event name

        Returns:
            True if transition was successful, False otherwise
        """
        key = (self._state, event)
        next_state = TRANSITION_TABLE.get(key)

        if next_state is None:
            self._log.warning(
                "invalid_transition",
                current=self._state.value if hasattr(self._state, 'value') else str(self._state),
                transition_event=event,
                module="state_manager"
            )
            return False

        old = self._state
        self._state = next_state

        # no_hand_detected fires on every frameless frame — suppress entirely.
        # hand_detected and gesture_stable log at INFO only on state change.
        # All other transitions log at INFO unconditionally.
        if old != next_state:
            if event == "no_hand_detected":
                pass  # intentionally silent
            else:
                self._log.info(
                    "state_transition",
                    old=old.value,
                    new=next_state.value,
                    transition_event=event,
                    module="state_manager"
                )

        if self._sio:
            self._sio.emit("system_state_change", {
                "old_state": old.value,
                "new_state": next_state.value
            })

        for cb in self._listeners:
            try:
                cb(old, next_state)
            except Exception:
                pass

        return True

    def get_valid_events(self) -> List[str]:
        """Get list of valid events from the current state."""
        valid = []
        for (state, event), _ in TRANSITION_TABLE.items():
            if state == self._state:
                valid.append(event)
        return valid
