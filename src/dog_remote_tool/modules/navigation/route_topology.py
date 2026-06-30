from __future__ import annotations

import heapq
import math
from typing import Any

from dog_remote_tool.modules.navigation.route_geometry import edge_intersections, polyline_length


def split_crossing_edges(graph: Any, tolerance: float = 0.03) -> tuple[int, int]:
    from dog_remote_tool.modules.navigation.route_network import RouteNode

    intersections = edge_intersections(graph)
    if not intersections:
        return 0, 0

    node_by_key: dict[tuple[int, int], int] = {}
    added_nodes = 0

    def point_key(x: float, y: float) -> tuple[int, int]:
        return (round(x / tolerance), round(y / tolerance))

    def node_for_point(x: float, y: float) -> int:
        nonlocal added_nodes
        key = point_key(x, y)
        if key in node_by_key:
            return node_by_key[key]
        for node in graph.nodes.values():
            if math.hypot(node.x - x, node.y - y) <= tolerance:
                node_by_key[key] = node.id
                return node.id
        node_id = graph.next_node_id()
        while node_id in graph.nodes:
            node_id += 1
        graph.nodes[node_id] = RouteNode(node_id, x, y, {"id": node_id, "source": "auto_crossing"})
        node_by_key[key] = node_id
        added_nodes += 1
        return node_id

    splits: dict[int, list[tuple[int, float, int]]] = {}
    for left_id, left_segment, left_t, right_id, right_segment, right_t, x, y in intersections:
        node_id = node_for_point(x, y)
        splits.setdefault(left_id, []).append((left_segment, left_t, node_id))
        splits.setdefault(right_id, []).append((right_segment, right_t, node_id))

    split_edge_count = _split_edges_at_nodes(graph, splits)
    return added_nodes, split_edge_count


def attach_isolated_nodes_to_edges(
    graph: Any,
    tolerance: float | None = None,
    node_ids: set[int] | None = None,
) -> tuple[int, int]:
    from dog_remote_tool.modules.navigation.route_network import (
        DEFAULT_ROUTE_PASSABLE_WIDTH,
        ROUTE_DIRECTION_BOTH,
        RouteEdge,
        node_coordinate_tuple,
    )

    degrees: dict[int, int] = {node_id: 0 for node_id in graph.nodes}
    for edge in graph.edges.values():
        if edge.startid in degrees:
            degrees[edge.startid] += 1
        if edge.endid in degrees:
            degrees[edge.endid] += 1

    attached_nodes = 0
    created_edges = 0
    next_edge_id = max([0, *graph.edges.keys()]) + 1
    target_node_ids = set(node_ids) if node_ids is not None else None
    for node in sorted(graph.nodes.values(), key=lambda item: item.id):
        if target_node_ids is not None and node.id not in target_node_ids:
            continue
        if degrees.get(node.id, 0) != 0:
            continue
        best: tuple[float, Any] | None = None
        for other in graph.nodes.values():
            if other.id == node.id:
                continue
            distance = math.hypot(node.x - other.x, node.y - other.y)
            if tolerance is not None and distance > tolerance:
                continue
            if best is None or distance < best[0] or (abs(distance - best[0]) <= 1e-9 and other.id < best[1].id):
                best = (distance, other)
        if best is None:
            continue
        _distance, target = best
        coords = [node_coordinate_tuple(node), node_coordinate_tuple(target)]
        cost = polyline_length(coords)
        graph.edges[next_edge_id] = RouteEdge(
            next_edge_id,
            node.id,
            target.id,
            coords,
            direction=ROUTE_DIRECTION_BOTH,
            cost=cost,
            properties={
                "id": next_edge_id,
                "startid": node.id,
                "endid": target.id,
                "direction": ROUTE_DIRECTION_BOTH,
                "cost": cost,
                "passable_width": DEFAULT_ROUTE_PASSABLE_WIDTH,
                "source": "auto_attach_isolated",
            },
        )
        degrees[node.id] = degrees.get(node.id, 0) + 1
        degrees[target.id] = degrees.get(target.id, 0) + 1
        next_edge_id += 1
        attached_nodes += 1
        created_edges += 1
    if created_edges:
        graph.dirty = True
    return attached_nodes, created_edges


