"""Pre-Phase 3 measurement readiness: preview, exit_reason, injection, metadata."""

import json
import os
import queue
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from backend.core.configuration import ConfigurationManager
from backend.core.errors import CameraInitializationError, UnmappedGestureError
from backend.core.models import Frame, Session
from backend.core.state_manager import StateManager
from backend.pipeline.camera import CameraModule, FrameStore
from backend.pipeline.pipeline_runner import PipelineRunner
from backend.utils.instrumentation import (
    EXIT_REASONS,
    ExperimentLogger,
    collect_run_metadata,
    resolve_run_id,
    sidecar_path_for,
)
from tests.fixtures import build_open_palm_landmark


def _config(extra=None, jsonl_path=None, enabled=True):
    data = {
        "instrumentation": {
            "enabled": enabled,
            "jsonl_path": jsonl_path or "logs/instrumentation.jsonl",
            "resource_sample_interval_s": 1.0,
            "run_id": "test-run",
        },
        "gesture_recognition": {
            "smoothing_window_size": 1,
        },
        "gesture_cooldowns_ms": {
            "open_palm": 0,
            "closed_fist": 0,
            "point_left": 0,
            "point_right": 0,
            "thumb_up": 0,
            "victory": 0,
            "stop": 0,
            "pinch": 0,
            "ok": 0,
        },
        "camera": {"colab_mode": True},
        "evaluation": {
            "mode": False,
            "preview_enabled": True,
            "strict_camera": False,
        },
        "dynamic_gestures": {"enabled": False},
    }
    if extra:
        for key, value in extra.items():
            if isinstance(value, dict) and isinstance(data.get(key), dict):
                merged = dict(data[key])
                merged.update(value)
                data[key] = merged
            else:
                data[key] = value
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as handle:
        json.dump(data, handle)
        handle.flush()
        path = handle.name
    try:
        return ConfigurationManager(path)
    finally:
        os.unlink(path)


def _blank_bgr():
    return np.zeros((48, 64, 3), dtype=np.uint8)


def _frame(frame_id=1, blur_score=200.0):
    from backend.utils.instrumentation import mono_now

    t0 = mono_now()
    frame = Frame(
        frame_id=frame_id,
        bgr_data=_blank_bgr(),
        blur_score=blur_score,
        width=64,
        height=48,
    )
    frame.t_capture = t0
    frame.t_server_received = t0
    return frame


def _runner(config, jsonl_path, camera=None, detector=None, socketio=None):
    if camera is None:
        camera = MagicMock()
        camera.capture.return_value = _frame(1)
        camera.get_frame_store.return_value = FrameStore()
    if detector is None:
        detector = MagicMock()
        detector.detect.return_value = []
    logger = ExperimentLogger(jsonl_path, enabled=config.is_instrumentation_enabled())
    state_manager = StateManager(None, MagicMock())
    state_manager.transition("client_connected")
    return PipelineRunner(
        config,
        queue.Queue(maxsize=20),
        state_manager,
        camera=camera,
        detector=detector,
        logger=None,
        socketio=socketio,
        session=Session(),
        experiment_logger=logger,
        resource_sampler=None,
    )


def _hand_runner(config, jsonl_path, blur_score=200.0, socketio=None, frame_ids=None):
    camera = MagicMock()
    ids = frame_ids or [1]
    camera.capture.side_effect = [_frame(i, blur_score=blur_score) for i in ids]
    camera.get_frame_store.return_value = FrameStore()
    detector = MagicMock()
    detector.detect.return_value = [("raw", "hand")]
    runner = _runner(
        config, jsonl_path, camera=camera, detector=detector, socketio=socketio
    )
    runner._extractor.extract_all = MagicMock(return_value=[build_open_palm_landmark()])
    return runner


def _jsonl_records(path):
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines]


