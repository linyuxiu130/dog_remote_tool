from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from dog_remote_tool.modules.navigation import route_map_yaml
from dog_remote_tool.modules.navigation.route_network import (
    RouteCoordinate,
    RouteEdge,
    RouteGraph,
    RouteNode,
    ValidationIssue,
    edge_passable_width,
    edge_road_class,
    set_edge_passable_width,
    set_edge_road_class,
)
from dog_remote_tool.modules.navigation.route_geometry import polyline_length


read_map_yaml = route_map_yaml.read_map_yaml



def load_geojson(path: str | Path) -> RouteGraph:
    source = Path(path)
    data = json.loads(source.read_text(encoding="utf-8"))
    graph = route_graph_from_geojson(data)
    graph.source_path = str(source)
    return graph


def route_graph_from_geojson(data: dict[str, Any]) -> RouteGraph:
    if data.get("type") != "FeatureCollection":
        raise ValueError("GeoJSON 必须是 FeatureCollection")
    graph = RouteGraph()
    seen_nodes: set[int] = set()
    seen_edges: set[int] = set()
    for feature in data.get("features", []):
        if not isinstance(feature, dict):
            continue
        geometry = feature.get("geometry") or {}
        properties = dict(feature.get("properties") or {})
        geometry_type = geometry.get("type")
        coords = geometry.get("coordinates")
        if geometry_type == "Point" and isinstance(coords, list) and len(coords) >= 2:
            node_id = _int_property(properties, "id")
            if node_id is None:
                continue
            if node_id in seen_nodes:
                graph.import_issues.append(ValidationIssue("error", "duplicate_node_id", f"节点 ID 重复：{node_id}", "node", node_id))
            seen_nodes.add(node_id)
            z = float(coords[2]) if len(coords) >= 3 and isinstance(coords[2], (int, float)) else _float_property(properties, "z")
            graph.nodes[node_id] = RouteNode(node_id, float(coords[0]), float(coords[1]), properties, z)
        elif geometry_type in {"LineString", "MultiLineString"}:
            edge_id = _int_property(properties, "id")
            startid = _int_property(properties, "startid")
            endid = _int_property(properties, "endid")
            if edge_id is None or startid is None or endid is None:
                continue
            if edge_id in seen_edges:
                graph.import_issues.append(ValidationIssue("error", "duplicate_edge_id", f"边 ID 重复：{edge_id}", "edge", edge_id))
            seen_edges.add(edge_id)
            line = _flatten_line_coordinates(coords)
            if len(line) < 2:
                continue
            direction = properties.get("direction", "both")
            cost = _float_property(properties, "cost") or polyline_length(line)
            edge = RouteEdge(edge_id, startid, endid, line, direction, cost, properties)
            set_edge_passable_width(edge, properties.get("passable_width"))
            set_edge_road_class(edge, properties.get("road_class"))
            graph.edges[edge_id] = edge
    return graph


def graph_to_geojson(graph: RouteGraph) -> dict[str, Any]:
    features: list[dict[str, Any]] = []
    for node in sorted(graph.nodes.values(), key=lambda item: item.id):
        props = dict(node.properties)
        props["id"] = node.id
        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": node_coordinates(node)},
                "properties": props,
            }
        )
    for edge in sorted(graph.edges.values(), key=lambda item: item.id):
        props = dict(edge.properties)
        props.update(
            {
                "id": edge.id,
                "startid": edge.startid,
                "endid": edge.endid,
                "direction": edge.direction,
                "cost": edge.cost or edge.length(),
                "passable_width": edge_passable_width(edge),
                "road_class": edge_road_class(edge),
            }
        )
        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "MultiLineString", "coordinates": [[coordinate_values(point) for point in edge.coordinates]]},
                "properties": props,
            }
        )
    return {"type": "FeatureCollection", "features": features}


def node_coordinates(node: RouteNode) -> list[float]:
    coords = [node.x, node.y]
    if node.z is not None:
        coords.append(node.z)
    return coords


def coordinate_values(point: RouteCoordinate) -> list[float]:
    values = [point[0], point[1]]
    if len(point) >= 3:
        values.append(point[2])
    return values


def save_geojson(graph: RouteGraph, path: str | Path) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(graph_to_geojson(graph), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    graph.source_path = str(target)
    graph.dirty = False


def _int_property(properties: dict[str, Any], key: str) -> int | None:
    try:
        return int(properties[key])
    except (KeyError, TypeError, ValueError):
        return None


def _float_property(properties: dict[str, Any], key: str) -> float | None:
    try:
        return float(properties[key])
    except (KeyError, TypeError, ValueError):
        return None


def _flatten_line_coordinates(coords: Any) -> list[RouteCoordinate]:
    if not isinstance(coords, list):
        return []
    if coords and isinstance(coords[0], list) and coords[0] and isinstance(coords[0][0], (int, float)):
        points: list[RouteCoordinate] = []
        for item in coords:
            if not isinstance(item, list) or len(item) < 2:
                continue
            if len(item) >= 3 and isinstance(item[2], (int, float)):
                points.append((float(item[0]), float(item[1]), float(item[2])))
            else:
                points.append((float(item[0]), float(item[1])))
        return points
    points: list[RouteCoordinate] = []
    for part in coords:
        for point in _flatten_line_coordinates(part):
            if not points or points[-1] != point:
                points.append(point)
    return points
