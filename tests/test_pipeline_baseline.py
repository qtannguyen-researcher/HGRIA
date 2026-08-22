"""Phase 1 baseline: static-only path, shared Session, evaluation guards."""

import json
import os
import queue
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from backend.core.configuration import ConfigurationManager
from backend.core.models import Session
from backend.core.state_manager import StateManager
from backend.pipeline.pipeline_runner import PipelineRunner


def _runner(config, session=None):
    """Build a PipelineRunner without opening a camera or MediaPipe."""
    return PipelineRunner(
        config,
        queue.Queue(maxsize=20),
        StateManager(None, None),
        camera=MagicMock(),
        detector=MagicMock(),
        logger=None,
        socketio=None,
        session=session,
    )


class TestDynamicPathRespectsEnabledFlag:
    """dynamic_gestures.enabled=false must not construct the ONNX recognizer."""

    def test_committed_config_does_not_init_onnx(self):
        config = ConfigurationManager("config/config.json")
        assert config.is_dynamic_gestures_enabled() is False
        with patch(
            "backend.pipeline.dynamic_recognizer.DynamicGestureRecognizer"
        ) as mock_cls:
            runner = _runner(config)
            mock_cls.assert_not_called()
        assert runner._dynamic_recognizer is None

    def test_enabled_false_skips_init_even_when_section_present(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"dynamic_gestures": {"enabled": False}}, f)
            f.flush()
            config = ConfigurationManager(f.name)
            os.unlink(f.name)

        with patch(
            "backend.pipeline.dynamic_recognizer.DynamicGestureRecognizer"
        ) as mock_cls:
            runner = _runner(config)
            mock_cls.assert_not_called()
        assert runner._dynamic_recognizer is None


class TestSharedSession:
    """SystemOrchestrator, PipelineRunner, CommandGenerator, and Flask share one Session."""

    def test_pipeline_uses_injected_session(self):
        config = ConfigurationManager("config/config.json")
        session = Session()
        runner = _runner(config, session=session)
        assert runner.session is session

        runner._command_generator.generate(
            {"gesture_name": "point_left", "confidence": 0.9}
        )
        assert session.commands_sent == 1
        assert session.gesture_counts.get("point_left") == 1

    def test_pipeline_command_visible_on_flask_session_api(self):
        from backend.app import create_app

        config = ConfigurationManager("config/config.json")
        session = Session()
        runner = _runner(config, session=session)

        app, _ = create_app(
            config, session, StateManager(None, None), queue.Queue(maxsize=20), None
        )
        app.config["TESTING"] = True
        client = app.test_client()

        runner._command_generator.generate(
            {"gesture_name": "thumb_up", "confidence": 0.88}
        )
        data = client.get("/api/session").get_json()
        assert data["session_id"] == session.session_id
        assert data["commands_sent"] == 1
        assert data["gesture_counts"].get("thumb_up") == 1
        assert runner.session is session


class TestEvaluationModeClientGuards:
    """Source-level check that evaluation mode disables client injection paths."""

    def test_websocket_ui_bypass_gated(self):
        text = Path("frontend/js/websocket.js").read_text(encoding="utf-8")
        assert "UI_BYPASS" in text
        assert "isEvaluationMode(this.#gameState)" in text

    def test_keyboard_injection_gated(self):
        text = Path("frontend/js/main.js").read_text(encoding="utf-8")
        assert "KEYBOARD_MAP" in text
        assert "isEvaluationMode(gameState)" in text
        assert "command_type: 'KEYBOARD'" in text

    def test_dbg_inject_gated(self):
        html = Path("frontend/index.html").read_text(encoding="utf-8")
        assert "window._dbgInject" in html
        assert "isEvaluationMode" in html
        assert "blocked: evaluation mode" in html
        # The inject function must return before enqueueCommand when eval is on.
        inject_start = html.index("window._dbgInject = function")
        inject_end = html.index("window._dbgServerEmit = async function")
        inject_fn = html[inject_start:inject_end]
        assert "blocked: evaluation mode" in inject_fn
        assert inject_fn.index("isEvaluationMode") < inject_fn.index("enqueueCommand")

    def test_enqueue_rejects_artificial_commands_in_evaluation(self):
        state = Path("frontend/js/state.js").read_text(encoding="utf-8")
        assert "shouldBlockCommandInjection" in state
        cfg = Path("frontend/js/config.js").read_text(encoding="utf-8")
        assert "function shouldBlockCommandInjection" in cfg
        assert "function isArtificialCommand" in cfg
        assert "DEBUG" in cfg
        assert "KEYBOARD" in cfg
        assert "client_bypass" in cfg
