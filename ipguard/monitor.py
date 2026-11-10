"""Background monitor thread: polls the external IP, re-scrapes on change or cache expiry.

Implementation: interruptible polling via a command queue + timed wait (no busy loop).
- probes the external IP every ip_check_interval seconds (lightweight request);
- IP changed  -> immediately re-scrapes the fraud score (cache bypassed);
- IP unchanged -> cache lookup; zero Scamalytics requests while the TTL is valid;
- manual refresh -> a "force" command is queued.
"""
from __future__ import annotations

import logging
import queue

from PySide6.QtCore import QThread, Signal

from .config import Config
from .ipprobe import IpProbe
from .models import utcnow
from .scamalytics import ScamalyticsScraper

log = logging.getLogger(__name__)


class MonitorWorker(QThread):
    report_ready = Signal(object)   # IpReport
    ip_changed = Signal(str, str)   # old_ip, new_ip
    probe_error = Signal(str)       # i18n message key

    def __init__(self, config: Config, probe: IpProbe, scraper: ScamalyticsScraper, parent=None):
        super().__init__(parent)
        self._cfg = config
        self._probe = probe
        self._scraper = scraper
        self._cmds: queue.Queue[str] = queue.Queue()
        self._current_ip: str | None = None

    def refresh(self, force: bool = False) -> None:
        """Request one check (force=True bypasses the fraud score cache). Thread-safe."""
        self._cmds.put("force" if force else "tick")

    def stop(self) -> None:
        self._cmds.put("stop")

    def run(self) -> None:  # QThread entry point, runs in the worker thread
        first = True
        while True:
            timeout = 0 if first else self._cfg.ip_check_interval
            first = False
            try:
                cmd = self._cmds.get(timeout=timeout)
            except queue.Empty:
                cmd = "tick"
            if cmd == "stop":
                return
            force = cmd == "force"

            ip = self._probe.current_ip()
            if ip is None:
                self.probe_error.emit("probe.failed")
                continue

            old = self._current_ip
            self._current_ip = ip
            changed = old is not None and ip != old

            report = self._scraper.fetch(ip, force=force or changed)
            report.checked_at = utcnow()
            if changed:
                self.ip_changed.emit(old, ip)
            self.report_ready.emit(report)
