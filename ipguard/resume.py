"""Detect resume from system sleep (macOS lid close / Windows suspend).

QTimer does not fire while the machine is asleep, so the first tick after
wake-up shows a wall-clock gap far larger than the timer interval. That is
enough to detect resume without any platform-specific API or extra dependency.
"""
from __future__ import annotations

import time
from collections.abc import Callable

from PySide6.QtCore import QObject, QTimer, Signal


class ResumeWatcher(QObject):
    """Emit ``resumed`` once when the event loop was suspended for a long gap."""

    resumed = Signal()

    def __init__(self, interval_ms: int = 10_000, threshold_s: float = 30.0,
                 clock: Callable[[], float] = time.time, parent=None):
        super().__init__(parent)
        self._threshold = threshold_s
        self._clock = clock
        self._last = clock()
        self._timer = QTimer(self)
        self._timer.setInterval(interval_ms)
        self._timer.timeout.connect(self.check)

    def start(self) -> None:
        self._last = self._clock()
        self._timer.start()

    def stop(self) -> None:
        self._timer.stop()

    def check(self) -> None:
        now = self._clock()
        gap = now - self._last
        self._last = now
        if gap >= self._threshold:
            self.resumed.emit()
