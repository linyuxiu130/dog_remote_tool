from __future__ import annotations

import math
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from dog_remote_tool.modules.navigation.route_network import Bounds, MapMetadata, RouteGraph


RouteCoordinate = tuple[float, float] | tuple[float, float, float]


def polyline_length(points: list[RouteCoordinate]) -> float:
    return sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(points, points[1:]))


def map_bounds(metadata: "MapMetadata", image_size: tuple[int, int]) -> "Bounds":
    from dog_remote_tool.modules.navigation.route_network import Bounds

    width, height = image_size
    min_x = metadata.origin[0]
    min_y = metadata.origin[1]
    return Bounds(min_x, min_y, min_x + width * metadata.resolution, min_y + height * metadata.resolution)


def graph_bounds(graph: "RouteGraph") -> "Bounds | None":
    from dog_remote_tool.modules.navigation.route_network import Bounds

    points: list[RouteCoordinate] = []
    for node in graph.nodes.values():
        points.append((node.x, node.y))
    for edge in graph.edges.values():
        points.extend(edge.coordinates)
    if not points:
        return None
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    return Bounds(min(xs), min(ys), max(xs), max(ys))


def nearest_node(graph: "RouteGraph", x: float, y: float, max_distance: float = 0.25) -> int | None:
    best_id: int | None = None
    best_dist = max_distance
    for node in graph.nodes.values():
        dist = math.hypot(node.x - x, node.y - y)
        if dist <= best_dist:
            best_id = node.id
            best_dist = dist
    return best_id


def polylines_cross(left: list[RouteCoordinate], right: list[RouteCoordinate]) -> bool:
    for a1, a2 in zip(left, left[1:]):
        for b1, b2 in zip(right, right[1:]):
            if segments_cross(a1, a2, b1, b2):
                return True
    return False


def segments_cross(a: RouteCoordinate, b: RouteCoordinate, c: RouteCoordinate, d: RouteCoordinate) -> bool:
    def orient(p: RouteCoordinate, q: RouteCoordinate, r: RouteCoordinate) -> float:
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])

    o1 = orient(a, b, c)
    o2 = orient(a, b, d)
    o3 = orient(c, d, a)
    o4 = orient(c, d, b)
    return o1 * o2 < 0 and o3 * o4 < 0


def edge_intersections(graph: "RouteGraph") -> list[tuple[int, int, float, int, int, float, float, float]]:
    intersections: list[tuple[int, int, float, int, int, float, float, float]] = []
    edges = list(graph.edges.values())
    for index, left in enumerate(edges):
        for right in edges[index + 1 :]:
            if {left.startid, left.endid} & {right.startid, right.endid}:
                continue
            for left_segment, (a, b) in enumerate(zip(left.coordinates, left.coordinates[1:])):
                for right_segment, (c, d) in enumerate(zip(right.coordinates, right.coordinates[1:])):
                    hit = segment_intersection(a, b, c, d)
                    if hit is None:
                        continue
                    left_t, right_t, x, y = hit
                    intersections.append((left.id, left_segment, left_t, right.id, right_segment, right_t, x, y))
    return intersections


def segment_intersection(
    a: RouteCoordinate,
    b: RouteCoordinate,
    c: RouteCoordinate,
    d: RouteCoordinate,
) -> tuple[float, float, float, float] | None:
    ax, ay = a[0], a[1]
    bx, by = b[0], b[1]
    cx, cy = c[0], c[1]
    dx, dy = d[0], d[1]
    rx = bx - ax
    ry = by - ay
    sx = dx - cx
    sy = dy - cy
    denominator = rx * sy - ry * sx
    if abs(denominator) <= 1e-12:
        return None
    qpx = cx - ax
    qpy = cy - ay
    left_t = (qpx * sy - qpy * sx) / denominator
    right_t = (qpx * ry - qpy * rx) / denominator
    if not (1e-9 < left_t < 1.0 - 1e-9 and 1e-9 < right_t < 1.0 - 1e-9):
        return None
    return left_t, right_t, ax + left_t * rx, ay + left_t * ry
