"""Input controls with deliberate wheel behavior."""

from __future__ import annotations

from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import QComboBox, QDoubleSpinBox, QSpinBox


class NoWheelSpinBox(QSpinBox):
    """A numeric input that only changes through keyboard or arrows."""

    def wheelEvent(self, event: QWheelEvent) -> None:
        event.ignore()


class NoWheelDoubleSpinBox(QDoubleSpinBox):
    """A floating-point input that ignores mouse-wheel changes."""

    def wheelEvent(self, event: QWheelEvent) -> None:
        event.ignore()


class NoWheelComboBox(QComboBox):
    """A selector that does not change accidentally while scrolling a page."""

    def wheelEvent(self, event: QWheelEvent) -> None:
        event.ignore()

