from __future__ import annotations

from PyQt5.QtCore import QRectF, Qt
from PyQt5.QtGui import QColor, QPainter, QPen

from dog_remote_tool.ui.route_map_canvas_robot_marker import RouteMapCanvasRobotMarkerMixin


class RouteMapCanvasNodeMarkerMixin(RouteMapCanvasRobotMarkerMixin):
    def _draw_nodes(self, painter: QPainter) -> None:
        if not self.show_nodes:
            return
        scale = self._marker_scale()
        font = painter.font()
        font.setBold(True)
        font.setPixelSize(max(8, int(8.5 * scale)))
        painter.save()
        painter.setFont(font)
        for node in self.graph.nodes.values():
            point = self._world_to_widget(node.x, node.y)
            if point is None:
                continue
            fill = QColor("#14b8a6")
            stroke = QColor("#ffffff")
            text_color = QColor("#0f172a")
            radius = 5.6 * scale
            stroke_width = max(2, int(2.0 * scale))
            if self.pending_node_id == node.id:
                fill = QColor("#22d3ee")
                stroke = QColor("#083344")
                radius = 7.2 * scale
                stroke_width = max(2, int(2.2 * scale))
            if self.selected_type == "node" and self.selected_id == node.id:
                fill = QColor("#f59e0b")
                stroke = QColor("#ffffff")
                radius = 7.8 * scale
                stroke_width = max(3, int(2.6 * scale))
            if ("node", node.id) in self.issue_targets:
                issue_level = self.issue_target_levels.get(("node", node.id))
                if issue_level == "warning":
                    fill = QColor("#f59e0b")
                    stroke = QColor("#ffffff")
                else:
                    fill = QColor("#dc2626")
                    stroke = QColor("#ffffff")
                radius = 8.2 * scale
                stroke_width = max(3, int(2.8 * scale))
                painter.setBrush(QColor(fill.red(), fill.green(), fill.blue(), 40))
                painter.setPen(Qt.NoPen)
                painter.drawEllipse(point, radius + 7.0 * scale, radius + 7.0 * scale)
            painter.setBrush(fill)
            painter.setPen(QPen(stroke, stroke_width))
            painter.drawEllipse(point, radius, radius)
            if self.show_node_labels or self.selected_id == node.id or self.pending_node_id == node.id or ("node", node.id) in self.issue_targets:
                label = str(node.id)
                metrics = painter.fontMetrics()
                label_width = max(18.0 * scale, metrics.horizontalAdvance(label) + 8.0 * scale)
                label_height = max(15.0 * scale, metrics.height() + 2.0 * scale)
                label_rect = QRectF(
                    point.x() - label_width / 2.0,
                    point.y() - radius - label_height - 4.0 * scale,
                    label_width,
                    label_height,
                )
                painter.setPen(Qt.NoPen)
                painter.setBrush(QColor(255, 255, 255, 232))
                painter.drawRoundedRect(label_rect, label_height / 2.0, label_height / 2.0)
                painter.setPen(QPen(QColor(15, 23, 42, 34), 1))
                painter.drawRoundedRect(label_rect, label_height / 2.0, label_height / 2.0)
                painter.setPen(text_color)
                painter.drawText(label_rect, Qt.AlignCenter, label)
        painter.restore()
