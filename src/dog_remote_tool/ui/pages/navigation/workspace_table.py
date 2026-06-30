from __future__ import annotations

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import QTableWidget


class WaypointTableWidget(QTableWidget):
    point_moved = pyqtSignal(int, int)

    def __init__(self, rows: int, columns: int) -> None:
        super().__init__(rows, columns)
        self._pressed_index = -1
        self.viewport().setCursor(Qt.OpenHandCursor)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self._pressed_index = self._index_at_position(event.pos())
            if self._pressed_index >= 0:
                self.viewport().setCursor(Qt.ClosedHandCursor)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        released_index = self._index_at_position(event.pos())
        pressed_index = self._pressed_index
        self._pressed_index = -1
        self.viewport().setCursor(Qt.OpenHandCursor)
        super().mouseReleaseEvent(event)
        if pressed_index >= 0 and released_index >= 0 and pressed_index != released_index:
            self.point_moved.emit(pressed_index, released_index)

    def _index_at_position(self, point) -> int:
        row = self.rowAt(point.y())
        column = self.columnAt(point.x())
        if row < 0 or column < 0:
            return -1
        return row * max(1, self.columnCount()) + column
