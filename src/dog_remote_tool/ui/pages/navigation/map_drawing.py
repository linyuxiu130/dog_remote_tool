from __future__ import annotations

import math

from PyQt5.QtCore import QPointF, QRectF, Qt
from PyQt5.QtGui import QColor, QFont, QPainter, QPen, QPolygonF

from dog_remote_tool.modules.navigation import route_network
from dog_remote_tool.ui.route_map_canvas_edge_rendering import (
    arrow_geometry as _arrow_geometry,
    route_edge_color_for_directions as _route_edge_color_for_directions,
    trim_polyline_to_distance as _trim_polyline_to_distance,
    visual_edge_groups as _visual_edge_groups,
)


class NavigationMapDrawingMixin:
    def _draw_target_marker(self, painter: QPainter, point: QPointF, yaw: float, index: int, scale: float) -> None:
        label = str(index)
        font = QFont(painter.font())
        font.setBold(True)
        font.setPixelSize(max(9, int(9.5 * scale)))
        painter.save()
        painter.setFont(font)
        metrics = painter.fontMetrics()
        body_height = max(15.2 * scale, metrics.height() + 4.0 * scale)
        body_width = max(body_height, metrics.horizontalAdvance(label) + 8.0 * scale)
        radius = body_height / 2.0
        tail_length = 13.0 * scale
        tail_width = 5.2 * scale
        dx = math.cos(yaw)
        dy = -math.sin(yaw)
        px = -dy
        py = dx
        body_extent = max(body_width, body_height) / 2.0
        tip = QPointF(point.x() + dx * (body_extent + tail_length), point.y() + dy * (body_extent + tail_length))
        left = QPointF(point.x() + dx * body_extent + px * tail_width, point.y() + dy * body_extent + py * tail_width)
        right = QPointF(point.x() + dx * body_extent - px * tail_width, point.y() + dy * body_extent - py * tail_width)

        painter.setPen(QPen(QColor(255, 255, 255, 230), max(2, int(2 * scale))))
        painter.setBrush(QColor("#65a30d"))
        painter.drawPolygon(QPolygonF([left, tip, right]))

        body_rect = QRectF(point.x() - body_width / 2.0, point.y() - body_height / 2.0, body_width, body_height)
        painter.setPen(QPen(QColor(255, 255, 255, 235), max(2, int(2 * scale))))
        painter.setBrush(QColor("#d7f500"))
        if body_width <= body_height + 1:
            painter.drawEllipse(point, radius, radius)
        else:
            painter.drawRoundedRect(body_rect, radius, radius)
        painter.setPen(QColor("#365314"))
        painter.drawText(body_rect.adjusted(-2 * scale, -2 * scale, 2 * scale, 2 * scale), Qt.AlignCenter, label)
        painter.restore()

    def _draw_charging_docks(self, painter: QPainter) -> None:
        if not self.charging_docks:
            return
        scale = self._marker_scale()
        width = 18.0 * scale
        height = 13.0 * scale
        corner = 2.5 * scale
        for _tag_id, x, y, _yaw in self.charging_docks:
            point = self._world_to_widget(x, y)
            if point is None:
                continue

            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(245, 158, 11, 34))
            painter.drawRoundedRect(
                QRectF(point.x() - width * 0.65, point.y() - height * 0.65, width * 1.3, height * 1.3),
                corner * 1.4,
                corner * 1.4,
            )
            painter.setPen(QPen(QColor("#92400e"), max(2, int(2 * scale))))
            painter.setBrush(QColor("#fffbeb"))
            painter.drawRoundedRect(QRectF(point.x() - width / 2, point.y() - height / 2, width, height), corner, corner)

    def _draw_route_graph(self, painter: QPainter) -> None:
        graph = self.route_graph
        if graph is None or (not graph.nodes and not graph.edges):
            return
        target_ids = set(self.route_target_node_ids)
        scale = self._marker_scale()
        painter.save()
        for group in _visual_edge_groups(graph.edges.values()):
            points = []
            for coordinate in group["coordinates"]:
                if len(coordinate) >= 2:
                    point = self._world_to_widget(float(coordinate[0]), float(coordinate[1]))
                    if point is not None:
                        points.append(point)
            if len(points) < 2:
                continue
            directions = group["directions"]
            color = _route_edge_color_for_directions(directions, group.get("road_classes"))
            width = max(2, int(2.2 * scale))
            if directions == {-1, 1}:
                self._draw_route_visual_polyline(painter, points, color, width)
                self._draw_route_direction_arrow(painter, points, color, scale)
                self._draw_route_direction_arrow(painter, list(reversed(points)), color, scale)
            else:
                directed_points = points if 1 in directions else list(reversed(points))
                self._draw_route_directional_polyline(painter, directed_points, color, width, scale)

        self._draw_route_target_path(painter)

        font = QFont(painter.font())
        font.setBold(True)
        font.setPixelSize(max(8, int(8.5 * scale)))
        painter.setFont(font)
        for node in graph.nodes.values():
            point = self._world_to_widget(node.x, node.y)
            if point is None:
                continue
            selected = node.id in target_ids
            radius = (7.5 if selected else 5.5) * scale
            painter.setPen(QPen(QColor("#ffffff"), max(2, int(2 * scale))))
            painter.setBrush(QColor("#f59e0b") if selected else QColor("#14b8a6"))
            painter.drawEllipse(point, radius, radius)
            if selected:
                label = "/".join(str(index + 1) for index, target_id in enumerate(self.route_target_node_ids) if target_id == node.id)
                text_rect = QRectF(point.x() - radius, point.y() - radius, radius * 2, radius * 2)
                painter.setPen(QColor("#111827"))
                painter.drawText(text_rect, Qt.AlignCenter, label)
        painter.restore()

    def _draw_route_directional_polyline(
        self,
        painter: QPainter,
        points: list[QPointF],
        color: QColor,
        width: int,
        scale: float,
    ) -> None:
        arrow = _arrow_geometry(points, scale)
        if arrow is None:
            self._draw_route_visual_polyline(painter, points, color, width)
            return
        _tip, _left, _right, base_distance = arrow
        self._draw_route_visual_polyline(painter, _trim_polyline_to_distance(points, base_distance), color, width)
        self._draw_route_direction_arrow(painter, points, color, scale)

    def _draw_route_visual_polyline(
        self,
        painter: QPainter,
        points: list[QPointF],
        color: QColor,
        width: int,
    ) -> None:
        painter.setPen(QPen(QColor(255, 255, 255, 215), width + 3, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        for start, end in zip(points, points[1:]):
            painter.drawLine(start, end)
        painter.setPen(QPen(color, width, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        for start, end in zip(points, points[1:]):
            painter.drawLine(start, end)

    def _draw_route_direction_arrow(
        self,
        painter: QPainter,
        points: list[QPointF],
        color: QColor,
        scale: float,
    ) -> None:
        arrow = _arrow_geometry(points, scale)
        if arrow is None:
            return
        tip, left, right, _base_distance = arrow
        arrow_color = QColor(color).darker(106)
        painter.setBrush(arrow_color)
        painter.setPen(QPen(QColor(255, 255, 255, 235), max(2, int(2.4 * scale)), Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        painter.drawPolygon(QPolygonF([tip, left, right]))
        painter.setPen(QPen(arrow_color, max(1, int(1.2 * scale)), Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        painter.drawPolygon(QPolygonF([tip, left, right]))

    def _route_target_path_coordinates(self) -> list[list[tuple[float, float]]]:
        graph = self.route_graph
        target_ids = list(getattr(self, "route_target_node_ids", []))
        if graph is None or not target_ids:
            return []
        robot_pose = getattr(self, "robot_pose", None)
        robot_point: tuple[float, float] | None = None
        start_id: int | None = None
        if robot_pose is not None:
            robot_x, robot_y = float(robot_pose[0]), float(robot_pose[1])
            start_id = route_network.nearest_node(graph, robot_x, robot_y, max_distance=1.50)
            if start_id is not None:
                robot_point = (robot_x, robot_y)
        route_ids = list(target_ids)
        if start_id is not None:
            if not route_ids or route_ids[0] != start_id:
                route_ids.insert(0, start_id)
            elif len(route_ids) == 1:
                node = graph.nodes.get(start_id)
                if node is None:
                    return []
                node_point = (float(node.x), float(node.y))
                if robot_point is not None and robot_point != node_point:
                    return [[robot_point, node_point]]
                return []
        if len(route_ids) < 2:
            return []
        paths: list[list[tuple[float, float]]] = []
        for segment_index, (start_id, goal_id) in enumerate(zip(route_ids, route_ids[1:])):
            if start_id == goal_id:
                continue
            path = route_network.shortest_path(graph, start_id, goal_id)
            if not path.reachable or len(path.node_ids) < 2:
                continue
            points: list[tuple[float, float]] = []
            for from_id, to_id, edge_id in zip(path.node_ids, path.node_ids[1:], path.edge_ids):
                edge = graph.edges.get(edge_id)
                if edge is None:
                    continue
                coordinates = list(edge.coordinates)
                if edge.startid == to_id and edge.endid == from_id:
                    coordinates = list(reversed(coordinates))
                elif edge.startid != from_id or edge.endid != to_id:
                    from_node = graph.nodes.get(from_id)
                    to_node = graph.nodes.get(to_id)
                    coordinates = []
                    if from_node is not None and to_node is not None:
                        coordinates = [(from_node.x, from_node.y), (to_node.x, to_node.y)]
                for coordinate in coordinates:
                    if len(coordinate) < 2:
                        continue
                    point = (float(coordinate[0]), float(coordinate[1]))
                    if not points or point != points[-1]:
                        points.append(point)
            if segment_index == 0 and robot_point is not None and points and robot_point != points[0]:
                points.insert(0, robot_point)
            if len(points) >= 2:
                paths.append(points)
        return paths

    def _draw_route_target_path(self, painter: QPainter) -> None:
        paths = self._route_target_path_coordinates()
        if not paths:
            return
        scale = self._marker_scale()
        outline_width = max(7, int(7.0 * scale))
        main_width = max(4, int(4.4 * scale))
        outline = QColor(255, 255, 255, 180)
        color = QColor(225, 29, 72, 150)
        painter.save()
        for world_points in paths:
            points = [self._world_to_widget(x, y) for x, y in world_points]
            points = [point for point in points if point is not None]
            if len(points) < 2:
                continue
            painter.setPen(QPen(outline, outline_width, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            for start, end in zip(points, points[1:]):
                painter.drawLine(start, end)
            painter.setPen(QPen(color, main_width, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            for start, end in zip(points, points[1:]):
                painter.drawLine(start, end)
            arrow = _arrow_geometry(points, scale)
            if arrow is None:
                continue
            tip, left, right, _base_distance = arrow
            arrow_color = QColor(color).darker(105)
            arrow_color.setAlpha(175)
            painter.setBrush(arrow_color)
            painter.setPen(QPen(outline, max(2, int(2.4 * scale)), Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            painter.drawPolygon(QPolygonF([tip, left, right]))
            painter.setPen(QPen(arrow_color, max(1, int(1.2 * scale)), Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            painter.drawPolygon(QPolygonF([tip, left, right]))
        painter.restore()

    def _draw_polyline(self, painter: QPainter, points: list[tuple[float, float, float]], color: QColor, width: int) -> None:
        widget_points = [self._world_to_widget(x, y) for x, y, _yaw in points]
        widget_points = [point for point in widget_points if point is not None]
        if len(widget_points) < 2:
            return
        painter.setPen(QPen(color, width))
        for start, end in zip(widget_points, widget_points[1:]):
            painter.drawLine(start, end)

    def _draw_robot_pose(self, painter: QPainter, point: QPointF, yaw: float) -> None:
        scale = self._marker_scale()
        outer_radius = 10.5 * scale
        inner_radius = 6.5 * scale
        length = 30.0 * scale
        head = 6.5 * scale
        dx = math.cos(yaw)
        dy = -math.sin(yaw)
        end = QPointF(point.x() + dx * length, point.y() + dy * length)
        left = QPointF(
            end.x() - dx * head + dy * head * 0.72,
            end.y() - dy * head - dx * head * 0.72,
        )
        right = QPointF(
            end.x() - dx * head - dy * head * 0.72,
            end.y() - dy * head + dx * head * 0.72,
        )
        arrow_head = QPolygonF([end, left, right])

        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(220, 38, 38, 24))
        painter.drawEllipse(point, outer_radius * 1.45, outer_radius * 1.45)

        painter.setPen(QPen(QColor(255, 255, 255, 235), max(4, int(5 * scale)), Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        painter.drawLine(point, end)
        painter.setPen(QPen(QColor("#dc2626"), max(2, int(2.4 * scale)), Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        painter.drawLine(point, end)

        painter.setPen(QPen(QColor(255, 255, 255, 235), max(2, int(2.5 * scale)), Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        painter.setBrush(QColor("#dc2626"))
        painter.drawPolygon(arrow_head)

        painter.setPen(QPen(QColor(255, 255, 255, 245), max(2, int(2.5 * scale))))
        painter.setBrush(QColor("#dc2626"))
        painter.drawEllipse(point, outer_radius, outer_radius)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#ef4444"))
        painter.drawEllipse(point, inner_radius, inner_radius)
