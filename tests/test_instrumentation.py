"""Phase 2: server-side instrumentation (timing, frame_id, JSONL, drops)."""

import json
import os
import queue
import tempfile
from unittest.mock import MagicMock

import numpy as np

from backend.core.configuration import ConfigurationManager
from backend.core.models import Frame, Session
from backend.core.state_manager import StateManager
from backend.pipeline.camera import CameraModule, FrameStore
from backend.pipeline.classifier import GestureClassifier
from backend.pipeline.pipeline_runner import PipelineRunner
from backend.utils.instrumentation import (
    ExperimentLogger,
    FrameIdSequence,
    ResourceSampler,
    mono_now,
    normalize_frame_id,
    time_call,
)
from tests.fixtures import build_open_palm_landmark


def _config(extra=None, jsonl_path=None, enabled=True):
    data = {
        "instrumentation": {
            "enabled": enabled,
            "jsonl_path": jsonl_path or "logs/instrumentation.jsonl",
            "resource_sample_interval_s": 1.0,
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
    }
    if extra:
        data.update(extra)
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


def _frame(frame_id=1):
    t0 = mono_now()
    frame = Frame(
        frame_id=frame_id,
        bgr_data=_blank_bgr(),
        blur_score=200.0,
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
    # Production starts SEARCHING after client_connected; tests skip SocketIO.
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
        resource_sampler=ResourceSampler(interval_s=1.0),
    )


class TestFrameId:
    """frame_id exists and is unique; client IDs are preserved."""

    def setup_method(self):
        FrameStore().reset_instrumentation()

    def test_server_generated_ids_are_unique(self):
        seq = FrameIdSequence()
        ids = [seq.next_id() for _ in range(50)]
        assert len(ids) == len(set(ids))
        assert all(isinstance(i, int) for i in ids)

    def test_opencv_style_capture_assigns_unique_ids(self):
        config = _config()
        camera = CameraModule(config)
        store = camera.get_frame_store()
        store.reset_instrumentation()
        ids = []
        for _ in range(12):
            store.put(_blank_bgr())
            frame = camera.capture()
            assert frame is not None
            assert frame.frame_id is not None
            ids.append(frame.frame_id)
        assert len(set(ids)) == 12

    def test_client_frame_id_is_preserved(self):
        config = _config()
        camera = CameraModule(config)
        store = camera.get_frame_store()
        store.reset_instrumentation()
        store.put(_blank_bgr(), frame_id=4242)
        frame = camera.capture()
        assert frame.frame_id == 4242

    def test_normalize_keeps_string_ids(self):
        assert normalize_frame_id("client-abc") == "client-abc"
        assert normalize_frame_id("17") == 17
        assert normalize_frame_id(None) is None


class TestTimestampsAndDurations:
    """Monotonic timestamps and non-negative stage durations."""

    def test_time_call_duration_non_negative(self):
        def _work(x):
            return x + 1

        result, elapsed_ms, t_done = time_call(_work, 1)
        assert result == 2
        assert elapsed_ms >= 0.0
        assert t_done >= 0.0

    def test_processed_frame_timestamps_are_monotonic(self, tmp_path):
        jsonl_path = str(tmp_path / "frames.jsonl")
        config = _config(jsonl_path=jsonl_path)
        runner = _runner(config, jsonl_path)
        assert runner._process_frame() is True
        timing = runner._latest_frame_timing
        assert timing is not None
        stamps = timing.monotonic_timestamps()
        assert stamps == sorted(stamps)
        for value in timing.stage_durations_ms().values():
            assert value >= 0.0


class TestCommandPayloadFrameId:
    """gesture_command payload includes frame_id without renaming fields."""

    def test_generate_includes_frame_id(self):
        from backend.pipeline.commander import CommandGenerator

        config = _config()
        gen = CommandGenerator(config, Session())
        cmd = gen.generate(
            {"gesture_name": "open_palm", "confidence": 0.91, "frame_id": 123}
        )
        payload = cmd.to_dict()
        assert payload["frame_id"] == 123
        assert payload["gesture_name"] == "open_palm"
        assert payload["command_type"] == "MOVE"
        assert payload["command_value"] == {"direction": "stop"}
        assert payload["confidence"] == 0.91
        assert "command_id" in payload
        assert "session_id" in payload
        assert "timestamp" in payload

    def test_pipeline_emit_includes_frame_id(self, tmp_path):
        jsonl_path = str(tmp_path / "cmd.jsonl")
        config = _config(jsonl_path=jsonl_path)
        socketio = MagicMock()
        camera = MagicMock()
        camera.capture.return_value = _frame(77)
        camera.get_frame_store.return_value = FrameStore()
        detector = MagicMock()
        detector.detect.return_value = [("raw", "hand")]
        runner = _runner(
            config, jsonl_path, camera=camera, detector=detector, socketio=socketio
        )
        runner._extractor.extract_all = MagicMock(
            return_value=[build_open_palm_landmark()]
        )
        assert runner._process_frame() is True
        assert socketio.emit.called
        event, payload = socketio.emit.call_args_list[-1][0]
        assert event == "gesture_command"
        assert payload["frame_id"] == 77
        assert payload["gesture_name"]
        assert "confidence" in payload
        assert "server_emitted_at" in payload


class TestFrameStoreDroppedFrames:
    """Last-write-wins overwrite increments the dropped-frame counter."""

    def setup_method(self):
        FrameStore().reset_instrumentation()

    def test_overwrite_increments_counter(self):
        store = FrameStore()
        store.reset_instrumentation()
        store.put(_blank_bgr(), frame_id=1)
        assert store.dropped_frames == 0
        store.put(_blank_bgr(), frame_id=2)
        assert store.dropped_frames == 1
        store.put(_blank_bgr(), frame_id=3)
        assert store.dropped_frames == 2
        frame = store.consume()
        assert frame is not None
        assert store.dropped_frames == 2

    def test_consume_then_put_does_not_count_as_drop(self):
        store = FrameStore()
        store.reset_instrumentation()
        store.put(_blank_bgr(), frame_id=1)
        store.consume()
        store.put(_blank_bgr(), frame_id=2)
        assert store.dropped_frames == 0


class TestJsonlWriter:
    """JSONL writer creates valid JSON lines."""

    def test_writes_valid_json_lines(self, tmp_path):
        path = str(tmp_path / "obs.jsonl")
        writer = ExperimentLogger(path, enabled=True)
        writer.write({"frame_id": 1, "capture_ms": 1.2})
        writer.write({"frame_id": 2, "command_emitted": False})
        lines = open(path, encoding="utf-8").read().splitlines()
        assert len(lines) == 2
        rec1 = json.loads(lines[0])
        rec2 = json.loads(lines[1])
        assert rec1["frame_id"] == 1
        assert rec2["frame_id"] == 2

    def test_disabled_writer_does_not_create_file(self, tmp_path):
        path = str(tmp_path / "disabled.jsonl")
        writer = ExperimentLogger(path, enabled=False)
        writer.write({"frame_id": 1})
        assert not os.path.exists(path)


class TestClassificationUnchanged:
    """Instrumentation must not change classification results."""

    def test_time_call_does_not_change_classify_result(self):
        config = ConfigurationManager("config/config.json")
        classifier = GestureClassifier(config)
        landmark = build_open_palm_landmark()
        direct = classifier.classify(landmark)
        wrapped, elapsed_ms, _ = time_call(classifier.classify, landmark)
        assert elapsed_ms >= 0.0
        assert wrapped.gesture_name == direct.gesture_name
        assert wrapped.confidence == direct.confidence
        assert wrapped.raw_scores == direct.raw_scores

    def test_enabled_vs_disabled_same_classification(self, tmp_path):
        landmark = build_open_palm_landmark()
        results = []
        for enabled in (True, False):
            jsonl_path = str(tmp_path / f"{enabled}.jsonl")
            config = _config(jsonl_path=jsonl_path, enabled=enabled)
            camera = MagicMock()
            camera.capture.return_value = _frame(5)
            camera.get_frame_store.return_value = FrameStore()
            detector = MagicMock()
            detector.detect.return_value = [("raw", "hand")]
            runner = _runner(
                config, jsonl_path, camera=camera, detector=detector
            )
            runner._extractor.extract_all = MagicMock(return_value=[landmark])
            orig = runner._classifier.classify

            def _capture(lm, _orig=orig, _bucket=results):
                pred = _orig(lm)
                _bucket.append(pred)
                return pred

            runner._classifier.classify = _capture
            assert runner._process_frame() is True

        assert len(results) == 2
        assert results[0].gesture_name == results[1].gesture_name
        assert results[0].confidence == results[1].confidence
        assert results[0].raw_scores == results[1].raw_scores


class TestDebugEndpointInstrumentation:
    """GET /api/debug exposes processed frames, commands, drops, latest timing."""

    def test_debug_includes_instrumentation_fields(
        self, test_session, test_state_manager, command_queue, tmp_path
    ):
        from backend.app import create_app

        jsonl_path = str(tmp_path / "dbg.jsonl")
        config = _config(jsonl_path=jsonl_path)
        runner = _runner(config, jsonl_path)
        runner._process_frame()

        app, _ = create_app(
            config, test_session, test_state_manager, command_queue, None
        )
        app.config["TESTING"] = True
        app.config["HG_PIPELINE"] = runner
        client = app.test_client()
        data = client.get("/api/debug").get_json()
        assert "processed_frames" in data
        assert "commands_sent" in data
        assert "dropped_frames" in data
        assert "latest_timing" in data
        assert "avg_total_server_ms" in data
        assert "p50" not in json.dumps(data).lower()
        assert "p95" not in json.dumps(data).lower()
        assert "p99" not in json.dumps(data).lower()
        assert data["processed_frames"] >= 1


class TestApiFramePreservesId:
    """POST /api/frame stays compatible and can carry frame_id."""

    def setup_method(self):
        FrameStore().reset_instrumentation()

    def test_optional_frame_id_survives_to_capture(
        self, test_session, test_state_manager, command_queue
    ):
        import base64

        import cv2

        from backend.app import create_app

        config = _config()
        app, _ = create_app(
            config, test_session, test_state_manager, command_queue, None
        )
        app.config["TESTING"] = True
        client = app.test_client()

        ok, buf = cv2.imencode(".jpg", _blank_bgr())
        assert ok
        b64 = base64.b64encode(buf.tobytes()).decode("ascii")
        response = client.post(
            "/api/frame",
            json={"image": b64, "frame_id": 555},
            content_type="application/json",
        )
        assert response.status_code == 204

        camera = CameraModule(config)
        frame = camera.capture()
        assert frame is not None
        assert frame.frame_id == 555


class TestSmokeStaticPipeline:
    """Small static-path smoke: JSONL parses, IDs correlate, no negative ms."""

    def test_smoke_jsonl_and_command_correlation(self, tmp_path):
        jsonl_path = str(tmp_path / "smoke.jsonl")
        config = _config(jsonl_path=jsonl_path)
        socketio = MagicMock()
        camera = MagicMock()
        camera.capture.side_effect = [_frame(i) for i in (101, 102, 103)]
        camera.get_frame_store.return_value = FrameStore()
        detector = MagicMock()
        detector.detect.return_value = [("raw", "hand")]
        runner = _runner(
            config, jsonl_path, camera=camera, detector=detector, socketio=socketio
        )
        runner._extractor.extract_all = MagicMock(
            return_value=[build_open_palm_landmark()]
        )

        processed = [runner._process_frame() for _ in range(3)]
        assert processed == [True, True, True]

        lines = open(jsonl_path, encoding="utf-8").read().splitlines()
        assert len(lines) == 3
        records = [json.loads(line) for line in lines]
        assert [rec["frame_id"] for rec in records] == [101, 102, 103]
        for rec in records:
            for key, value in rec.items():
                if key.endswith("_ms") and value is not None:
                    assert value >= 0.0, (key, value)

        command_events = [
            call[0][1]
            for call in socketio.emit.call_args_list
            if call[0][0] == "gesture_command"
        ]
        assert command_events
        emitted_ids = {evt["frame_id"] for evt in command_events}
        assert emitted_ids.issubset({101, 102, 103})
        assert all("server_emitted_at" in evt for evt in command_events)

        # First frame with window=1 and cooldown 0 should emit.
        assert any(rec["command_emitted"] for rec in records)
        assert records[0]["frame_id"] == command_events[0]["frame_id"]
