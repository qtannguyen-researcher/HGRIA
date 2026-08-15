"""Cooldown manager for rate-limiting gesture emissions."""

import time
from typing import TYPE_CHECKING, Any, Dict, Optional

if TYPE_CHECKING:
    from backend.core.configuration import ConfigurationManager


class CooldownManager:
    """Manages per-gesture cooldowns to prevent rapid-fire commands."""

    DEFAULT_COOLDOWN_MS = 500

    def __init__(self, config: "ConfigurationManager", logger: Any = None) -> None:
        """
        Initialize the cooldown manager.

        Args:
            config: Configuration object with gesture_cooldowns_ms
            logger: Optional logger
        """
        self._cooldowns: Dict[str, int] = config.gesture_cooldowns_ms
        self._last_emission: Dict[str, float] = {}
        self._logger = logger

    def check(self, gesture: str, confidence: float) -> Optional[Dict[str, Any]]:
        """
        Check if a gesture can be emitted based on its cooldown.

        Args:
            gesture: The gesture name
            confidence: The gesture confidence

        Returns:
            A partial command dict if cooldown has elapsed, None otherwise
        """
        cooldown_ms = self._cooldowns.get(gesture, self.DEFAULT_COOLDOWN_MS)
        now_ms = time.monotonic() * 1000
        last = self._last_emission.get(gesture, 0.0)
        elapsed = now_ms - last

        if elapsed < cooldown_ms:
            self._log_debug(
                "cooldown_active",
                gesture=gesture,
                elapsed_ms=round(elapsed, 1),
                cooldown_ms=cooldown_ms
            )
            return None

        self._last_emission[gesture] = now_ms
        self._log_debug(
            "cooldown_expired",
            gesture=gesture,
            cooldown_ms=cooldown_ms
        )
        return {"gesture_name": gesture, "confidence": confidence}

    def _log_debug(self, event: str, **kwargs: Any) -> None:
        """Log at DEBUG level if logger is available."""
        if self._logger:
            self._logger.debug(event, module="cooldown_manager", **kwargs)

    def reset(self, gesture: Optional[str] = None) -> None:
        """
        Reset cooldown tracking for a gesture or all gestures.

        Args:
            gesture: Optional specific gesture to reset, or None for all
        """
        if gesture:
            self._last_emission.pop(gesture, None)
        else:
            self._last_emission.clear()