def _split_edges_at_nodes(graph: Any, splits: dict[int, list[tuple[int, float, int]]]) -> int:
    from dog_remote_tool.modules.navigation.route_network import RouteEdge

    original_edges = {edge_id: graph.edges[edge_id] for edge_id in splits if edge_id in graph.edges}
    if not original_edges:
        return 0
    next_edge_id = max([0, *graph.edges.keys(), *original_edges.keys()]) + 1
    split_edge_count = 0

    for edge_id in original_edges:
        graph.edges.pop(edge_id, None)

    for edge_id, edge in sorted(original_edges.items()):
        positions = [(0.0, edge.startid)]
        last_position = max(0.0, float(len(edge.coordinates) - 1))
        for segment, t, node_id in sorted(set(splits.get(edge_id, [])), key=lambda item: (item[0], item[1], item[2])):
            if node_id not in graph.nodes:
                continue
            position = float(segment) + max(0.0, min(1.0, float(t)))
            if 1e-9 < position < last_position - 1e-9:
                positions.append((position, node_id))
        positions.append((last_position, edge.endid))
        positions = _dedupe_split_positions(positions)
        if len(positions) < 2:
            continue
        for segment_index, ((start_position, start_id), (end_position, end_id)) in enumerate(zip(positions, positions[1:])):
            if start_id not in graph.nodes or end_id not in graph.nodes or start_id == end_id:
                continue
            new_edge_id = edge.id if segment_index == 0 else next_edge_id
            if segment_index > 0:
                next_edge_id += 1
            start = graph.nodes[start_id]
            end = graph.nodes[end_id]
            coords = _subline_coordinates(edge.coordinates, start_position, end_position, start, end)
            cost = polyline_length(coords)
            properties = dict(edge.properties)
            properties.update({"id": new_edge_id, "startid": start_id, "endid": end_id, "direction": edge.direction, "cost": cost})
            graph.edges[new_edge_id] = RouteEdge(
                new_edge_id,
                start_id,
                end_id,
                coords,
                edge.direction,
                cost,
                properties,
            )
            split_edge_count += 1
    if split_edge_count:
        graph.dirty = True
    return split_edge_count


def _dedupe_split_positions(positions: list[tuple[float, int]]) -> list[tuple[float, int]]:
    ordered: list[tuple[float, int]] = []
    for position, node_id in sorted(positions, key=lambda item: (item[0], item[1])):
        if ordered and abs(position - ordered[-1][0]) <= 1e-9:
            if node_id == ordered[-1][1]:
                continue
        if ordered and node_id == ordered[-1][1]:
            continue
        ordered.append((position, node_id))
    return ordered


def _subline_coordinates(
    coordinates: list[Any],
    start_position: float,
    end_position: float,
    start: Any,
    end: Any,
) -> list[Any]:
    from dog_remote_tool.modules.navigation.route_network import node_coordinate_tuple

    values: list[Any] = [node_coordinate_tuple(start)]
    for index, point in enumerate(coordinates[1:-1], start=1):
        if start_position < float(index) < end_position:
            values.append(point)
    values.append(node_coordinate_tuple(end))
    return [point for index, point in enumerate(values) if index == 0 or point != values[index - 1]]


def shortest_path(graph: Any, start_id: int, goal_id: int) -> Any:
    from dog_remote_tool.modules.navigation.route_network import PathResult

    if start_id not in graph.nodes or goal_id not in graph.nodes:
        return PathResult([], [], math.inf)
    adjacency: dict[int, list[tuple[int, float, int]]] = {}
    for edge in graph.edges.values():
        cost = edge.cost or edge.length()
        adjacency.setdefault(edge.startid, []).append((edge.endid, cost, edge.id))
        if edge.is_reverse_allowed():
            adjacency.setdefault(edge.endid, []).append((edge.startid, cost, edge.id))
    queue: list[tuple[float, int]] = [(0.0, start_id)]
    best: dict[int, float] = {start_id: 0.0}
    prev: dict[int, tuple[int, int]] = {}
    while queue:
        cost, node_id = heapq.heappop(queue)
        if node_id == goal_id:
            break
        if cost > best.get(node_id, math.inf):
            continue
        for next_id, edge_cost, edge_id in adjacency.get(node_id, []):
            candidate = cost + edge_cost
            if candidate < best.get(next_id, math.inf):
                best[next_id] = candidate
                prev[next_id] = (node_id, edge_id)
                heapq.heappush(queue, (candidate, next_id))
    if goal_id not in best:
        return PathResult([], [], math.inf)
    nodes = [goal_id]
    edges: list[int] = []
    cursor = goal_id
    while cursor != start_id:
        previous, edge_id = prev[cursor]
        edges.append(edge_id)
        nodes.append(previous)
        cursor = previous
    nodes.reverse()
    edges.reverse()
    return PathResult(nodes, edges, best[goal_id])
