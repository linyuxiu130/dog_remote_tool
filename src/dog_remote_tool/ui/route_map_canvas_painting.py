from __future__ import annotations

from PyQt5.QtCore import QRectF, Qt
from PyQt5.QtGui import QColor, QPainter


class RouteMapCanvasPaintingMixin:
    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.fillRect(self.rect(), QColor("#f8fbff"))
        target = self._map_rect()
        if self.pixmap and not self.pixmap.isNull():
            painter.drawPixmap(target, self.pixmap, QRectF(self.pixmap.rect()))
            if self.show_inflation_overlay and self.inflation_overlay and not self.inflation_overlay.isNull():
                painter.drawPixmap(target, self.inflation_overlay, QRectF(self.inflation_overlay.rect()))
        else:
            painter.setPen(QColor("#8aa0b8"))
            painter.drawText(self.rect(), Qt.AlignCenter, "打开 map.yaml 加载底图")
        self._draw_grid_frame(painter, target)
        self._draw_edges(painter)
        self._draw_nodes(painter)
        self._draw_robot_pose(painter)
        if self.hover_text:
            painter.setPen(QColor("#52677e"))
            painter.drawText(14, self.height() - 14, self.hover_text)
