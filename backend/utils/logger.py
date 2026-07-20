"""Structured JSON logger for the HGRIA system.

Writes each entry as a single-line JSON object to stdout, with a background
thread + queue so writes never block the inference loop.
"""

import json
import logging
import sys
import threading
import queue
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from logging.handlers import RotatingFileHandler


LOG_LEVELS = {
    "DEBUG": logging.DEBUG,    # 10
    "INFO": logging.INFO,      # 20
    "WARNING": logging.WARNING, # 30
    "ERROR": logging.ERROR,    # 40
    "CRITICAL": logging.CRITICAL, # 50
}


class StructuredLogger:
    """Thread-safe structured JSON logger using a background drain thread."""

    def __init__(self, config: Any) -> None:
        """
        Initialize the structured logger.

        Args:
            config: Configuration object with logging.* fields
        """
        level_name = getattr(config, 'logging', None)
        if level_name and hasattr(level_name, 'level'):
            self._level = LOG_LEVELS.get(level_name.level, logging.INFO)
        else:
            self._level = logging.INFO

        self._queue: queue.Queue = queue.Queue()
        self._file_handler: Optional[logging.Handler] = None
        self._drain_thread: Optional[threading.Thread] = None
        self._running = True

        # Set up rotating file handler if configured
        if level_name and getattr(level_name, 'log_to_file', False):
            self._setup_file_handler(level_name)

        # Start background drain thread
        self._drain_thread = threading.Thread(target=self._drain, daemon=True)
        self._drain_thread.start()

    def _setup_file_handler(self, logging_config: Any) -> None:
        """Set up rotating file handler for Google Drive log path."""
        try:
            log_path = getattr(logging_config, 'log_file_path', '/tmp/hgria/logs/')
            max_size = getattr(logging_config, 'max_log_file_size_mb', 10) * 1024 * 1024
            max_files = getattr(logging_config, 'max_log_files', 5)

            # Ensure directory exists
            import os
            os.makedirs(log_path, exist_ok=True)

            self._file_handler = RotatingFileHandler(
                os.path.join(log_path, 'hgria.log'),
                maxBytes=max_size,
                backupCount=max_files
            )
        except (OSError, PermissionError) as e:
            # Fall back to stdout-only if file logging fails
            print(f"WARNING: Could not set up file logging: {e}", file=sys.stderr)
            self._file_handler = None

    def _entry(self, level: str, event: str, **kwargs: Any) -> Dict[str, Any]:
        """Build a structured log entry dictionary."""
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(timespec='milliseconds'),
            "level": level,
            "module": kwargs.pop("_module", "unknown"),
            "event": event,
            **kwargs,
        }

    def _should_log(self, level_name: str) -> bool:
        """Check if the given level should be logged."""
        level_value = LOG_LEVELS.get(level_name, logging.INFO)
        return level_value >= self._level

    def debug(self, event: str, **kwargs: Any) -> None:
        """Log a DEBUG level entry."""
        if self._should_log("DEBUG"):
            kwargs["_module"] = kwargs.pop("_module", "unknown")
            self._queue.put_nowait(self._entry("DEBUG", event, **kwargs))

    def info(self, event: str, **kwargs: Any) -> None:
        """Log an INFO level entry."""
        if self._should_log("INFO"):
            kwargs["_module"] = kwargs.pop("_module", "unknown")
            self._queue.put_nowait(self._entry("INFO", event, **kwargs))

    def warning(self, event: str, **kwargs: Any) -> None:
        """Log a WARNING level entry."""
        kwargs["_module"] = kwargs.pop("_module", "unknown")
        self._queue.put_nowait(self._entry("WARNING", event, **kwargs))

    def error(self, event: str, **kwargs: Any) -> None:
        """Log an ERROR level entry."""
        kwargs["_module"] = kwargs.pop("_module", "unknown")
        self._queue.put_nowait(self._entry("ERROR", event, **kwargs))

    def critical(self, event: str, **kwargs: Any) -> None:
        """Log a CRITICAL level entry."""
        kwargs["_module"] = kwargs.pop("_module", "unknown")
        self._queue.put_nowait(self._entry("CRITICAL", event, **kwargs))

    def flush(self) -> None:
        """Block until the queue is completely drained."""
        self._queue.join()

    def stop(self) -> None:
        """Stop the drain thread gracefully."""
        self._running = False
        self._queue.put_nowait(None)  # Sentinel to wake up the thread
        if self._drain_thread:
            self._drain_thread.join(timeout=5.0)

    def _drain(self) -> None:
        """Background thread that drains the queue and writes log entries."""
        while self._running:
            try:
                entry = self._queue.get(timeout=0.5)
                if entry is None:
                    self._queue.task_done()
                    continue

                line = json.dumps(entry, ensure_ascii=False)

                # Write to stdout
                print(line, file=sys.stdout, flush=True)

                # Write to file if configured
                if self._file_handler:
                    self._file_handler.emit(logging.LogRecord(
                        name="hgria",
                        level=LOG_LEVELS.get(entry.get("level", "INFO"), logging.INFO),
                        pathname="",
                        lineno=0,
                        msg=line,
                        args=(),
                        exc_info=None
                    ))

                self._queue.task_done()
            except queue.Empty:
                continue
            except Exception:
                # Never let the drain thread crash
                pass
