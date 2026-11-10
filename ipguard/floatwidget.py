"""Frameless translucent floating widget: fraud score / IP / ISP display.

Supports dragging, double-click refresh, a context menu and runtime language
switching (retranslate). Position is remembered in config.
"""
from __future__ import annotations

from PySide6.QtCore import QPoint, QRectF, Qt, Signal
from PySide6.QtGui import QActionGroup, QColor, QGuiApplication, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QHBoxLayout, QLabel, QMenu, QPushButton, QVBoxLayout, QWidget

from . import i18n
from .config import Config
from .i18n import LANGUAGES, tr
from .models import IpReport, LEVEL_META, RiskLevel

_CARD_BG = QColor(28, 28, 36, 240)
_DANGER_BORDER = QColor(255, 91, 91, 220)
_NORMAL_BORDER = QColor(255, 255, 255, 26)
_TEXT = "#E8E8EC"
_SUB = "#9A9AA5"

_BTN_QSS = """
QPushButton {
    background: rgba(255, 255, 255, 20);
    border: none; border-radius: 6px;
    color: #D0D0D8; font-size: 13px;
}
QPushButton:hover { background: rgba(255, 255, 255, 44); }
QPushButton:pressed { background: rgba(255, 255, 255, 60); }
"""


class Dot(QWidget):
    """Colored status dot."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self._level = RiskLevel.UNKNOWN
        self.setFixedSize(14, 14)

    def set_level(self, level: RiskLevel) -> None:
        self._level = level
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(LEVEL_META[self._level].color))
        p.drawEllipse(QRectF(1, 1, self.width() - 2, self.height() - 2))
        p.end()


class FloatWidget(QWidget):
    refresh_requested = Signal()
    hide_requested = Signal()
    quit_requested = Signal()
    top_toggled = Signal(bool)
    language_selected = Signal(str)
    position_saved = Signal(int, int)

    def __init__(self, config: Config, parent=None):
        flags = Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool
        if config.ui.always_on_top:
            flags |= Qt.WindowType.WindowStaysOnTopHint
        super().__init__(parent, flags)
        self._cfg = config
        self._danger = False
        self._last_report: IpReport | None = None
        self._top_applied = False
        self._drag_offset: QPoint | None = None
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        # macOS: keep the tool window visible even while the app is inactive.
        if hasattr(Qt.WidgetAttribute, "WA_MacAlwaysShowToolWindow"):
            self.setAttribute(Qt.WidgetAttribute.WA_MacAlwaysShowToolWindow)
        self.setWindowTitle("IPGuard")
        self.setFixedWidth(248)
        if config.ui.opacity < 1.0:
            self.setWindowOpacity(config.ui.opacity)
        self._build_ui()

    # ---------- UI construction ----------
    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 12, 14, 12)
        outer.setSpacing(4)

        top = QHBoxLayout()
        top.setSpacing(6)
        self._dot = Dot()
        self._score = QLabel("--")
        self._score.setStyleSheet(f"font-size: 21px; font-weight: 700; color: {_TEXT}; background: transparent;")
        self._score_scale = QLabel("/ 100")
        self._score_scale.setStyleSheet(f"font-size: 11px; color: {_SUB}; background: transparent;")
        self._risk = QLabel(tr("widget.checking"))
        self._risk.setStyleSheet(f"font-size: 12px; color: {_SUB}; background: transparent;")
        self._btn_refresh = QPushButton("⟳")
        self._btn_refresh.setFixedSize(24, 24)
        self._btn_hide = QPushButton("—")
        self._btn_hide.setFixedSize(24, 24)
        for b in (self._btn_refresh, self._btn_hide):
            b.setStyleSheet(_BTN_QSS)
        top.addWidget(self._dot)
        top.addWidget(self._score)
        top.addWidget(self._score_scale)
        top.addWidget(self._risk)
        top.addStretch(1)
        top.addWidget(self._btn_refresh)
        top.addWidget(self._btn_hide)
        outer.addLayout(top)

        self._ip = QLabel(tr("widget.ip", ip="--"))
        self._ip.setStyleSheet(f"font-size: 13px; color: {_TEXT}; background: transparent;")
        self._sub = QLabel(tr("widget.waiting"))
        self._sub.setWordWrap(True)
        self._sub.setStyleSheet(f"font-size: 11px; color: {_SUB}; background: transparent;")
        self._warn = QLabel("")
        self._warn.setWordWrap(True)
        self._warn.setStyleSheet("font-size: 11px; font-weight: 600; color: #FF6B6B; background: transparent;")
        self._warn.hide()
        outer.addWidget(self._ip)
        outer.addWidget(self._sub)
        outer.addWidget(self._warn)

        self._btn_refresh.clicked.connect(self.refresh_requested.emit)
        self._btn_hide.clicked.connect(self.hide_requested.emit)
        self.retranslate()

    def retranslate(self) -> None:
        """Refresh all localized texts after a language switch."""
        self._btn_refresh.setToolTip(tr("widget.btn.refresh.tip"))
        self._btn_hide.setToolTip(tr("widget.btn.hide.tip"))
        self.update_report(self._last_report)

    # ---------- Data update ----------
    def update_report(self, report: IpReport | None) -> None:
        self._last_report = report
        self._danger = bool(report and report.is_danger(self._cfg.gate_threshold))
        if report is None or report.ip is None:
            self._dot.set_level(RiskLevel.UNKNOWN)
            self._score.setText("--")
            self._score.setStyleSheet(f"font-size: 21px; font-weight: 700; color: {_TEXT}; background: transparent;")
            self._risk.setText(tr("widget.checking"))
            self._risk.setStyleSheet(f"font-size: 12px; color: {_SUB}; background: transparent;")
            self._ip.setText(tr("widget.ip", ip="--"))
            self._sub.setText(tr("widget.waiting"))
            self._warn.hide()
            self.update()
            return

        level = report.risk_level(self._cfg.low_max, self._cfg.medium_max)
        meta = LEVEL_META[level]
        label = tr(meta.label)
        self._dot.set_level(level)
        self._score.setText(str(report.score) if report.score is not None else "--")
        self._score.setStyleSheet(f"font-size: 21px; font-weight: 700; color: {meta.color}; background: transparent;")
        self._risk.setText(f"{meta.emoji} {label}")
        self._risk.setStyleSheet(f"font-size: 12px; color: {meta.color}; background: transparent;")
        self._ip.setText(tr("widget.ip", ip=report.ip))

        src = {"scamalytics": tr("widget.source.live"),
               "cache": tr("widget.source.cache"),
               "stale-cache": tr("widget.source.stale")}.get(report.source, "")
        parts = [p for p in (report.isp, report.country) if p]
        if src:
            parts.append(src)
        if report.fetched_at:
            # Data freshness (local time): for cached reports this is when the
            # score was actually scraped, which is what users want to compare
            # against their clock.
            parts.append(tr("widget.fetched_at", time=report.fetched_at.astimezone().strftime("%H:%M")))
        if report.error:
            parts.append(report.error[:60])
        self._sub.setText(" · ".join(parts))

        if self._danger and report.score is not None:
            self._warn.setText(tr("widget.warn", score=report.score, threshold=self._cfg.gate_threshold))
            self._warn.show()
        else:
            self._warn.hide()
        self.update()

    def show_notice(self, msg: str) -> None:
        """Non-fatal notice (e.g. probe failure), shown in the risk label."""
        self._risk.setText(f"⚠️ {msg[:24]}")
        self._risk.setStyleSheet(f"font-size: 11px; color: {_SUB}; background: transparent;")

    # ---------- Painting and interaction ----------
    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        path = QPainterPath()
        path.addRoundedRect(rect, 14, 14)
        p.fillPath(path, _CARD_BG)
        p.setPen(QPen(_DANGER_BORDER if self._danger else _NORMAL_BORDER, 1.5))
        p.drawPath(path)
        p.end()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._drag_offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_offset)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if self._drag_offset is not None:
            self._drag_offset = None
            self.position_saved.emit(self.x(), self.y())

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.refresh_requested.emit()

    def contextMenuEvent(self, event) -> None:  # noqa: N802
        menu = QMenu(self)
        menu.addAction(tr("menu.refresh"), self.refresh_requested.emit)
        act_top = menu.addAction(tr("menu.on_top"))
        act_top.setCheckable(True)
        act_top.setChecked(self._cfg.ui.always_on_top)
        act_top.toggled.connect(self.top_toggled.emit)
        menu.addMenu(self._language_menu(menu))
        menu.addSeparator()
        menu.addAction(tr("menu.hide_to_tray"), self.hide_requested.emit)
        menu.addAction(tr("menu.quit"), self.quit_requested.emit)
        menu.exec(self.mapToGlobal(event.pos()))

    def _language_menu(self, parent) -> QMenu:
        lang_menu = QMenu(tr("menu.language"), parent)
        group = QActionGroup(lang_menu)
        for code, name in LANGUAGES:
            act = lang_menu.addAction(name)
            act.setCheckable(True)
            act.setChecked(code == i18n.current_language())
            act.triggered.connect(lambda _=False, c=code: self.language_selected.emit(c))
            group.addAction(act)
        return lang_menu

    # ---------- Position and always-on-top ----------
    def set_always_on_top(self, on: bool) -> None:
        visible = self.isVisible()
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, on)
        if visible:
            self.show()  # setWindowFlag hides the window on macOS; re-show it
        self._cfg.ui.always_on_top = on

    def reveal(self) -> None:
        """Force the window back on screen after system sleep.

        macOS can order tool windows out while the display sleeps without
        telling Qt; ``show()`` alone can be a no-op then, so hide first to
        guarantee a fresh native map.
        """
        if self.isVisible():
            self.hide()
        self.show_default()

    def show_default(self) -> None:
        """Show at the remembered position, or bottom-right of the screen."""
        if self._cfg.ui.pos_x is not None and self._cfg.ui.pos_y is not None:
            self.move(self._cfg.ui.pos_x, self._cfg.ui.pos_y)
        else:
            geo = QGuiApplication.primaryScreen().availableGeometry()
            self.move(geo.right() - self.width() - 24, geo.bottom() - self.height() - 24)
        self.show()
        if self._cfg.ui.always_on_top and not self._top_applied:
            # macOS quirk: WindowStaysOnTopHint passed to the constructor is not
            # applied until re-set after the window has been shown. Without this
            # the widget opens behind other windows and appears "missing".
            self._top_applied = True
            self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
            self.show()
        self.raise_()
