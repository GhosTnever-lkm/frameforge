from __future__ import annotations

from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QWidget

from ..core.benchmark import Benchmark


class FrameTimeChart(QWidget):
    """Accessible, dependency-free chart of frame-time distribution buckets."""

    _labels = ("< 8.33", "8.33–16.67", "16.67–33.33", "33.33–50", "50–100", "> 100")
    _before_color = QColor("#72a8ff")
    _after_color = QColor("#45d6a0")
    _grid_color = QColor("#293a56")
    _text_color = QColor("#a1b1cc")

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(260)
        self.setAccessibleName("Распределение времени кадров до и после")
        self.setToolTip("Доля кадров по диапазонам времени кадра в миллисекундах")
        self._before: Benchmark | None = None
        self._after: Benchmark | None = None

    def set_runs(self, before: Benchmark | None, after: Benchmark | None) -> None:
        self._before = before
        self._after = after
        self.update()

    def paintEvent(self, event):  # noqa: N802 - Qt event naming
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor("#111a2c"))

        area = self.rect().adjusted(54, 30, -18, -56)
        painter.setPen(QPen(self._grid_color, 1))
        painter.setFont(QFont("Segoe UI", 8))
        for percent in (0, 25, 50, 75, 100):
            y = area.bottom() - area.height() * percent / 100
            painter.drawLine(int(area.left()), int(y), int(area.right()), int(y))
            painter.setPen(self._text_color)
            painter.drawText(QRectF(2, y - 8, 44, 16), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, f"{percent}%")
            painter.setPen(QPen(self._grid_color, 1))

        runs = ((self._before, self._before_color), (self._after, self._after_color))
        group_width = area.width() / len(self._labels)
        bar_width = min(24, group_width * 0.28)
        for index, label in enumerate(self._labels):
            center = area.left() + group_width * (index + 0.5)
            for offset, (run, color) in enumerate(runs):
                if run is None:
                    continue
                share = 100 * run.frame_time_buckets[index] / run.sample_count
                height = area.height() * share / 100
                x = center + (-bar_width - 2 if offset == 0 else 2)
                y = area.bottom() - height
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(color)
                painter.drawRoundedRect(QRectF(x, y, bar_width, height), 3, 3)
                if share >= 7:
                    painter.setPen(QPen(QColor("#0b1020")))
                    painter.drawText(QRectF(x, y + 2, bar_width, 16), Qt.AlignmentFlag.AlignCenter, f"{share:.0f}")
            painter.setPen(self._text_color)
            painter.drawText(QRectF(center - group_width / 2, area.bottom() + 8, group_width, 34), Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop, label)

        legend_y = self.height() - 18
        for index, (run, color) in enumerate(runs):
            if run is None:
                continue
            x = 58 + index * 148
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color)
            painter.drawRoundedRect(QRectF(x, legend_y - 10, 10, 10), 2, 2)
            painter.setPen(self._text_color)
            painter.drawText(x + 16, legend_y, "До: " + run.name if index == 0 else "После: " + run.name)
        painter.end()
