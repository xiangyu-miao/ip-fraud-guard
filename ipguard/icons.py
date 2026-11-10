"""Status icons drawn at runtime with QPainter — no bundled image assets.

The icon is a colored circle (gray "?" when unknown). Sizes 22/44/64 are
registered so Qt picks the right pixmap for the current device pixel ratio.
Registering only one manually-DPR'd pixmap made the macOS menu bar clip the
circle into a quarter ("fan") shape, hence the multi-size approach.
"""
from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap

from .models import LEVEL_META, RiskLevel


def _pixmap(level: RiskLevel, size: int) -> QPixmap:
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(LEVEL_META[level].color))
    margin = max(1, round(size * 0.10))
    p.drawEllipse(QRectF(margin, margin, size - 2 * margin, size - 2 * margin))
    if level == RiskLevel.UNKNOWN:
        font = QFont()
        font.setPixelSize(int(size * 0.52))
        font.setBold(True)
        p.setFont(font)
        p.setPen(QColor(255, 255, 255, 235))
        p.drawText(QRectF(0, 0, size, size), Qt.AlignmentFlag.AlignCenter, "?")
    p.end()
    return pm


def make_status_icon(level: RiskLevel) -> QIcon:
    """Colored status dot usable for tray, notifications and widget."""
    icon = QIcon()
    for size in (22, 44, 64):
        icon.addPixmap(_pixmap(level, size))
    return icon
