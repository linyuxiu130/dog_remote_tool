from __future__ import annotations

import math

from PyQt5.QtCore import QPointF

from dog_remote_tool.modules.navigation import route_network


def point_to_polyline_distance(x: float, y: float, points: list[route_network.RouteCoordinate]) -> float:
    if len(points) < 2:
        return math.inf
    best = math.inf
    for a, b in zip(points, points[1:]):
        best = min(best, point_to_segment_distance(x, y, a, b))
    return best


def offset_polyline(points: list[QPointF], offset: float) -> list[QPointF]:
    if len(points) < 2 or abs(offset) < 1e-6:
        return list(points)
    result: list[QPointF] = []
    for index, point in enumerate(points):
        if index == 0:
            previous = point
            next_point = points[index + 1]
        elif index == len(points) - 1:
            previous = points[index - 1]
            next_point = point
        else:
            previous = points[index - 1]
            next_point = points[index + 1]
        dx = next_point.x() - previous.x()
        dy = next_point.y() - previous.y()
        length = math.hypot(dx, dy)
        if length <= 1e-9:
            result.append(QPointF(point))
            continue
        nx = -dy / length
        ny = dx / length
        result.append(QPointF(point.x() + nx * offset, point.y() + ny * offset))
    return result


def point_to_segment_distance(
    x: float, y: float, a: route_network.RouteCoordinate, b: route_network.RouteCoordinate
) -> float:
    ax, ay = a[0], a[1]
    bx, by = b[0], b[1]
    dx = bx - ax
    dy = by - ay
    length_sq = dx * dx + dy * dy
    if length_sq <= 1e-12:
        return math.hypot(x - ax, y - ay)
    t = max(0.0, min(1.0, ((x - ax) * dx + (y - ay) * dy) / length_sq))
    return math.hypot(x - (ax + t * dx), y - (ay + t * dy))
