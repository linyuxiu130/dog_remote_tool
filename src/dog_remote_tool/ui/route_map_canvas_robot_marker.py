from __future__ import annotations

import math

from PyQt5.QtCore import QPointF, Qt
from PyQt5.QtGui import QColor, QPainter, QPen, QPolygonF


class RouteMapCanvasRobotMarkerMixin:
    def _draw_robot_pose(self, painter: QPainter) -> None:
        if self.robot_pose is None:
            return
        x, y, yaw = self.robot_pose
        point = self._world_to_widget(x, y)
        if point is None:
            return
        scale = self._marker_scale()
        outer_radius = 9.6 * scale
        inner_radius = 5.8 * scale
        length = 27.0 * scale
        head = 6.2 * scale
        dx = math.cos(yaw)
        dy = -math.sin(yaw)
        end = QPointF(point.x() + dx * length, point.y() + dy * length)
        left = QPointF(end.x() - dx * head + dy * head * 0.72, end.y() - dy * head - dx * head * 0.72)
        right = QPointF(end.x() - dx * head - dy * head * 0.72, end.y() - dy * head + dx * head * 0.72)

        painter.save()
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(220, 38, 38, 28))
        painter.drawEllipse(point, outer_radius * 1.55, outer_radius * 1.55)
        painter.setPen(QPen(QColor(255, 255, 255, 235), max(4, int(4.5 * scale)), Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        painter.drawLine(point, end)
        painter.setPen(QPen(QColor("#dc2626"), max(2, int(2.3 * scale)), Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        painter.drawLine(point, end)
        painter.setPen(QPen(QColor(255, 255, 255, 245), max(2, int(2.4 * scale))))
        painter.setBrush(QColor("#dc2626"))
        painter.drawPolygon(QPolygonF([end, left, right]))
        painter.drawEllipse(point, outer_radius, outer_radius)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#ef4444"))
        painter.drawEllipse(point, inner_radius, inner_radius)
        painter.restore()