class TestPreviewSwitch:
    """Preview can be disabled; default still encodes/emits when socketio is set."""

    def test_preview_enabled_encodes_and_emits(self, tmp_path):
        jsonl_path = str(tmp_path / "preview_on.jsonl")
        config = _config(
            jsonl_path=jsonl_path,
            extra={"evaluation": {"preview_enabled": True}},
        )
        assert config.is_preview_enabled() is True
        socketio = MagicMock()
        runner = _hand_runner(config, jsonl_path, socketio=socketio)
        assert runner._preview_enabled is True
        with patch("cv2.imencode", wraps=__import__("cv2").imencode) as enc:
            assert runner._process_frame() is True
            assert enc.called
        events = [call[0][0] for call in socketio.emit.call_args_list]
        assert "frame_preview" in events
        preview = [
            call[0][1]
            for call in socketio.emit.call_args_list
            if call[0][0] == "frame_preview"
        ]
        assert preview
        assert "image" in preview[0]

    def test_preview_disabled_skips_encode_and_emit(self, tmp_path):
        jsonl_path = str(tmp_path / "preview_off.jsonl")
        config = _config(
            jsonl_path=jsonl_path,
            extra={"evaluation": {"preview_enabled": False}},
        )
        assert config.is_preview_enabled() is False
        socketio = MagicMock()
        runner = _hand_runner(config, jsonl_path, socketio=socketio)
        assert runner._preview_enabled is False
        with patch("cv2.imencode") as enc:
            assert runner._process_frame() is True
            enc.assert_not_called()
        events = [call[0][0] for call in socketio.emit.call_args_list]
        assert "frame_preview" not in events

    def test_preview_on_off_same_recognition(self, tmp_path):
        landmark = build_open_palm_landmark()
        results = []
        commands = []
        for preview in (True, False):
            jsonl_path = str(tmp_path / f"prev_{preview}.jsonl")
            config = _config(
                jsonl_path=jsonl_path,
                extra={"evaluation": {"preview_enabled": preview}},
            )
            socketio = MagicMock()
            runner = _hand_runner(config, jsonl_path, socketio=socketio)
            orig = runner._classifier.classify

            def _capture(lm, _orig=orig, _bucket=results):
                pred = _orig(lm)
                _bucket.append(pred)
                return pred

            runner._classifier.classify = _capture
            assert runner._process_frame() is True
            commands.append(runner._latest_frame_timing.command_emitted)
            commands.append(runner._latest_frame_timing.exit_reason)
            commands.append(runner._latest_frame_timing.gesture)

        assert results[0].gesture_name == results[1].gesture_name
        assert results[0].confidence == results[1].confidence
        assert results[0].raw_scores == results[1].raw_scores
        # command_emitted, exit_reason, gesture identical
        assert commands[0] == commands[3]
        assert commands[1] == commands[4]
        assert commands[2] == commands[5]


class TestExitReason:
    """One recorded exit_reason per processed frame, at the decision point."""

    def test_no_hand(self, tmp_path):
        jsonl_path = str(tmp_path / "no_hand.jsonl")
        config = _config(jsonl_path=jsonl_path)
        runner = _runner(config, jsonl_path)
        assert runner._process_frame() is True
        rec = _jsonl_records(jsonl_path)[0]
        assert rec["exit_reason"] == "no_hand"
        assert rec["command_emitted"] is False
        assert runner.stats["frames_no_hand"] == 1

    def test_noise(self, tmp_path):
        jsonl_path = str(tmp_path / "noise.jsonl")
        config = _config(jsonl_path=jsonl_path)
        runner = _hand_runner(config, jsonl_path, blur_score=1.0)
        assert runner._process_frame() is True
        rec = _jsonl_records(jsonl_path)[0]
        assert rec["exit_reason"] == "noise"
        assert rec["command_emitted"] is False
        assert runner.stats["frames_filtered_noise"] == 1

    def test_temporal(self, tmp_path):
        jsonl_path = str(tmp_path / "temporal.jsonl")
        config = _config(
            jsonl_path=jsonl_path,
            extra={"gesture_recognition": {"smoothing_window_size": 3}},
        )
        runner = _hand_runner(config, jsonl_path)
        assert runner._process_frame() is True
        rec = _jsonl_records(jsonl_path)[0]
        assert rec["exit_reason"] == "temporal"
        assert rec["command_emitted"] is False
        assert runner.stats["frames_filtered_temporal"] == 1

    def test_cooldown(self, tmp_path):
        jsonl_path = str(tmp_path / "cooldown.jsonl")
        # Fixture landmark classifies as a static gesture; raise every static
        # cooldown so the second frame is rate-limited regardless of name.
        high = {
            name: 60_000
            for name in (
                "open_palm",
                "closed_fist",
                "point_left",
                "point_right",
                "thumb_up",
                "victory",
                "stop",
                "pinch",
                "ok",
            )
        }
        config = _config(
            jsonl_path=jsonl_path,
            extra={"gesture_cooldowns_ms": high},
        )
        runner = _hand_runner(config, jsonl_path, frame_ids=[1, 2])
        assert runner._process_frame() is True
        assert runner._process_frame() is True
        records = _jsonl_records(jsonl_path)
        assert records[0]["exit_reason"] == "command"
        assert records[0]["command_emitted"] is True
        assert records[1]["exit_reason"] == "cooldown"
        assert records[1]["command_emitted"] is False
        assert runner.stats["frames_cooldown"] == 1

    def test_unmapped(self, tmp_path):
        jsonl_path = str(tmp_path / "unmapped.jsonl")
        config = _config(jsonl_path=jsonl_path)
        runner = _hand_runner(config, jsonl_path)
        runner._command_generator.generate = MagicMock(
            side_effect=UnmappedGestureError("unknown")
        )
        assert runner._process_frame() is True
        rec = _jsonl_records(jsonl_path)[0]
        assert rec["exit_reason"] == "unmapped"
        assert rec["command_emitted"] is False

    def test_command(self, tmp_path):
        jsonl_path = str(tmp_path / "command.jsonl")
        config = _config(jsonl_path=jsonl_path)
        runner = _hand_runner(config, jsonl_path)
        assert runner._process_frame() is True
        rec = _jsonl_records(jsonl_path)[0]
        assert rec["exit_reason"] == "command"
        assert rec["command_emitted"] is True
        assert rec["gesture"]

    def test_every_category_is_listed(self):
        assert set(EXIT_REASONS) == {
            "no_hand",
            "noise",
            "temporal",
            "cooldown",
            "unmapped",
            "command",
        }


