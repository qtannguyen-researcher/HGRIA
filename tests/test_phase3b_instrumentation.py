"""Phase 3B: local browser E2E instrumentation (no live benchmark)."""

import json
import os
import shutil
import subprocess
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np

from backend.core.configuration import DEFAULTS, ConfigurationManager
from backend.core.models import Session
from backend.pipeline.camera import CameraModule, FrameStore
from backend.pipeline.classifier import GESTURE_RULES, GestureClassifier
from backend.utils.e2e_matching import (
    compute_e2e_ms,
    compute_http_request_ms,
    match_e2e_samples,
    parse_jsonl_text,
    summarize_correlation,
)
from backend.utils.instrumentation import time_call
from tests.fixtures import build_open_palm_landmark
from tests.test_instrumentation import _blank_bgr, _config, _frame, _runner


REPO = Path(__file__).resolve().parents[1]
NODE = (
    os.environ.get("NODE")
    or shutil.which("node")
    or "/home/qtannguyen/.nvm/versions/node/v24.15.0/bin/node"
)


def _node_client_tests():
    script = REPO / "tests" / "js" / "test_client_instrumentation.js"
    result = subprocess.run(
        [NODE, str(script)],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + "\n" + result.stderr
    return json.loads(result.stdout.strip().splitlines()[-1])


class TestClientFrameIdAndTimestamps:
    """Client frame_id, performance.now semantics, HTTP and command times."""

    def test_node_client_instrumentation_contract(self):
        data = _node_client_tests()
        assert data["ok"] is True
        assert data["ids"] == [1, 2, 3]
        assert data["e2e_latency_ms"] == 64.5
        assert abs(data["http_request_ms"] - 32.25) < 1e-9

    def test_frame_id_included_in_post_payload_helper(self):
        data = _node_client_tests()
        assert data["ok"] is True
        source = (REPO / "frontend" / "js" / "webcam_capture.js").read_text(
            encoding="utf-8"
        )
        assert "frame_id" in source
        assert "/api/frame" in source
        assert "buildFramePayload" in source or "frame_id" in source
        helper = (REPO / "frontend" / "js" / "client_instrumentation.js").read_text(
            encoding="utf-8"
        )
        assert "function buildFramePayload" in helper or "buildFramePayload" in helper
        assert "performance.now" in helper
        assert "Date.now()" not in helper.split("wallIso")[0] or "performance.now" in helper

    def test_capture_uses_performance_now_not_date_now_for_arithmetic(self):
        helper = (REPO / "frontend" / "js" / "client_instrumentation.js").read_text(
            encoding="utf-8"
        )
        assert "function defaultNow" in helper
        assert "performance.now" in helper
        compute = helper[helper.index("function computeE2E") :]
        assert "Date.now" not in compute
        assert "toISOString" not in compute

    def test_webcam_capture_records_http_send_and_ack(self):
        source = (REPO / "frontend" / "js" / "webcam_capture.js").read_text(
            encoding="utf-8"
        )
        assert "recordCapture" in source
        assert "recordHttp" in source
        assert "tSend" in source
        assert "tAck" in source
        assert "JSON.stringify(bodyObj)" in source

    def test_command_receive_persists_frame_id_and_timestamp(self):
        source = (REPO / "frontend" / "js" / "websocket.js").read_text(encoding="utf-8")
        assert "recordCommandReceive" in source
        assert "t_client_cmd_recv" in source
        assert "data.frame_id" in source
        assert "updateLatency" not in source[source.index("gesture_command") :][
            :800
        ]


class TestE2EMatchingRules:
    """Matching is by frame_id only; unmatched / negative E2E are rejected."""

    def test_matching_capture_and_command_produces_e2e(self):
        client = [
            {"event": "client_capture", "run_id": "r", "frame_id": 7, "t_client_capture": 10.0},
            {
                "event": "client_http",
                "run_id": "r",
                "frame_id": 7,
                "t_client_http_send": 11.0,
                "t_client_http_ack": 21.0,
            },
            {
                "event": "client_command",
                "run_id": "r",
                "frame_id": 7,
                "t_client_cmd_recv": 40.0,
                "command_received": True,
            },
        ]
        server = [
            {"frame_id": 7, "command_emitted": True, "total_server_ms": 8.5},
        ]
        samples = match_e2e_samples(client, server)
        assert len(samples) == 1
        assert samples[0]["e2e_latency_ms"] == 30.0
        assert samples[0]["http_request_ms"] == 10.0
        assert samples[0]["total_server_ms"] == 8.5
        assert samples[0]["frame_id"] == 7

    def test_unmatched_frame_does_not_fabricate_e2e(self):
        client = [
            {"event": "client_capture", "run_id": "r", "frame_id": 1, "t_client_capture": 1.0},
            {"event": "client_capture", "run_id": "r", "frame_id": 2, "t_client_capture": 2.0},
            {
                "event": "client_command",
                "run_id": "r",
                "frame_id": 1,
                "t_client_cmd_recv": 5.0,
                "command_received": True,
            },
        ]
        server = [
            {"frame_id": 1, "command_emitted": True, "total_server_ms": 1.0},
        ]
        samples = match_e2e_samples(client, server)
        assert [s["frame_id"] for s in samples] == [1]
        summary = summarize_correlation(client, server)
        assert summary["client_frames_submitted"] == 2
        assert summary["server_frames_processed"] == 1
        assert summary["unmatched_client_frames"] == 1
        assert summary["matched_e2e_commands"] == 1
        assert "2" in summary["unmatched_client_frame_ids"]

    def test_negative_e2e_rejected(self):
        assert compute_e2e_ms(10.0, 20.0) is None
        client = [
            {"event": "client_capture", "frame_id": 3, "t_client_capture": 50.0},
            {
                "event": "client_command",
                "frame_id": 3,
                "t_client_cmd_recv": 10.0,
                "command_received": True,
            },
        ]
        server = [{"frame_id": 3, "command_emitted": True}]
        assert match_e2e_samples(client, server) == []

    def test_does_not_match_by_gesture_or_row(self):
        client = [
            {"event": "client_capture", "frame_id": 10, "t_client_capture": 1.0},
            {
                "event": "client_command",
                "frame_id": 99,
                "t_client_cmd_recv": 4.0,
                "command_received": True,
            },
        ]
        server = [
            {"frame_id": 10, "command_emitted": True, "gesture": "open_palm"},
            {"frame_id": 11, "command_emitted": True, "gesture": "open_palm"},
        ]
        assert match_e2e_samples(client, server) == []

    def test_server_without_command_emitted_is_not_e2e(self):
        client = [
            {"event": "client_capture", "frame_id": 4, "t_client_capture": 1.0},
            {
                "event": "client_command",
                "frame_id": 4,
                "t_client_cmd_recv": 9.0,
                "command_received": True,
            },
        ]
        server = [{"frame_id": 4, "command_emitted": False, "total_server_ms": 2.0}]
        assert match_e2e_samples(client, server) == []

    def test_http_metric_is_request_ack_not_one_way(self):
        assert compute_http_request_ms(40.0, 10.0) == 30.0
        assert compute_http_request_ms(10.0, 40.0) is None


class TestPingRttRemainsSeparate:
    """HUD / GameState ping RTT must not be reused as E2E."""

    def test_pong_handler_still_updates_latency_only(self):
        ws = (REPO / "frontend" / "js" / "websocket.js").read_text(encoding="utf-8")
        hud = (REPO / "frontend" / "js" / "hud.js").read_text(encoding="utf-8")
        state = (REPO / "frontend" / "js" / "state.js").read_text(encoding="utf-8")
        assert "socket.on('pong'" in ws
        assert "updateLatency" in ws
        pong_block = ws[ws.index("socket.on('pong'") : ws.index("socket.on('pong'") + 220]
        assert "updateLatency" in pong_block
        assert "e2e_latency_ms" not in pong_block
        assert "latencyMs" in state
        assert "updateLatency(sentTimestamp)" in state
        assert "hud-latency" in hud
        cmd_block = ws[ws.index("socket.on('gesture_command'") : ws.index("socket.on('gesture_update'")]
        assert "updateLatency" not in cmd_block
        assert "recordCommandReceive" in cmd_block

    def test_e2e_records_do_not_use_latency_ms_field(self):
        client_text = (
            '{"event":"client_command","frame_id":1,"t_client_cmd_recv":20,'
            '"t_client_capture":10,"e2e_latency_ms":10,"command_received":true}\n'
        )
        rec = parse_jsonl_text(client_text)[0]
        assert "latencyMs" not in rec
        assert rec["e2e_latency_ms"] == 10


class TestEvaluationIsolationUnchanged:
    """Debug / UI / keyboard / test-emit still cannot contaminate evaluation."""

    def test_existing_client_guards_still_present(self):
        ws = (REPO / "frontend" / "js" / "websocket.js").read_text(encoding="utf-8")
        main = (REPO / "frontend" / "js" / "main.js").read_text(encoding="utf-8")
        html = (REPO / "frontend" / "index.html").read_text(encoding="utf-8")
        cfg = (REPO / "frontend" / "js" / "config.js").read_text(encoding="utf-8")
        assert "UI_BYPASS" in ws
        assert "isEvaluationMode(this.#gameState)" in ws
        assert "isEvaluationMode(gameState)" in main
        assert "command_type: 'KEYBOARD'" in main
        assert "window._dbgInject" in html
        assert "blocked: evaluation mode" in html
        assert "window._dbgServerEmit" in html
        assert "shouldBlockCommandInjection" in cfg

    def test_test_emit_forbidden_in_evaluation(
        self, test_session, test_state_manager, command_queue
    ):
        from backend.app import create_app

        config = _config(extra={"evaluation": {"mode": True}})
        app, _ = create_app(
            config, test_session, test_state_manager, command_queue, None
        )
        app.config["TESTING"] = True
        response = app.test_client().get("/api/test-emit?gesture=point_left")
        assert response.status_code == 403


class TestRecognitionUnchanged:
    """Instrumentation must not change GESTURE_RULES or classify results."""

    def test_gesture_rules_baseline_names(self):
        names = [rule.gesture_name for rule in GESTURE_RULES]
        assert names == [
            "open_palm",
            "closed_fist",
            "point_left",
            "point_right",
            "thumb_up",
            "victory",
            "stop",
            "pinch",
            "ok",
        ]

    def test_classification_unchanged_by_timing_wrapper(self):
        config = ConfigurationManager("config/config.json")
        classifier = GestureClassifier(config)
        landmark = build_open_palm_landmark()
        direct = classifier.classify(landmark)
        wrapped, elapsed_ms, _ = time_call(classifier.classify, landmark)
        assert elapsed_ms >= 0.0
        assert wrapped.gesture_name == direct.gesture_name
        assert wrapped.confidence == direct.confidence
        assert wrapped.raw_scores == direct.raw_scores


class TestServerFrameIdAndBrowserSource:
    """Client frame_id survives the server path; browser_source is not Colab."""

    def setup_method(self):
        FrameStore().reset_instrumentation()

    def test_browser_source_default_false(self):
        cm = ConfigurationManager("config/config.json")
        assert cm.is_browser_source() is False
        assert DEFAULTS["camera"]["browser_source"] is False
        assert cm.camera.colab_mode is False
        assert cm.camera.colab_fallback is False

    def test_browser_source_uses_framestore_without_colab_flags(self):
        config = _config(
            extra={
                "camera": {
                    "colab_mode": False,
                    "colab_fallback": False,
                    "browser_source": True,
                }
            }
        )
        camera = CameraModule(config)
        assert config.camera.colab_mode is False
        assert config.camera.colab_fallback is False
        assert config.is_browser_source() is True
        camera.get_frame_store().put(_blank_bgr(), frame_id=321)
        frame = camera.capture()
        assert frame is not None
        assert frame.frame_id == 321

    def test_api_frame_active_when_browser_source(
        self, test_session, test_state_manager, command_queue
    ):
        import base64

        import cv2

        from backend.app import create_app

        config = _config(
            extra={
                "camera": {
                    "colab_mode": False,
                    "colab_fallback": False,
                    "browser_source": True,
                }
            }
        )
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
            json={"image": b64, "frame_id": 777},
            content_type="application/json",
        )
        assert response.status_code == 204
        camera = CameraModule(config)
        frame = camera.capture()
        assert frame is not None
        assert frame.frame_id == 777

    def test_pipeline_emit_keeps_client_frame_id(self, tmp_path):
        jsonl_path = str(tmp_path / "cmd.jsonl")
        config = _config(jsonl_path=jsonl_path)
        socketio = MagicMock()
        camera = MagicMock()
        camera.capture.return_value = _frame(88)
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
        event, payload = socketio.emit.call_args_list[-1][0]
        assert event == "gesture_command"
        assert payload["frame_id"] == 88

    def test_client_log_endpoint_writes_jsonl(
        self, tmp_path, test_session, test_state_manager, command_queue
    ):
        from backend.app import create_app

        client_path = str(tmp_path / "client.jsonl")
        config = _config(
            extra={"instrumentation": {"client_jsonl_path": client_path, "run_id": "r"}}
        )
        app, _ = create_app(
            config, test_session, test_state_manager, command_queue, None
        )
        app.config["TESTING"] = True
        client = app.test_client()
        response = client.post(
            "/api/client-log",
            json={
                "event": "client_capture",
                "run_id": "r",
                "frame_id": 1,
                "t_client_capture": 12.5,
            },
            content_type="application/json",
        )
        assert response.status_code == 204
        lines = Path(client_path).read_text(encoding="utf-8").splitlines()
        assert len(lines) == 1
        rec = json.loads(lines[0])
        assert rec["frame_id"] == 1
        assert rec["run_id"] == "r"
        assert rec["t_client_capture"] == 12.5

    def test_debug_reports_browser_source_false_by_default(
        self, tmp_path, test_session, test_state_manager, command_queue
    ):
        from backend.app import create_app

        jsonl_path = str(tmp_path / "dbg.jsonl")
        config = _config(
            jsonl_path=jsonl_path,
            extra={
                "instrumentation": {
                    "enabled": True,
                    "jsonl_path": jsonl_path,
                    "run_id": "test-run",
                },
                "evaluation": {
                    "mode": True,
                    "preview_enabled": False,
                    "strict_camera": True,
                },
                "camera": {
                    "colab_mode": False,
                    "colab_fallback": False,
                    "browser_source": False,
                },
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
        assert data["config"]["browser_source"] is False
        assert data["config"]["evaluation_mode"] is True
        assert data["config"]["preview_enabled"] is False
        assert data["instrumentation"]["run_id"] == "test-run"

    def test_index_loads_instrumented_capture_not_unwritable_bridge(self):
        html = (REPO / "frontend" / "index.html").read_text(encoding="utf-8")
        assert "js/client_instrumentation.js" in html
        assert "js/webcam_capture.js" in html
        assert "js/webcam_bridge.js" not in html


class TestLastWriteWinsUnmatchedFrames:
    """Overwritten FrameStore IDs stay client-only; do not fabricate server rows."""

    def setup_method(self):
        FrameStore().reset_instrumentation()

    def test_overwritten_ids_are_unmatched(self):
        store = FrameStore()
        store.reset_instrumentation()
        store.put(_blank_bgr(), frame_id=100)
        store.put(_blank_bgr(), frame_id=101)
        store.put(_blank_bgr(), frame_id=102)
        consumed = store.consume()
        assert consumed is not None
        meta_id, _ = store.last_consumed_meta()
        assert meta_id == 102
        assert store.dropped_frames == 2
        client = [
            {"event": "client_capture", "frame_id": i, "t_client_capture": float(i)}
            for i in (100, 101, 102)
        ]
        server = [{"frame_id": 102, "command_emitted": False, "total_server_ms": 1.0}]
        summary = summarize_correlation(client, server)
        assert summary["client_frames_submitted"] == 3
        assert summary["server_frames_processed"] == 1
        assert summary["unmatched_client_frames"] == 2
        assert summary["matched_e2e_commands"] == 0
