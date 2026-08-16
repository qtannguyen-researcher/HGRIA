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
from typing import TYPE_CHECKING, Any, Optional

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
        """
        self._config = config
        self._command_queue = command_queue
        self._state_manager = state_manager
        self._camera = camera
        self._detector = detector
        self._logger = logger
        self._running = False
        self._thread: Optional[threading.Thread] = None

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

        # Dynamic gesture recognizer (optional – skipped if not configured)
        self._dynamic_recognizer: Optional[Any] = None
        self._init_dynamic_recognizer(config)

        # Session + command generator
        from backend.core.models import Session
        self._session = Session()
        self._command_generator = CommandGenerator(config, self._session)

        # Error handler
        from backend.core.errors import ErrorHandler
        self._error_handler = ErrorHandler(logger, None, state_manager)

    def _init_dynamic_recognizer(self, config: "ConfigurationManager") -> None:
        """Initialise the DynamicGestureRecognizer if the config section exists."""
        try:
            # ConfigurationManager raises AttributeError when the section
            # is absent, so we guard here to keep the static path working
            # without requiring the dynamic_gestures section.
            _ = config.dynamic_gestures
        except AttributeError:
            if self._logger:
                self._logger.info(
                    "dynamic_gestures_disabled",
                    reason="no dynamic_gestures section in config",
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
                self._process_frame()
            except Exception as e:
                if self._error_handler:
                    self._error_handler.handle(e)

    def _process_frame(self) -> None:
        """Process a single frame through all pipeline stages."""
        from backend.core.errors import MediaPipeError

        # Stage 1: Capture
        frame = self._camera.capture()
        if frame is None:
            return

        # Stage 2: Preprocess (BGR → RGB + optional CLAHE)
        frame = self._preprocessor.process(frame)

        # ── Stage 3b: Dynamic path ─────────────────────────────────────────
        # Runs on the raw BGR frame independently of MediaPipe.
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
            raw_landmarks = self._detector.detect(frame)
        except Exception as e:
            raise MediaPipeError(str(e)) from e

        static_gesture: Optional[str] = None
        static_confidence: float = 0.0

        if raw_landmarks:
            self._state_manager.transition("hand_detected")

            dominant_hand = self._config.gesture_recognition.dominant_hand
            landmarks = self._extractor.extract_all(raw_landmarks, dominant_hand)
            if landmarks:
                landmark = landmarks[0]
                prediction = self._classifier.classify(landmark)
                prediction = self._noise_filter.filter(prediction, landmark, frame)
                if not prediction.is_filtered:
                    smoothed = self._temporal_filter.update(prediction)
                    if smoothed != "UNKNOWN":
                        static_gesture = smoothed
                        static_confidence = prediction.confidence
        else:
            self._state_manager.transition("no_hand_detected")

        # ── Stage 4: Merge ─────────────────────────────────────────────────
        # Dynamic gesture takes priority when both are present.
        if dynamic_gesture:
            gesture = dynamic_gesture
            confidence = 1.0
        elif static_gesture:
            gesture = static_gesture
            confidence = static_confidence
        else:
            return

        self._state_manager.transition("gesture_stable")

        # Stage 5: Cooldown check
        partial = self._cooldown_manager.check(gesture, confidence)
        if partial is None:
            return

        # Stage 6: Generate command
        try:
            command = self._command_generator.generate(partial)
        except Exception:
            # UnmappedGestureError – skip silently
            return

        self._state_manager.transition("command_emitted")
        self._command_queue.put_nowait(command)
        self._state_manager.transition("command_processed")

        if self._logger and self._config.debug.log_pipeline_latency:
            self._logger.debug(
                "gesture_dispatched",
                gesture=gesture,
                source="dynamic" if dynamic_gesture else "static",
                module="pipeline_runner",
            )

    @property
    def camera(self) -> "CameraModule":
        """Get the camera module."""
        return self._camera

    @property
    def is_running(self) -> bool:
        """Check if the pipeline is running."""
        return self._running