class TestEvaluationIsolation:
    """Evaluation mode blocks artificial command injection; demo still works."""

    def test_test_emit_forbidden_in_evaluation(
        self, test_session, test_state_manager, command_queue
    ):
        from backend.app import create_app

        config = _config(extra={"evaluation": {"mode": True}})
        app, _ = create_app(
            config, test_session, test_state_manager, command_queue, None
        )
        app.config["TESTING"] = True
        client = app.test_client()
        response = client.get("/api/test-emit?gesture=point_left")
        assert response.status_code == 403
        assert response.get_json()["ok"] is False

    def test_test_emit_allowed_in_demo(
        self, test_session, test_state_manager, command_queue
    ):
        from backend.app import create_app

        config = _config(extra={"evaluation": {"mode": False}})
        app, _ = create_app(
            config, test_session, test_state_manager, command_queue, None
        )
        app.config["TESTING"] = True
        client = app.test_client()
        response = client.get("/api/test-emit?gesture=point_left")
        assert response.status_code == 200
        assert response.get_json()["ok"] is True

    def test_debug_reports_evaluation_and_colab(self, tmp_path, test_session, test_state_manager, command_queue):
        from backend.app import create_app

        jsonl_path = str(tmp_path / "dbg.jsonl")
        config = _config(
            jsonl_path=jsonl_path,
            extra={
                "evaluation": {"mode": True, "preview_enabled": False, "strict_camera": True},
                "camera": {"colab_mode": False, "colab_fallback": False},
            },
        )
        runner = _runner(config, jsonl_path)
        app, _ = create_app(
            config, test_session, test_state_manager, command_queue, None
        )
        app.config["TESTING"] = True
        app.config["HG_PIPELINE"] = runner
        data = app.test_client().get("/api/debug").get_json()
        assert data["config"]["colab_mode"] is False
        assert data["config"]["colab_fallback"] is False
        assert data["config"]["evaluation_mode"] is True
        assert data["config"]["preview_enabled"] is False
        assert data["config"]["strict_camera"] is True
        assert data["config"]["opencv_baseline_invalid_if_colab_mode"] is True
        assert data["instrumentation"]["run_id"] == "test-run"


