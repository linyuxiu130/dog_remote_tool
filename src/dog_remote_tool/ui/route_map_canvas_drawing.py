from __future__ import annotations

import math

from PyQt5.QtCore import QPointF, Qt
from PyQt5.QtGui import QColor, QPainter, QPen, QPolygonF

from dog_remote_tool.ui.route_map_canvas_edge_rendering import (
    arrow_geometry as _arrow_geometry,
    highest_edge_issue_level as _highest_edge_issue_level,
    route_edge_color_for_directions as _route_edge_color_for_directions,
    trim_polyline_to_distance as _trim_polyline_to_distance,
    visual_edge_groups as _visual_edge_groups,
)
from dog_remote_tool.ui.route_map_canvas_node_marker import RouteMapCanvasNodeMarkerMixin


class RouteMapCanvasDrawingMixin(RouteMapCanvasNodeMarkerMixin):
    def _draw_grid_frame(self, painter: QPainter, target) -> None:
        painter.setPen(QPen(QColor("#d7e2ef"), 1))
        painter.drawRect(target)

    def _marker_scale(self) -> float:
        return max(1.0, min(2.2, math.sqrt(max(1.0, self.view_zoom))))

    def _draw_edges(self, painter: QPainter) -> None:
        scale = self._marker_scale()
        for group in _visual_edge_groups(self.graph.edges.values()):
            points = [self._world_to_widget(point[0], point[1]) for point in group["coordinates"]]
            points = [point for point in points if point is not None]
            if len(points) < 2:
                continue
            edge_ids = group["edge_ids"]
            directions = group["directions"]
            color = _route_edge_color_for_directions(directions, group.get("road_classes"))
            width = max(2, int(2.2 * scale))
            if edge_ids & self.path_edge_ids:
                color = QColor("#2563eb")
                width = max(4, int(4.2 * scale))
            if self.selected_type == "edge" and self.selected_id in edge_ids:
                color = QColor("#f59e0b")
                width = max(4, int(4.0 * scale))
            issue_level = _highest_edge_issue_level(edge_ids, self.issue_target_levels)
            if issue_level == "warning":
                color = QColor("#f59e0b")
                width = max(4, int(4.0 * scale))
            if issue_level == "error":
                color = QColor("#dc2626")
                width = max(5, int(4.8 * scale))
            if directions == {-1, 1}:
                self._draw_visual_polyline(painter, points, color, width)
                if self.show_direction_arrows:
                    self._draw_direction_arrow(painter, points, color, reverse=False, scale=scale)
                    self._draw_direction_arrow(painter, list(reversed(points)), color, reverse=True, scale=scale)
            else:
                directed_points = points if 1 in directions else list(reversed(points))
                self._draw_directional_polyline(painter, directed_points, color, width, scale, reverse=False)

    def _draw_directional_polyline(
        self,
        painter: QPainter,
        points: list[QPointF],
        color: QColor,
        width: int,
        scale: float,
        reverse: bool = False,
    ) -> None:
        if not self.show_direction_arrows:
            self._draw_visual_polyline(painter, points, color, width)
            return
        arrow = _arrow_geometry(points, scale)
        if arrow is None:
            self._draw_visual_polyline(painter, points, color, width)
            return
        _tip, _left, _right, base_distance = arrow
        line_points = _trim_polyline_to_distance(points, base_distance)
        self._draw_visual_polyline(painter, line_points, color, width)
        self._draw_direction_arrow(painter, points, color, reverse=reverse, scale=scale)

    def _draw_visual_polyline(self, painter: QPainter, points: list[QPointF], color: QColor, width: int) -> None:
        if len(points) < 2:
            return
        painter.setPen(QPen(QColor(255, 255, 255, 215), width + 3, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        for left, right in zip(points, points[1:]):
            painter.drawLine(left, right)
        painter.setPen(QPen(color, width, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        for left, right in zip(points, points[1:]):
            painter.drawLine(left, right)

    def _draw_direction_arrow(
        self,
        painter: QPainter,
        points: list[QPointF],
        color: QColor,
        reverse: bool = False,
        scale: float | None = None,
    ) -> None:
        if len(points) < 2:
            return
        scale = scale or self._marker_scale()
        arrow = _arrow_geometry(points, scale)
        if arrow is None:
            return
        tip, left, right, _base_distance = arrow
        arrow_color = QColor(color).darker(106)

        painter.save()
        painter.setBrush(arrow_color)
        painter.setPen(QPen(QColor(255, 255, 255, 235), max(2, int(2.4 * scale)), Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        painter.drawPolygon(QPolygonF([tip, left, right]))
        painter.setPen(QPen(arrow_color, max(1, int(1.2 * scale)), Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        painter.drawPolygon(QPolygonF([tip, left, right]))
        painter.restore()
