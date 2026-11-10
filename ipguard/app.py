"""IPGuard application entry point and controller (signal wiring)."""
from __future__ import annotations

import argparse
import logging
import sys
import threading
import webbrowser

from PySide6.QtCore import QObject
from PySide6.QtWidgets import QApplication

from . import __version__
from .config import Config
from .floatwidget import FloatWidget
from .gate_server import GateServer
from .i18n import set_language, tr
from .ipprobe import IpProbe
from .models import IpReport
from .monitor import MonitorWorker
from .notifier import Notifier
from .resume import ResumeWatcher
from .scamalytics import ScamalyticsScraper
from .trayicon import TrayIcon

log = logging.getLogger(__name__)


class _State:
    """Thread-safe latest state, read by the local gate service."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.report: IpReport | None = None


class Controller(QObject):
    def __init__(self, app: QApplication, cfg: Config, probe: IpProbe, scraper: ScamalyticsScraper):
        super().__init__()
        self._app = app
        self._cfg = cfg
        self._state = _State()
        self._gate: GateServer | None = None

        self.widget = FloatWidget(cfg)
        self.tray = TrayIcon(cfg)
        self.notifier = Notifier(self.tray, cfg)
        self.worker = MonitorWorker(cfg, probe, scraper)
        # User intent, independent of Qt's window state: macOS may order the
        # window out on sleep while QWidget::isVisible() still reports True.
        self._widget_visible = not cfg.ui.start_hidden
        self._resume = ResumeWatcher(parent=self)
        self._resume.resumed.connect(self._on_resume)

        # Monitor thread -> UI
        self.worker.report_ready.connect(self._on_report)
        self.worker.ip_changed.connect(self.notifier.on_ip_change)
        self.worker.probe_error.connect(self._on_probe_error)
        # Floating widget
        self.widget.refresh_requested.connect(lambda: self.worker.refresh(force=True))
        self.widget.hide_requested.connect(self._hide_widget)
        self.widget.quit_requested.connect(self._app.quit)
        self.widget.top_toggled.connect(self._set_top)
        self.widget.language_selected.connect(self._set_language)
        self.widget.position_saved.connect(self._save_position)
        # Tray
        self.tray.toggle_requested.connect(self._toggle_widget)
        self.tray.refresh_requested.connect(lambda: self.worker.refresh(force=True))
        self.tray.gate_toggled.connect(self._set_gate)
        self.tray.top_toggled.connect(self._set_top)
        self.tray.page_requested.connect(self._open_page)
        self.tray.language_selected.connect(self._set_language)
        self.tray.quit_requested.connect(self._app.quit)

        self._app.aboutToQuit.connect(self._cleanup)

    # ---------- Lifecycle ----------
    def start(self) -> None:
        self.tray.show()
        if self._cfg.gate_server.enabled:
            self._start_gate()
        self.worker.start()
        self._resume.start()
        if self._widget_visible:
            self.widget.show_default()

    def _cleanup(self) -> None:
        self._resume.stop()
        self.worker.stop()
        if not self.worker.wait(5000):
            self.worker.terminate()
            self.worker.wait(1000)
        if self._gate:
            self._gate.stop()
        self._cfg.save()

    # ---------- Event handlers ----------
    def _on_report(self, report: IpReport) -> None:
        with self._state.lock:
            self._state.report = report
        self.widget.update_report(report)
        self.tray.update_level(report.risk_level(self._cfg.low_max, self._cfg.medium_max))
        score = "--" if report.score is None else f"{report.score}/100"
        self.tray.setToolTip(f"IPGuard\nIP: {report.ip or '--'}\nFraud Score: {score}")
        self.tray.act_page.setEnabled(bool(report.ip))
        self.notifier.on_report(report)

    def _on_probe_error(self, key: str) -> None:
        log.warning("%s", key)
        self.widget.show_notice(tr(key))

    def _hide_widget(self) -> None:
        self._widget_visible = False
        self.widget.hide()

    def _toggle_widget(self) -> None:
        self._widget_visible = not self._widget_visible
        if self._widget_visible:
            self.widget.show_default()
        else:
            self.widget.hide()

    def _on_resume(self) -> None:
        # macOS orders tool windows out during sleep; bring ours back if the
        # user did not explicitly hide it.
        log.info("System resumed from sleep")
        if self._widget_visible:
            self.widget.reveal()

    def _set_top(self, on: bool) -> None:
        self.widget.set_always_on_top(on)
        self.tray.act_top.setChecked(on)
        self._cfg.save()

    def _set_language(self, lang: str) -> None:
        if lang == self._cfg.language or lang not in ("en", "zh"):
            return
        set_language(lang)
        self._cfg.language = lang
        self.widget.retranslate()
        self.tray.rebuild_menu()
        self._cfg.save()

    def _set_gate(self, on: bool) -> None:
        self._cfg.gate_server.enabled = on
        if on:
            self._start_gate()
        elif self._gate:
            self._gate.stop()
            self._gate = None
        self._cfg.save()

    def _start_gate(self) -> None:
        if self._gate:
            return
        try:
            self._gate = GateServer(
                self._cfg.gate_server.host,
                self._cfg.gate_server.port,
                self._cfg.gate_server.token,
                self._state,
                self._cfg,
            )
            self._gate.start()
        except OSError as e:
            log.warning("Gate service failed to start (port in use?): %s", e)
            self._gate = None
            self.tray.act_gate.setChecked(False)

    def _open_page(self) -> None:
        with self._state.lock:
            ip = self._state.report.ip if self._state.report else None
        if ip:
            webbrowser.open(f"https://scamalytics.com/ip/{ip}")

    def _save_position(self, x: int, y: int) -> None:
        self._cfg.ui.pos_x = x
        self._cfg.ui.pos_y = y
        self._cfg.save()


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv if argv is None else argv)
    p = argparse.ArgumentParser(prog="ipguard", description=f"IPGuard v{__version__} — proxy IP fraud score monitor and security gate")
    p.add_argument("--config", metavar="PATH", help="Config file path")
    p.add_argument("--check", action="store_true", help="Run one gate check and exit (same as python -m ipguard.gate_cli)")
    p.add_argument("--max", type=int, default=None, help="Gate threshold (overrides config)")
    p.add_argument("--json", action="store_true", help="Print JSON with --check")
    p.add_argument("--no-gate", action="store_true", help="Disable the local gate HTTP service")
    p.add_argument("--log-level", default="INFO", help="Log level")
    args = p.parse_args(argv[1:])

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    cfg = Config.load(args.config)
    if args.max is not None:
        cfg.gate_threshold = args.max
    if args.no_gate:
        cfg.gate_server.enabled = False

    set_language(cfg.language)

    if args.check:
        from .gate_cli import run_check
        return run_check(cfg, max_score=args.max, as_json=args.json)

    app = QApplication([argv[0]])
    app.setApplicationName("IPGuard")
    app.setApplicationDisplayName("IPGuard")
    app.setQuitOnLastWindowClosed(False)  # tray app: keep running with all windows closed

    probe = IpProbe(cfg.request)
    scraper = ScamalyticsScraper(cfg.cache_dir, cfg.request, cfg.score_cache_ttl)
    controller = Controller(app, cfg, probe, scraper)
    controller.start()
    return app.exec()
