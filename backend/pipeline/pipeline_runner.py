"""Pipeline runner that orchestrates all stages in a background thread."""

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
        Initialize the pipeline runner.

        Args:
            config: Configuration object
            command_queue: Queue for transmitting commands
            state_manager: State manager for state transitions
            camera: Optional pre-created CameraModule
            detector: Optional pre-created HandDetector
            logger: Optional logger
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

        # Create all pipeline stages
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

        # Get session from config or create minimal one
        from backend.core.models import Session
        self._session = Session()
        self._command_generator = CommandGenerator(config, self._session)

        # Error handler
        from backend.core.errors import ErrorHandler
        self._error_handler = ErrorHandler(logger, None, state_manager)

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
                # Loop continues on recoverable errors

    def _process_frame(self) -> None:
        """Process a single frame through all pipeline stages."""
        from backend.core.errors import MediaPipeError

        # Stage 1: Capture
        frame = self._camera.capture()
        if frame is None:
            return

        # Stage 2: Preprocess (BGR → RGB + optional CLAHE)
        frame = self._preprocessor.process(frame)

        # Stage 3-4: Detect hands
        try:
            raw_landmarks = self._detector.detect(frame)
        except Exception as e:
            raise MediaPipeError(str(e)) from e

        if not raw_landmarks:
            self._state_manager.transition("no_hand_detected")
            return

        self._state_manager.transition("hand_detected")

        # Stage 5: Extract landmarks for primary hand
        dominant_hand = self._config.gesture_recognition.dominant_hand
        landmark = self._extractor.extract_all(raw_landmarks, dominant_hand)
        if not landmark:
            return
        landmark = landmark[0]

        # Stage 6: Classify gesture
        prediction = self._classifier.classify(landmark)

        # Stage 7: Noise filter
        prediction = self._noise_filter.filter(prediction, landmark, frame)
        if prediction.is_filtered:
            if self._logger:
                self._logger.debug(
                    "prediction_filtered",
                    gesture=prediction.gesture_name,
                    reason=prediction.filter_reason,
                    module="pipeline_runner"
                )
            return

        # Stage 8: Temporal filter (majority vote)
        gesture = self._temporal_filter.update(prediction)
        if gesture == "UNKNOWN":
            return

        self._state_manager.transition("gesture_stable")

        # Stage 9: Cooldown check
        partial = self._cooldown_manager.check(gesture, prediction.confidence)
        if partial is None:
            return

        # Stage 10: Generate command
        command = self._command_generator.generate(partial)
        self._state_manager.transition("command_emitted")

        # Send to transmitter
        self._command_queue.put_nowait(command)
        self._state_manager.transition("command_processed")

    @property
    def camera(self) -> "CameraModule":
        """Get the camera module."""
        return self._camera

    @property
    def is_running(self) -> bool:
        """Check if the pipeline is running."""
        return self._running
