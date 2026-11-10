"""System tray icon and menu (macOS menu bar / Windows notification area)."""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtGui import QActionGroup
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from . import i18n
from .config import Config
from .i18n import LANGUAGES, tr
from .icons import make_status_icon
from .models import RiskLevel


class TrayIcon(QSystemTrayIcon):
    toggle_requested = Signal()
    refresh_requested = Signal()
    gate_toggled = Signal(bool)
    top_toggled = Signal(bool)
    page_requested = Signal()
    language_selected = Signal(str)
    quit_requested = Signal()

    def __init__(self, config: Config, parent=None):
        super().__init__(parent)
        self._cfg = config
        self.setIcon(make_status_icon(RiskLevel.UNKNOWN))
        self.setToolTip("IPGuard")
        self._build_menu()
        self.activated.connect(self._on_activated)

    def _build_menu(self, gate_on: bool | None = None, top_on: bool | None = None,
                    page_on: bool | None = None) -> None:
        """(Re)build the menu in the current language.

        Checked states are applied before connecting signals so rebuilding
        never emits spurious toggle events.
        """
        if gate_on is None:
            gate_on = self._cfg.gate_server.enabled
        if top_on is None:
            top_on = self._cfg.ui.always_on_top
        if page_on is None:
            page_on = False

        menu = QMenu()
        self.act_show = menu.addAction(tr("menu.show_widget"))
        self.act_refresh = menu.addAction(tr("menu.refresh"))
        menu.addSeparator()
        self.act_gate = menu.addAction(tr("menu.gate"))
        self.act_gate.setCheckable(True)
        self.act_gate.setChecked(gate_on)
        self.act_top = menu.addAction(tr("menu.on_top"))
        self.act_top.setCheckable(True)
        self.act_top.setChecked(top_on)
        self.act_page = menu.addAction(tr("menu.open_page"))
        self.act_page.setEnabled(page_on)
        menu.addSeparator()
        lang_menu = menu.addMenu(tr("menu.language"))
        group = QActionGroup(lang_menu)
        for code, name in LANGUAGES:
            act = lang_menu.addAction(name)
            act.setCheckable(True)
            act.setChecked(code == i18n.current_language())
            act.triggered.connect(lambda _=False, c=code: self.language_selected.emit(c))
            group.addAction(act)
        menu.addSeparator()
        self.act_quit = menu.addAction(tr("menu.quit"))
        self.setContextMenu(menu)
        self._menu = menu  # keep a reference so it is not garbage-collected

        self.act_show.triggered.connect(self.toggle_requested.emit)
        self.act_refresh.triggered.connect(self.refresh_requested.emit)
        self.act_gate.toggled.connect(self.gate_toggled.emit)
        self.act_top.toggled.connect(self.top_toggled.emit)
        self.act_page.triggered.connect(self.page_requested.emit)
        self.act_quit.triggered.connect(self.quit_requested.emit)

    def rebuild_menu(self) -> None:
        """Rebuild after a language switch, preserving the current states."""
        self._build_menu(
            gate_on=self.act_gate.isChecked(),
            top_on=self.act_top.isChecked(),
            page_on=self.act_page.isEnabled(),
        )

    def _on_activated(self, reason) -> None:
        # With a context menu set, macOS opens the menu on click; this path
        # mainly serves Windows/Linux.
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.toggle_requested.emit()

    def update_level(self, level: RiskLevel) -> None:
        self.setIcon(make_status_icon(level))

    def notify(self, title: str, body: str, level: RiskLevel) -> None:
        if self.isVisible():
            self.showMessage(title, body, make_status_icon(level), 8000)
