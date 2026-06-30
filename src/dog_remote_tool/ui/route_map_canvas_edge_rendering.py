from __future__ import annotations

import math

from PyQt5.QtCore import QPointF
from PyQt5.QtGui import QColor

from dog_remote_tool.modules.navigation import route_network

ROUTE_EDGE_BOTH_COLOR = "#0f766e"
ROUTE_EDGE_FORWARD_COLOR = "#2563eb"
ROUTE_EDGE_SAME_KNEE_COLOR = "#9333ea"


def visual_edge_groups(edges) -> list[dict]:
    groups: dict[tuple[tuple[int, int], ...], dict] = {}
    for edge in edges:
        if len(edge.coordinates) < 2:
            continue
        forward_key = edge_geometry_key(edge.coordinates)
        reverse_key = tuple(reversed(forward_key))
        if forward_key <= reverse_key:
            key = forward_key
            coordinates = list(edge.coordinates)
            orientation = 1
        else:
            key = reverse_key
            coordinates = list(reversed(edge.coordinates))
            orientation = -1
        group = groups.setdefault(key, {"coordinates": coordinates, "edge_ids": set(), "directions": set(), "road_classes": set()})
        group["edge_ids"].add(edge.id)
        group["road_classes"].add(route_network.edge_road_class(edge))
        if edge.is_reverse_allowed():
            group["directions"].update({-1, 1})
        else:
            group["directions"].add(orientation)
    return list(groups.values())


def route_edge_color_for_directions(directions: set[int], road_classes: set[int] | None = None) -> QColor:
    if road_classes and 3 in road_classes:
        return QColor(ROUTE_EDGE_SAME_KNEE_COLOR)
    return QColor(ROUTE_EDGE_BOTH_COLOR if directions == {-1, 1} else ROUTE_EDGE_FORWARD_COLOR)


def edge_geometry_key(points: list[route_network.RouteCoordinate]) -> tuple[tuple[int, int], ...]:
    return tuple((round(point[0] * 1000), round(point[1] * 1000)) for point in points)


def highest_edge_issue_level(edge_ids: set[int], levels: dict[tuple[str, int], str]) -> str | None:
    result = None
    for edge_id in edge_ids:
        level = levels.get(("edge", edge_id))
        if level == "error":
            return "error"
        if level == "warning":
            result = "warning"
    return result


def arrow_geometry(points: list[QPointF], scale: float) -> tuple[QPointF, QPointF, QPointF, float] | None:
    total = sum(math.hypot(b.x() - a.x(), b.y() - a.y()) for a, b in zip(points, points[1:]))
    if total < 10:
        return None
    head = 7.0 * scale
    half_width = 3.6 * scale
    node_gap = 6.5 * scale
    tip_distance = max(total * 0.45, total - min(node_gap, total * 0.28))
    segment = point_at_polyline_distance(points, tip_distance)
    if segment is None:
        return None
    a, b, length, t = segment
    ux = (b.x() - a.x()) / length
    uy = (b.y() - a.y()) / length
    px = -uy
    py = ux
    tip = QPointF(a.x() + (b.x() - a.x()) * t, a.y() + (b.y() - a.y()) * t)
    base = QPointF(tip.x() - ux * head, tip.y() - uy * head)
    left = QPointF(base.x() + px * half_width, base.y() + py * half_width)
    right = QPointF(base.x() - px * half_width, base.y() - py * half_width)
    return tip, left, right, max(0.0, tip_distance - head)


def point_at_polyline_distance(points: list[QPointF], distance: float) -> tuple[QPointF, QPointF, float, float] | None:
    travelled = 0.0
    for a, b in zip(points, points[1:]):
        length = math.hypot(b.x() - a.x(), b.y() - a.y())
        if length < 1e-6:
            continue
        if travelled + length >= distance:
            return a, b, length, max(0.0, min(1.0, (distance - travelled) / length))
        travelled += length
    return None


def trim_polyline_to_distance(points: list[QPointF], distance: float) -> list[QPointF]:
    if not points:
        return []
    if distance <= 0:
        return [points[0]]
    result = [points[0]]
    travelled = 0.0
    for a, b in zip(points, points[1:]):
        length = math.hypot(b.x() - a.x(), b.y() - a.y())
        if length < 1e-6:
            continue
        if travelled + length >= distance:
            t = max(0.0, min(1.0, (distance - travelled) / length))
            result.append(QPointF(a.x() + (b.x() - a.x()) * t, a.y() + (b.y() - a.y()) * t))
            return result
        result.append(b)
        travelled += length
    return result
