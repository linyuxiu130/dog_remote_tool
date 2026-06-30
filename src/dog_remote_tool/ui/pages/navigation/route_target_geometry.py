from __future__ import annotations

import math

from dog_remote_tool.modules.navigation import route_network


def route_path_yaw(graph: route_network.RouteGraph, start_id: int, goal_id: int) -> float | None:
    if start_id == goal_id:
        return route_node_outgoing_yaw(graph, goal_id)
    path = route_network.shortest_path(graph, start_id, goal_id)
    if not path.reachable or len(path.node_ids) < 2:
        return None
    return route_segment_yaw(graph, path.node_ids[-2], path.node_ids[-1], path.edge_ids[-1])


def route_path_start_yaw(graph: route_network.RouteGraph, start_id: int, goal_id: int) -> float | None:
    if start_id == goal_id:
        return route_node_outgoing_yaw(graph, goal_id)
    path = route_network.shortest_path(graph, start_id, goal_id)
    if not path.reachable or len(path.node_ids) < 2:
        return None
    return route_segment_yaw(
        graph,
        path.node_ids[0],
        path.node_ids[1],
        path.edge_ids[0],
        final_segment=False,
    )


def route_node_outgoing_yaw(graph: route_network.RouteGraph, node_id: int) -> float | None:
    candidates: list[tuple[float, int, int]] = []
    for edge in graph.edges.values():
        if edge.startid == node_id and edge.endid in graph.nodes:
            candidates.append((edge.length(), edge.id, edge.endid))
        elif edge.is_reverse_allowed() and edge.endid == node_id and edge.startid in graph.nodes:
            candidates.append((edge.length(), edge.id, edge.startid))
    if not candidates:
        return None
    _length, edge_id, next_id = min(candidates)
    return route_segment_yaw(graph, node_id, next_id, edge_id, final_segment=False)


def route_segment_yaw(
    graph: route_network.RouteGraph,
    from_id: int,
    to_id: int,
    edge_id: int | None = None,
    *,
    final_segment: bool = True,
) -> float | None:
    edge = graph.edges.get(edge_id) if edge_id is not None else None
    points = list(edge.coordinates) if edge is not None else []
    if edge is not None:
        if edge.startid == from_id and edge.endid == to_id:
            pass
        elif edge.is_reverse_allowed() and edge.endid == from_id and edge.startid == to_id:
            points = list(reversed(points))
        else:
            points = []
    if len(points) >= 2:
        start, end = (points[-2], points[-1]) if final_segment else (points[0], points[1])
        dx = float(end[0]) - float(start[0])
        dy = float(end[1]) - float(start[1])
        if math.hypot(dx, dy) > 1e-6:
            return math.atan2(dy, dx)
    from_node = graph.nodes.get(from_id)
    to_node = graph.nodes.get(to_id)
    if from_node is None or to_node is None:
        return None
    dx = to_node.x - from_node.x
    dy = to_node.y - from_node.y
    if math.hypot(dx, dy) <= 1e-6:
        return None
    return math.atan2(dy, dx)
