from __future__ import annotations

import math
from typing import Any

from dog_remote_tool.modules.navigation.route_geometry import map_bounds, polylines_cross


def validate_graph(graph: Any, map_metadata: Any | None = None, image_size: tuple[int, int] | None = None) -> list[Any]:
    from dog_remote_tool.modules.navigation.route_network import ValidationIssue

    issues: list[Any] = [
        issue for issue in graph.import_issues if isinstance(issue, ValidationIssue)
    ]
    map_area = map_bounds(map_metadata, image_size) if map_metadata and image_size else None
    if not graph.nodes:
        issues.append(ValidationIssue("error", "no_nodes", "路网没有节点"))
    if not graph.edges:
        issues.append(ValidationIssue("error", "no_edges", "路网没有有效边"))
    for edge in graph.edges.values():
        if edge.startid not in graph.nodes:
            issues.append(ValidationIssue("error", "missing_start", f"边 {edge.id} 引用不存在的起点 {edge.startid}", "edge", edge.id))
        if edge.endid not in graph.nodes:
            issues.append(ValidationIssue("error", "missing_end", f"边 {edge.id} 引用不存在的终点 {edge.endid}", "edge", edge.id))
        if edge.startid == edge.endid:
            issues.append(ValidationIssue("error", "self_loop", f"边 {edge.id} 起终点相同", "edge", edge.id))
        if len(edge.coordinates) < 2:
            issues.append(ValidationIssue("error", "short_geometry", f"边 {edge.id} 缺少有效线段", "edge", edge.id))
        if edge.length() < 0.05:
            issues.append(ValidationIssue("warning", "tiny_edge", f"边 {edge.id} 长度过短", "edge", edge.id))
        _check_edge_endpoint(graph, edge, True, issues)
        _check_edge_endpoint(graph, edge, False, issues)
        if str(edge.direction).strip().lower() not in {"0", "1", "2", "both", "forward", "bidirectional", "双向", "单向"}:
            issues.append(ValidationIssue("warning", "unknown_direction", f"边 {edge.id} direction={edge.direction} 未知，将原样保留", "edge", edge.id))
        if map_area:
            outside_count = sum(1 for point in edge.coordinates if not map_area.contains_point(point[0], point[1]))
            if outside_count:
                issues.append(ValidationIssue("warning", "edge_outside_map", f"边 {edge.id} 有 {outside_count} 个几何点超出底图范围", "edge", edge.id))
    connected = _reachable_node_ids(graph)
    for node in graph.nodes.values():
        degree = sum(1 for edge in graph.edges.values() if edge.startid == node.id or edge.endid == node.id)
        if degree == 0:
            issues.append(ValidationIssue("warning", "isolated_node", f"节点 {node.id} 是孤立点", "node", node.id))
        if connected and node.id not in connected:
            issues.append(ValidationIssue("warning", "disconnected_node", f"节点 {node.id} 不在主连通区域", "node", node.id))
        if map_area:
            if not map_area.contains_point(node.x, node.y):
                issues.append(ValidationIssue("warning", "outside_map", f"节点 {node.id} 超出底图范围", "node", node.id))
    _check_near_nodes(graph, issues)
    _check_crossing_edges(graph, issues)
    return issues


def _check_edge_endpoint(graph: Any, edge: Any, start: bool, issues: list[Any]) -> None:
    from dog_remote_tool.modules.navigation.route_network import ValidationIssue

    node = graph.nodes.get(edge.startid if start else edge.endid)
    if node is None or not edge.coordinates:
        return
    point = edge.coordinates[0] if start else edge.coordinates[-1]
    dist = math.hypot(point[0] - node.x, point[1] - node.y)
    if dist > 0.25:
        label = "起点" if start else "终点"
        issues.append(ValidationIssue("error", "endpoint_mismatch", f"边 {edge.id} 几何{label}与节点 {node.id} 偏差 {dist:.2f}m", "edge", edge.id))


def _reachable_node_ids(graph: Any) -> set[int]:
    if not graph.nodes:
        return set()
    adjacency: dict[int, set[int]] = {}
    for edge in graph.edges.values():
        if edge.startid in graph.nodes and edge.endid in graph.nodes:
            adjacency.setdefault(edge.startid, set()).add(edge.endid)
            adjacency.setdefault(edge.endid, set()).add(edge.startid)
    start = next(iter(graph.nodes))
    seen = {start}
    stack = [start]
    while stack:
        node_id = stack.pop()
        for next_id in adjacency.get(node_id, set()):
            if next_id not in seen:
                seen.add(next_id)
                stack.append(next_id)
    return seen


def _check_near_nodes(graph: Any, issues: list[Any]) -> None:
    from dog_remote_tool.modules.navigation.route_network import ValidationIssue

    nodes = list(graph.nodes.values())
    for index, left in enumerate(nodes):
        for right in nodes[index + 1 :]:
            dist = math.hypot(left.x - right.x, left.y - right.y)
            if dist < 0.10:
                issues.append(ValidationIssue("warning", "near_nodes", f"节点 {left.id} 和 {right.id} 距离 {dist:.2f}m，建议合并", "node", left.id))


def _check_crossing_edges(graph: Any, issues: list[Any]) -> None:
    from dog_remote_tool.modules.navigation.route_network import ValidationIssue

    edges = list(graph.edges.values())
    for index, left in enumerate(edges):
        for right in edges[index + 1 :]:
            if {left.startid, left.endid} & {right.startid, right.endid}:
                continue
            if polylines_cross(left.coordinates, right.coordinates):
                issues.append(ValidationIssue("warning", "crossing_edges", f"边 {left.id} 与边 {right.id} 相交但没有共享交点", "edge", left.id))
