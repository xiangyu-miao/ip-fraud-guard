"""Unit tests for sleep/resume detection."""
from __future__ import annotations

import unittest

from PySide6.QtCore import QCoreApplication

from ipguard.resume import ResumeWatcher


class TestResumeWatcher(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # QTimer needs an event dispatcher; no GUI is required.
        cls._app = QCoreApplication.instance() or QCoreApplication([])

    def _watcher(self, start: float):
        now = [start]
        w = ResumeWatcher(clock=lambda: now[0])
        fired = []
        w.resumed.connect(lambda: fired.append(True))
        return w, now, fired

    def test_normal_ticks_do_not_fire(self):
        w, now, fired = self._watcher(100.0)
        for _ in range(10):
            now[0] += 10.0
            w.check()
        self.assertEqual(fired, [])

    def test_sleep_gap_fires_once(self):
        w, now, fired = self._watcher(100.0)
        now[0] += 3600.0  # machine slept for an hour
        w.check()
        self.assertEqual(fired, [True])
        now[0] += 10.0
        w.check()
        self.assertEqual(fired, [True])  # only once per gap

    def test_start_resets_baseline(self):
        w, now, fired = self._watcher(100.0)
        now[0] += 500.0
        w.start()
        w.check()
        self.assertEqual(fired, [])


if __name__ == "__main__":
    unittest.main()
