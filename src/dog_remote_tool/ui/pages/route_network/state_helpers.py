from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from dog_remote_tool.modules.navigation import route_network
from dog_remote_tool.modules.navigation.route_network import RouteGraph


@dataclass(frozen=True)
class RouteObjectProperties:
    object_type: str
    object_id: str
    start: str
    end: str
    direction_enabled: bool
    metric: str
    direction: int | str | None = None
    passable_width: float | None = None
    road_class: int | None = None


def default_local_geojson_path(map_path: str, home: Path) -> Path:
    map_path = map_path.strip()
    if map_path:
        return Path(map_path).with_name("map.geojson")
    return home / "map.geojson"


def path_preview_text(result) -> tuple[str, str]:
    if result.reachable:
        return f"路径：{' -> '.join(map(str, result.node_ids))}\n边数 {len(result.edge_ids)}，代价 {result.cost:.2f}", "success"
    return "不可达，请检查断点或单向边。", "error"


def route_object_properties(graph: RouteGraph, object_type: str, object_id: int) -> RouteObjectProperties | None:
    if object_type == "node" and object_id in graph.nodes:
        node = graph.nodes[object_id]
        z_text = f" / z={node.z:.3f}" if node.z is not None else ""
        return RouteObjectProperties(
            object_type="节点",
            object_id=str(node.id),
            start=f"{node.x:.3f}",
            end=f"{node.y:.3f}",
            direction_enabled=False,
            metric=f"节点位置可在上方 X/Y 查看{z_text}",
            passable_width=None,
            road_class=None,
        )
    if object_type == "edge" and object_id in graph.edges:
        edge = graph.edges[object_id]
        length = edge.length()
        return RouteObjectProperties(
            object_type="边",
            object_id=str(edge.id),
            start=str(edge.startid),
            end=str(edge.endid),
            direction_enabled=True,
            metric=(
                f"长度 {length:.2f} m；cost {edge.cost or length:.2f}；"
                f"路宽 {route_network.edge_passable_width(edge):.2f} m；"
                f"{route_network.road_class_label(route_network.edge_road_class(edge))}"
            ),
            direction=route_network.normalized_direction(edge.direction),
            passable_width=route_network.edge_passable_width(edge),
            road_class=route_network.edge_road_class(edge),
        )
    return None