class TestRunMetadata:
    """Sidecar + run_id make copied logs self-identifying."""

    def test_sidecar_written_with_schema(self, tmp_path):
        jsonl_path = str(tmp_path / "meta.jsonl")
        config = _config(
            jsonl_path=jsonl_path,
            extra={"instrumentation": {"run_id": "phase3-local-a"}},
        )
        runner = _runner(config, jsonl_path)
        assert runner._run_id == "phase3-local-a"
        sidecar = Path(sidecar_path_for(jsonl_path))
        assert sidecar.is_file()
        meta = json.loads(sidecar.read_text(encoding="utf-8"))
        assert meta["schema"] == "hgria.run_metadata.v1"
        assert meta["run_id"] == "phase3-local-a"
        assert "git_sha" in meta
        assert "config_sha256" in meta
        assert meta["preview_enabled"] is True
        assert meta["colab_mode"] is True
        assert meta["dynamic_gestures_enabled"] is False
        assert "opencv" in meta
        assert "cv2_version" in meta["opencv"]
        assert "distributions" in meta["opencv"]

    def test_jsonl_rows_include_run_id(self, tmp_path):
        jsonl_path = str(tmp_path / "rows.jsonl")
        config = _config(
            jsonl_path=jsonl_path,
            extra={"instrumentation": {"run_id": "row-id-1"}},
        )
        runner = _runner(config, jsonl_path)
        runner._process_frame()
        rec = _jsonl_records(jsonl_path)[0]
        assert rec["run_id"] == "row-id-1"
        assert rec["exit_reason"] == "no_hand"

    def test_generated_run_id_when_unset(self):
        config = _config(extra={"instrumentation": {"run_id": ""}})
        rid = resolve_run_id(config)
        assert rid
        assert rid != ""

    def test_collect_run_metadata_keys(self):
        config = ConfigurationManager("config/config.json")
        meta = collect_run_metadata(config, run_id="k", jsonl_path="logs/x.jsonl")
        for key in (
            "schema",
            "run_id",
            "git_sha",
            "config_sha256",
            "python",
            "cwd",
            "jsonl_path",
            "deployment_path",
            "preview_enabled",
            "colab_mode",
            "dynamic_gestures_enabled",
            "opencv",
            "packages",
        ):
            assert key in meta


class TestCameraFallback:
    """Fallback remains, but is observable; strict_camera refuses it."""

    def setup_method(self):
        FrameStore().reset_instrumentation()

    def test_fallback_sets_colab_mode_and_flag(self):
        config = _config(
            extra={
                "camera": {"colab_mode": False, "colab_fallback": False},
                "evaluation": {"strict_camera": False},
            }
        )
        with patch(
            "backend.pipeline.camera.OpenCVCaptureStrategy",
            side_effect=CameraInitializationError("no camera"),
        ):
            with pytest.warns(RuntimeWarning, match="NOT a valid local OpenCV baseline"):
                camera = CameraModule(config)
        assert config.camera.colab_mode is True
        assert config.camera.colab_fallback is True
        assert camera.get_frame_store() is not None

    def test_strict_camera_reraises(self):
        config = _config(
            extra={
                "camera": {"colab_mode": False, "colab_fallback": False},
                "evaluation": {"strict_camera": True},
            }
        )
        with patch(
            "backend.pipeline.camera.OpenCVCaptureStrategy",
            side_effect=CameraInitializationError("no camera"),
        ):
            with pytest.raises(CameraInitializationError):
                CameraModule(config)
        assert config.camera.colab_mode is False
        assert config.camera.colab_fallback is False


class TestDynamicPathStillOff:
    def test_committed_config_does_not_construct_onnx(self):
        config = ConfigurationManager("config/config.json")
        assert config.is_dynamic_gestures_enabled() is False
        with patch(
            "backend.pipeline.dynamic_recognizer.DynamicGestureRecognizer"
        ) as mock_cls:
            runner = PipelineRunner(
                config,
                queue.Queue(maxsize=4),
                StateManager(None, None),
                camera=MagicMock(),
                detector=MagicMock(),
                logger=None,
                socketio=None,
                session=Session(),
                experiment_logger=ExperimentLogger("logs/unused.jsonl", enabled=False),
            )
            mock_cls.assert_not_called()
        assert runner._dynamic_recognizer is None


class TestRecognitionUnchangedWithHardening:
    """Same mocked frame sequence → same gesture/command with instr on/off."""

    def test_instrumentation_on_off_same_decisions(self, tmp_path):
        decisions = []
        for enabled in (True, False):
            jsonl_path = str(tmp_path / f"inv_{enabled}.jsonl")
            config = _config(jsonl_path=jsonl_path, enabled=enabled)
            runner = _hand_runner(config, jsonl_path, frame_ids=[11, 12])
            gestures = []
            emitted = []
            reasons = []
            for _ in range(2):
                assert runner._process_frame() is True
                timing = runner._latest_frame_timing
                gestures.append(timing.gesture)
                emitted.append(timing.command_emitted)
                reasons.append(timing.exit_reason)
            decisions.append((gestures, emitted, reasons))
        assert decisions[0][0] == decisions[1][0]
        assert decisions[0][1] == decisions[1][1]
        assert decisions[0][2] == decisions[1][2]


class TestOpenCVRequirementPin:
    def test_requirements_pins_both_opencv_distributions(self):
        text = Path("requirements.txt").read_text(encoding="utf-8")
        assert "opencv-python-headless==4.10.0.84" in text
        assert "opencv-contrib-python==4.10.0.84" in text
        assert "opencv-python==" not in text.replace("opencv-python-headless", "")
