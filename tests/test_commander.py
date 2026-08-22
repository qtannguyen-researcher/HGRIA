"""Tests for CommandGenerator and CommandTransmitter."""

import uuid
from unittest.mock import MagicMock

import pytest

from backend.core.errors import UnmappedGestureError
from backend.core.models import Command, Session
from backend.pipeline.commander import COMMAND_MAP, CommandGenerator, CommandTransmitter


class TestCommandGenerator:
    """Tests for CommandGenerator."""

    def test_generate_creates_command_with_correct_fields(self):
        """generate() creates Command with all required fields."""
        session = Session()
        config = MagicMock()
        config.custom_gestures = []

        gen = CommandGenerator(config, session)

        partial = {"gesture_name": "open_palm", "confidence": 0.9}
        cmd = gen.generate(partial)

        assert cmd.gesture_name == "open_palm"
        assert cmd.confidence == 0.9
        assert cmd.session_id == session.session_id
        assert cmd.command_type == "MOVE"
        assert cmd.command_value == {"direction": "stop"}

    def test_generate_unmapped_gesture_raises(self):
        """generate() raises UnmappedGestureError for unknown gesture."""
        session = Session()
        config = MagicMock()
        config.custom_gestures = []

        gen = CommandGenerator(config, session)

        partial = {"gesture_name": "unknown_gesture", "confidence": 0.9}
        with pytest.raises(UnmappedGestureError):
            gen.generate(partial)

    def test_command_id_is_unique(self):
        """Each generate() call produces a unique command_id."""
        session = Session()
        config = MagicMock()
        config.custom_gestures = []

        gen = CommandGenerator(config, session)

        ids = set()
        for _ in range(100):
            partial = {"gesture_name": "open_palm", "confidence": 0.9}
            cmd = gen.generate(partial)
            assert cmd.command_id not in ids
            ids.add(cmd.command_id)

    def test_point_left_command_type(self):
        """point_left gesture generates MOVE command."""
        session = Session()
        config = MagicMock()
        config.custom_gestures = []

        gen = CommandGenerator(config, session)

        partial = {"gesture_name": "point_left", "confidence": 0.9}
        cmd = gen.generate(partial)

        assert cmd.command_type == "MOVE"
        assert cmd.command_value == {"direction": "left"}

    def test_thumb_up_command_type(self):
        """thumb_up gesture generates ACTION command."""
        session = Session()
        config = MagicMock()
        config.custom_gestures = []

        gen = CommandGenerator(config, session)

        partial = {"gesture_name": "thumb_up", "confidence": 0.9}
        cmd = gen.generate(partial)

        assert cmd.command_type == "ACTION"
        assert cmd.command_value == {"action": "jump"}

    def test_session_records_command(self):
        """Session.record_command() is called on generate."""
        session = Session()
        config = MagicMock()
        config.custom_gestures = []

        gen = CommandGenerator(config, session)

        assert session.commands_sent == 0

        gen.generate({"gesture_name": "open_palm", "confidence": 0.9})
        assert session.commands_sent == 1
        assert session.gesture_counts.get("open_palm") == 1

        gen.generate({"gesture_name": "closed_fist", "confidence": 0.85})
        assert session.commands_sent == 2
        assert session.gesture_counts.get("closed_fist") == 1

    def test_to_dict_is_json_safe(self):
        """Command.to_dict() returns JSON-serializable dict."""
        session = Session()
        config = MagicMock()
        config.custom_gestures = []

        gen = CommandGenerator(config, session)
        cmd = gen.generate({"gesture_name": "victory", "confidence": 0.95})

        d = cmd.to_dict()

        assert "command_id" in d
        assert "session_id" in d
        assert "gesture_name" in d
        assert "timestamp" in d
        assert "Z" in d["timestamp"]  # ISO-8601 with Z suffix


class TestCommandMap:
    """Tests for COMMAND_MAP."""

    STATIC_GESTURES = {
        "open_palm", "closed_fist", "point_left", "point_right",
        "thumb_up", "victory", "stop", "pinch", "ok",
    }

    DYNAMIC_GESTURES = {
        "SWIPE_LEFT", "SWIPE_RIGHT", "SWIPE_UP", "SWIPE_DOWN",
        "SWIPE_LEFT2", "SWIPE_RIGHT2", "SWIPE_UP2", "SWIPE_DOWN2",
        "SWIPE_LEFT3", "SWIPE_RIGHT3", "SWIPE_UP3", "SWIPE_DOWN3",
        "FAST_SWIPE_UP", "FAST_SWIPE_DOWN",
        "ZOOM_IN", "ZOOM_OUT",
        "DRAG", "DROP", "DRAG2", "DROP2", "DRAG3", "DROP3",
        "TAP", "DOUBLE_TAP",
    }

    def test_all_nine_static_gestures_mapped(self):
        """All 9 built-in static gestures are in COMMAND_MAP."""
        assert self.STATIC_GESTURES.issubset(COMMAND_MAP.keys())

    def test_command_map_includes_dynamic_names(self):
        """Dynamic event names currently in COMMAND_MAP remain mapped.

        The map grew beyond the original 9 static keys; equality against only
        those 9 is an obsolete assertion. This checks the current published set.
        """
        expected = self.STATIC_GESTURES | self.DYNAMIC_GESTURES
        assert set(COMMAND_MAP.keys()) == expected

    def test_command_types_are_valid(self):
        """All command types are valid."""
        valid_types = {"MOVE", "ACTION", "UI", "SYSTEM", "CUSTOM", "NONE"}
        for gesture, mapping in COMMAND_MAP.items():
            assert mapping["command_type"] in valid_types, f"{gesture} has invalid type"


class TestCommandTransmitter:
    """Tests for CommandTransmitter."""

    def test_transmitter_initializes(self):
        """CommandTransmitter can be instantiated."""
        socketio = MagicMock()
        cmd_queue = MagicMock()

        ct = CommandTransmitter(socketio, cmd_queue)
        assert ct is not None

    def test_set_connected(self):
        """set_connected() updates connection state."""
        socketio = MagicMock()
        cmd_queue = MagicMock()

        ct = CommandTransmitter(socketio, cmd_queue)
        ct.set_connected(True)
        ct.set_connected(False)
