"""Notification policy: risk escalation / IP change / gate alert (deduplicated)."""
from __future__ import annotations

import logging

from .config import Config
from .i18n import tr
from .models import IpReport, LEVEL_META, RiskLevel
from .trayicon import TrayIcon

log = logging.getLogger(__name__)


class Notifier:
    def __init__(self, tray: TrayIcon, config: Config):
        self._tray = tray
        self._cfg = config
        self._first = True
        self._last_level = RiskLevel.UNKNOWN
        self._danger_active = False

    def on_report(self, report: IpReport) -> None:
        level = report.risk_level(self._cfg.low_max, self._cfg.medium_max)
        danger = report.is_danger(self._cfg.gate_threshold)
        label = tr(LEVEL_META[level].label)

        if self._first:
            # First result only establishes the baseline; alert immediately if already dangerous.
            self._first = False
            if danger and self._cfg.notify_on_danger:
                self._danger(report, label)
        else:
            if self._cfg.notify_on_level_up and level > self._last_level:
                self._tray.notify(
                    tr("notify.level_up.title"),
                    tr("notify.level_up.body", ip=report.ip, score=report.score, label=label),
                    level,
                )
            if self._cfg.notify_on_danger:
                if danger and not self._danger_active:
                    self._danger(report, label)
                elif not danger:
                    self._danger_active = False
        self._last_level = level

    def on_ip_change(self, old: str, new: str) -> None:
        if self._cfg.notify_on_ip_change:
            self._tray.notify(
                tr("notify.ip_change.title"),
                tr("notify.ip_change.body", old=old, new=new),
                RiskLevel.UNKNOWN,
            )

    def _danger(self, report: IpReport, label: str) -> None:
        self._danger_active = True
        self._tray.notify(
            tr("notify.danger.title"),
            tr("notify.danger.body",
               score=report.score, threshold=self._cfg.gate_threshold, label=label),
            RiskLevel.HIGH,
        )
