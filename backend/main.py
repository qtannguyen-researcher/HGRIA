"""System orchestrator for the HGRIA server startup and shutdown."""

import queue
import signal
import sys
import threading
from typing import Any, Optional

from backend.core.configuration import ConfigurationManager
from backend.core.models import Session
from backend.core.state_manager import StateManager
from backend.pipeline.camera import CameraModule
from backend.pipeline.commander import CommandTransmitter
from backend.pipeline.detector import HandDetector
from backend.pipeline.pipeline_runner import PipelineRunner
from backend.utils.logger import StructuredLogger


class SystemOrchestrator:
    """Orchestrates the entire HGRIA system startup and shutdown."""

    def __init__(self, config_path: str = "config/config.json") -> None:
        """
        Initialize the system orchestrator.

        Args:
            config_path: Path to the configuration JSON file
        """
        self._config: Optional[ConfigurationManager] = None
        self._logger: Optional[StructuredLogger] = None
        self._session: Optional[Session] = None
        self._state_manager: Optional[StateManager] = None
        self._cmd_queue: Optional[queue.Queue] = None
        self._pipeline: Optional[PipelineRunner] = None
        self._app: Any = None
        self._socketio: Any = None
        self._config_path = config_path
        self._shutdown_requested = False

    def start(self) -> None:
        """Start the entire HGRIA system."""
        try:
            self._logger = StructuredLogger(self._get_minimal_config())
            self._logger.info("startup_begin", module="orchestrator")

            # 1. Configuration
            self._config = ConfigurationManager(self._config_path)
            self._logger.info("config_loaded", module="orchestrator")

            # 2. Logger (with config)
            self._logger = StructuredLogger(self._config)

            # 3. State Manager
            self._state_manager = StateManager(None, self._logger)

            # 4. Session
            self._session = Session()

            # 5. Command queue
            self._cmd_queue = queue.Queue(maxsize=20)

            # 6. MediaPipe detector
            self._logger.info("mediapipe_init_start", module="orchestrator")
            detector = HandDetector(self._config, self._logger)
            self._logger.info("mediapipe_ready", module="orchestrator")

            # 7. Camera
            camera = CameraModule(self._config)
            self._logger.info("camera_ready", module="orchestrator")

            # 8. Flask app
            from backend.app import create_app
            self._app, self._socketio = create_app(
                self._config, self._session,
                self._state_manager, self._cmd_queue, self._logger
            )
            # Set socketio reference in state manager
            self._state_manager._sio = self._socketio
            self._logger.info("flask_server_ready", module="orchestrator")

            # 9. Pipeline runner
            self._pipeline = PipelineRunner(
                self._config, self._cmd_queue, self._state_manager,
                camera=camera, detector=detector, logger=self._logger
            )

            # 10. Register signal handlers
            signal.signal(signal.SIGINT, self._shutdown)
            signal.signal(signal.SIGTERM, self._shutdown)

            # 11. Start pipeline in background
            self._pipeline.start()
            self._logger.info("pipeline_started", module="orchestrator")

            # 12. Start ngrok if available
            public_url = self._start_ngrok()
            if public_url:
                print(f"Server URL: http://{self._config.server.host}:{self._config.server.port}")
                print(f"Public URL: {public_url}")
            else:
                print(f"Server running at: http://{self._config.server.host}:{self._config.server.port}")

            # 13. Start Flask server (blocks)
            self._logger.info("server_starting", module="orchestrator")
            self._socketio.run(
                self._app,
                host=self._config.server.host,
                port=self._config.server.port,
                use_reloader=False,
                allow_unsafe_werkzeug=True
            )

        except Exception as e:
            from backend.core.errors import CameraInitializationError
            if isinstance(e, CameraInitializationError):
                msg = (
                    f"FATAL: Cannot open camera — {e}\n"
                    "  - Check that a webcam is connected and not in use by another app.\n"
                    "  - To run without a camera (browser-based), set \"colab_mode\": true in config/config.json."
                )
                print(msg, file=sys.stderr)
            elif self._logger:
                self._logger.critical("startup_failed", error=str(e), module="orchestrator")
            else:
                print(f"FATAL: Startup failed: {e}", file=sys.stderr)
            raise SystemExit(1) from e

    def _get_minimal_config(self) -> Any:
        """Get a minimal config for initial logger setup."""
        class MinimalConfig:
            class Logging:
                level = "INFO"
                log_to_file = False
            logging = Logging()
        return MinimalConfig()

    def _start_ngrok(self) -> Optional[str]:
        """Start ngrok tunnel if available."""
        try:
            from pyngrok import ngrok
            port = self._config.server.port if self._config else 5000
            tunnel = ngrok.connect(port, "http")
            public_url = tunnel.public_url.replace("http://", "https://")
            self._logger.info("ngrok_tunnel_opened", url=public_url, module="orchestrator")
            return public_url
        except ImportError:
            self._logger.warning(
                "pyngrok_not_installed",
                msg="Install pyngrok for automatic tunnel",
                module="orchestrator"
            )
            return None
        except Exception as e:
            self._logger.warning(
                "ngrok_tunnel_failed",
                error=str(e),
                module="orchestrator"
            )
            return None

    def _shutdown(self, signum: Any = None, frame: Any = None) -> None:
        """Graceful shutdown handler."""
        if self._shutdown_requested:
            return
        self._shutdown_requested = True

        self._logger.info("shutdown_begin", module="orchestrator")

        # Stop pipeline
        if self._pipeline:
            self._pipeline.stop()

        # Emit shutdown event
        if self._socketio:
            self._socketio.emit("server_shutdown", {"reason": "SIGINT"})

        # Flush logger
        if self._logger:
            self._logger.flush()
            self._logger.stop()

        self._logger.info("shutdown_complete", module="orchestrator")
        raise SystemExit(0)


def main() -> None:
    """Main entry point."""
    orchestrator = SystemOrchestrator()
    orchestrator.start()


if __name__ == "__main__":
    main()
