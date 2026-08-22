"""Pipeline runner that orchestrates all stages in a background thread.

Stage layout
------------
1.  Capture           – CameraModule
2.  Preprocess        – FramePreprocessor (BGR → RGB, CLAHE)
3a. Static path       – HandDetector (MediaPipe) → LandmarkExtractor
                        → GestureClassifier → NoiseFilter → TemporalFilter
3b. Dynamic path      – DynamicGestureRecognizer (ONNX + OC-SORT)
                        runs on the raw BGR frame in parallel with 3a
4.  Merge & cooldown  – first valid gesture wins (dynamic takes priority),
                        then CooldownManager
5.  Command           – CommandGenerator → Queue → SocketIO
"""

import queue
import threading
import time
from collections import deque
from typing import TYPE_CHECKING, Any, Deque, Dict, Optional

if TYPE_CHECKING:
    from backend.core.configuration import ConfigurationManager
    from backend.core.state_manager import StateManager
    from backend.pipeline.camera import CameraModule


class PipelineRunner:
    """Orchestrates all pipeline stages in a single background thread."""

    def __init__(
        self,
        config: "ConfigurationManager",
        command_queue: queue.Queue,
        state_manager: "StateManager",
        camera: Optional["CameraModule"] = None,
        detector: Any = None,
        logger: Any = None,
        socketio: Any = None,
        session: Any = None,
        experiment_logger: Any = None,
        resource_sampler: Any = None,
    ) -> None:
        """
        Initialise the pipeline runner.

        Args:
            config: Configuration object.
            command_queue: Queue for transmitting commands.
            state_manager: State manager for state transitions.
            camera: Optional pre-created CameraModule.
            detector: Optional pre-created HandDetector.
            logger: Optional logger.
            socketio: Optional SocketIO instance for emitting preview frames.
            session: Optional shared Session. If omitted a new Session is created.
            experiment_logger: Optional JSONL writer. If omitted, built from config.
            resource_sampler: Optional 1 Hz CPU/RSS sampler. If omitted, built
                from config when instrumentation is enabled.
        """
        self._config = config
        self._command_queue = command_queue
        self._state_manager = state_manager
        self._camera = camera
        self._detector = detector
        self._logger = logger
        self._socketio = socketio
        self._running = False
        self._thread: Optional[threading.Thread] = None
        # Throttle frame preview emissions to ~10 FPS to avoid flooding clients.
        self._preview_interval = 0.1  # seconds
        self._last_preview_time = 0.0

        # Lazy imports to avoid circular dependencies
        if camera is None:
            from backend.pipeline.camera import CameraModule
            self._camera = CameraModule(config)
        if detector is None:
            from backend.pipeline.detector import HandDetector
            self._detector = HandDetector(config, logger)

        # Static pipeline stages
        from backend.pipeline.preprocessor import FramePreprocessor
        from backend.pipeline.extractor import LandmarkExtractor
        from backend.pipeline.classifier import GestureClassifier
        from backend.pipeline.filter import NoiseFilter, TemporalFilter
        from backend.pipeline.cooldown import CooldownManager
        from backend.pipeline.commander import CommandGenerator

        self._preprocessor = FramePreprocessor(config)
        self._extractor = LandmarkExtractor()
        self._classifier = GestureClassifier(config)
        self._noise_filter = NoiseFilter(config, logger)
        self._temporal_filter = TemporalFilter(config)
        self._cooldown_manager = CooldownManager(config, logger)

        # Dynamic gesture recognizer (optional – skipped unless enabled)
        self._dynamic_recognizer: Optional[Any] = None
        self._init_dynamic_recognizer(config)

        # Session + command generator. The same Session instance must be shared
        # with SystemOrchestrator and the Flask /api/session routes; otherwise
        # pipeline-recorded commands never appear in the HTTP session API.
        from backend.core.models import Session
        self._session = session if session is not None else Session()
        self._command_generator = CommandGenerator(config, self._session)

        # Error handler
        from backend.core.errors import ErrorHandler
        self._error_handler = ErrorHandler(logger, None, state_manager)

        # ── Diagnostic counters (thread-safe via GIL on int increments) ───
        self.stats: Dict[str, int] = {
            "frames_captured": 0,
            "frames_no_hand": 0,
            "frames_filtered_noise": 0,
            "frames_filtered_temporal": 0,
            "frames_cooldown": 0,
            "commands_sent": 0,
            "dropped_frames": 0,
        }
        # Rolling blur scores for the last 30 frames (debug)
        self._blur_history: Deque[float] = deque(maxlen=30)

        from backend.utils.instrumentation import (
            ResourceSampler,
            build_experiment_logger,
            instrumentation_config,
        )
        instr_cfg = instrumentation_config(config)
        self._instrumentation_enabled = bool(instr_cfg["enabled"])
        self._experiment_logger = (
            experiment_logger
            if experiment_logger is not None
            else build_experiment_logger(config)
        )
        self._resource_sampler = resource_sampler
        if self._resource_sampler is None and self._instrumentation_enabled:
            self._resource_sampler = ResourceSampler(
                interval_s=instr_cfg["resource_sample_interval_s"]
            )
        self._latest_timing: Dict[str, Any] = {}
        self._latest_frame_timing: Any = None
        self._total_server_ms_sum = 0.0
        self._total_server_ms_n = 0

    def _init_dynamic_recognizer(self, config: "ConfigurationManager") -> None:
        """Initialise the DynamicGestureRecognizer only when enabled is true.

        The baseline path is static MediaPipe/rule-based recognition. The
        dynamic ONNX implementation is left in the tree but must not load
        unless ``dynamic_gestures.enabled`` is explicitly true.
        """
        enabled = False
        try:
            enabled = config.is_dynamic_gestures_enabled()
        except AttributeError:
            # Older/minimal config objects may lack the helper; fall back to
            # reading the flag without treating section presence as enabled.
            try:
                dg_cfg = config.dynamic_gestures
                enabled = bool(getattr(dg_cfg, "enabled", False))
            except AttributeError:
                enabled = False

        if not enabled:
            if self._logger:
                self._logger.info(
                    "dynamic_gestures_disabled",
                    reason="dynamic_gestures.enabled is false",
                    module="pipeline_runner",
                )
            return

        try:
            from backend.pipeline.dynamic_recognizer import DynamicGestureRecognizer
            self._dynamic_recognizer = DynamicGestureRecognizer(config)
            if self._logger:
                self._logger.info(
                    "dynamic_gestures_enabled",
                    module="pipeline_runner",
                )
        except Exception as exc:
            # Dynamic path is best-effort; log and continue with static only.
            if self._logger:
                self._logger.warning(
                    "dynamic_gestures_init_failed",
                    error=str(exc),
                    module="pipeline_runner",
                )

    def start(self) -> None:
        """Start the pipeline in a background daemon thread."""
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        if self._logger:
            self._logger.info("pipeline_started", module="pipeline_runner")

    def stop(self) -> None:
        """Stop the pipeline and release resources."""
        self._running = False
        if self._camera:
            self._camera.release()
        if self._logger:
            self._logger.info("pipeline_stopped", module="pipeline_runner")

    def _run_loop(self) -> None:
        """Main pipeline loop running in a background thread."""
        while self._running:
            try:
                processed = self._process_frame()
                # In colab/browser mode frames arrive at ~30 fps.  When the
                # store is empty (consume() returned None) sleep briefly so we
                # don't busy-spin at thousands of iterations per second.
                if not processed:
                    time.sleep(0.005)
            except Exception as e:
                if self._error_handler:
                    self._error_handler.handle(e)

    def _process_frame(self) -> bool:
        """Process a single frame through all pipeline stages.

        Returns:
            True if a frame was available and processed, False if the capture
            returned None (no new frame yet in colab/browser mode).
        """
        from backend.core.errors import MediaPipeError
        from backend.utils.instrumentation import FrameTiming, mono_now, time_call, wall_iso

        timing = FrameTiming()

        # Stage 1: Capture
        t_cap0 = mono_now()
        frame = self._camera.capture()
        t_cap1 = mono_now()
        if frame is None:
            return False

        timing.frame_id = frame.frame_id
        timing.t_capture = getattr(frame, "t_capture", t_cap0)
        timing.t_server_received = getattr(frame, "t_server_received", t_cap0)
        timing.capture_ms = (t_cap1 - t_cap0) * 1000.0
        timing.dropped_frames = self._dropped_frame_count()

        self.stats["frames_captured"] += 1
        self.stats["dropped_frames"] = timing.dropped_frames
        if hasattr(frame, "blur_score"):
            self._blur_history.append(frame.blur_score)

        try:
            # Emit a preview frame to connected clients (throttled to ~10 FPS).
            self._maybe_emit_preview(frame.bgr_data)

            # Stage 2: Preprocess (BGR → RGB + optional CLAHE)
            frame, timing.preprocess_ms, timing.t_preprocess_done = time_call(
                self._preprocessor.process, frame
            )

            # ── Stage 3b: Dynamic path ─────────────────────────────────────────
            # Runs on the raw BGR frame independently of MediaPipe.
            # Baseline: dynamic_gestures.enabled=false — this block is skipped.
            # ONNX time is intentionally not recorded even if the path is on.
            dynamic_gesture: Optional[str] = None
            if self._dynamic_recognizer is not None and frame.bgr_data is not None:
                try:
                    dynamic_pred = self._dynamic_recognizer.process_frame(frame.bgr_data)
                    if dynamic_pred is not None and dynamic_pred.is_valid():
                        dynamic_gesture = dynamic_pred.event_name
                except Exception as exc:
                    if self._logger:
                        self._logger.warning(
                            "dynamic_recognizer_error",
                            error=str(exc),
                            module="pipeline_runner",
                        )

            # ── Stage 3a: Static path ──────────────────────────────────────────
            try:
                raw_landmarks, timing.mediapipe_ms, timing.t_mediapipe_done = time_call(
                    self._detector.detect, frame
                )
            except Exception as e:
                raise MediaPipeError(str(e)) from e

            static_gesture: Optional[str] = None
            static_confidence: float = 0.0

            if raw_landmarks:
                self._state_manager.transition("hand_detected")

                dominant_hand = self._config.gesture_recognition.dominant_hand
                landmarks, timing.landmark_extraction_ms, _ = time_call(
                    self._extractor.extract_all, raw_landmarks, dominant_hand
                )
                if landmarks:
                    landmark = landmarks[0]
                    prediction, timing.classification_ms, timing.t_classification_done = (
                        time_call(self._classifier.classify, landmark)
                    )
                    timing.gesture = prediction.gesture_name
                    timing.score = prediction.confidence
                    if self._logger:
                        self._logger.debug(
                            "classifier_result",
                            gesture=prediction.gesture_name,
                            confidence=round(prediction.confidence, 3),
                            blur_score=round(frame.blur_score, 1) if hasattr(frame, "blur_score") else None,
                            module="pipeline_runner",
                        )
                    prediction, timing.noise_filter_ms, _ = time_call(
                        self._noise_filter.filter, prediction, landmark, frame
                    )
                    if not prediction.is_filtered:
                        smoothed, timing.temporal_filter_ms, _ = time_call(
                            self._temporal_filter.update, prediction
                        )
                        if self._logger and smoothed == "UNKNOWN":
                            self._logger.debug(
                                "temporal_filter_pending",
                                gesture=prediction.gesture_name,
                                buffer_size=self._temporal_filter.window_size,
                                module="pipeline_runner",
                            )
                        if smoothed != "UNKNOWN":
                            static_gesture = smoothed
                            static_confidence = prediction.confidence
                            timing.gesture = smoothed
                            timing.score = prediction.confidence
                        else:
                            self.stats["frames_filtered_temporal"] += 1
                    else:
                        self.stats["frames_filtered_noise"] += 1
            else:
                self._state_manager.transition("no_hand_detected")
                self.stats["frames_no_hand"] += 1

            # ── Stage 4: Merge ─────────────────────────────────────────────────
            # Dynamic gesture takes priority when both are present.
            if dynamic_gesture:
                gesture = dynamic_gesture
                confidence = 1.0
            elif static_gesture:
                gesture = static_gesture
                confidence = static_confidence
            else:
                return True  # frame processed, no gesture this cycle

            timing.gesture = gesture
            timing.score = confidence

            transitioned = self._state_manager.transition("gesture_stable")
            if transitioned and self._logger:
                self._logger.info(
                    "gesture_stable",
                    gesture=gesture,
                    confidence=round(confidence, 3),
                    source="dynamic" if dynamic_gesture else "static",
                    module="pipeline_runner",
                )

            # Emit gesture_update so the HUD reflects the recognised gesture in
            # real-time, regardless of whether a command is generated.
            if self._socketio is not None:
                self._socketio.emit("gesture_update", {
                    "gesture_name": gesture,
                    "confidence": round(confidence, 3),
                })

            # Stage 5: Cooldown check
            partial = self._cooldown_manager.check(gesture, confidence)
            if partial is None:
                self.stats["frames_cooldown"] += 1
                return True  # gesture seen but rate-limited

            # Stage 6: Generate command
            partial["frame_id"] = frame.frame_id
            try:
                command, timing.command_generation_ms, timing.t_command_generated = (
                    time_call(self._command_generator.generate, partial)
                )
            except Exception as exc:
                if self._logger:
                    self._logger.warning(
                        "gesture_unmapped",
                        gesture=gesture,
                        error=str(exc),
                        module="pipeline_runner",
                    )
                return True

            self._state_manager.transition("command_emitted")
            command.server_emitted_at = wall_iso()
            command.frame_id = frame.frame_id
            # Emit gesture_command directly — bypasses the queue/transmitter
            # which depends on start_background_task timing.
            if self._socketio is not None:
                self._socketio.emit("gesture_command", command.to_dict())
            timing.t_command_emitted = mono_now()
            timing.command_emitted = True
            # Also push to queue for any other consumers (logging, stats, etc.)
            try:
                self._command_queue.put_nowait(command)
            except queue.Full:
                pass  # queue is secondary; socket emit already done
            self._state_manager.transition("command_processed")
            self.stats["commands_sent"] += 1

            if self._logger:
                source = "dynamic" if dynamic_gesture else "static"
                self._logger.info(
                    "gesture_recognized",
                    gesture=gesture,
                    confidence=round(confidence, 3),
                    source=source,
                    command=command.command_type,
                    module="pipeline_runner",
                )

            return True
        finally:
            timing.finish()
            self._record_frame_instrumentation(timing)

    def _maybe_emit_preview(self, bgr_data: Any) -> None:
        """Encode a frame as JPEG and emit it to clients via SocketIO.

        Throttled to ``_preview_interval`` seconds so we do not saturate the
        WebSocket with full-rate camera frames.  Only runs when a SocketIO
        instance is available (i.e. not in test / offline mode).
        """
        if self._socketio is None or bgr_data is None:
            return

        now = time.monotonic()
        if now - self._last_preview_time < self._preview_interval:
            return

        try:
            import base64
            import cv2

            ok, buf = cv2.imencode(".jpg", bgr_data, [cv2.IMWRITE_JPEG_QUALITY, 60])
            if not ok:
                return

            b64 = base64.b64encode(buf.tobytes()).decode("ascii")
            self._socketio.emit("frame_preview", {"image": f"data:image/jpeg;base64,{b64}"})
            self._last_preview_time = now
        except Exception as exc:
            if self._logger:
                self._logger.warning(
                    "frame_preview_error",
                    error=str(exc),
                    module="pipeline_runner",
                )

    def _dropped_frame_count(self) -> int:
        """Unread frames overwritten in FrameStore (last-write-wins)."""
        try:
            store = None
            if self._camera is not None and hasattr(self._camera, "get_frame_store"):
                store = self._camera.get_frame_store()
            if store is None:
                from backend.pipeline.camera import FrameStore
                store = FrameStore()
            return int(store.dropped_frames)
        except Exception:
            return int(self.stats.get("dropped_frames", 0))

    def _record_frame_instrumentation(self, timing: Any) -> None:
        """Update debug snapshot and optionally write a JSONL observation."""
        if self._resource_sampler is not None:
            sample = self._resource_sampler.maybe_sample()
            timing.cpu_percent = sample.get("cpu_percent")
            timing.rss_mb = sample.get("rss_mb")

        if timing.total_server_ms is not None:
            self._total_server_ms_sum += timing.total_server_ms
            self._total_server_ms_n += 1

        self._latest_timing = timing.debug_snapshot()
        self._latest_frame_timing = timing

        if self._experiment_logger is not None:
            self._experiment_logger.write(timing.to_jsonl_record())

    def instrumentation_debug(self) -> Dict[str, Any]:
        """Live counters and latest timings for GET /api/debug.

        Does not report P50/P95/P99. ``avg_total_server_ms`` is an arithmetic
        mean of recorded ``total_server_ms`` values in this process.
        """
        avg = (
            self._total_server_ms_sum / self._total_server_ms_n
            if self._total_server_ms_n
            else None
        )
        return {
            "processed_frames": self.stats.get("frames_captured", 0),
            "commands_sent": self.stats.get("commands_sent", 0),
            "dropped_frames": self._dropped_frame_count(),
            "avg_total_server_ms": avg,
            "latest_timing": dict(self._latest_timing),
            "jsonl_enabled": bool(
                getattr(self._experiment_logger, "enabled", False)
            ),
            "jsonl_path": getattr(self._experiment_logger, "path", None),
            "cpu_scope": "process",
        }

    @property
    def session(self) -> Any:
        """Session used by CommandGenerator (shared with the Flask API)."""
        return self._session

    @property
    def camera(self) -> "CameraModule":
        """Get the camera module."""
        return self._camera

    @property
    def is_running(self) -> bool:
        """Check if the pipeline is running."""
        return self._running
