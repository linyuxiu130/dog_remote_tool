from __future__ import annotations

from dataclasses import dataclass, field
import math
from pathlib import Path, PurePosixPath
from typing import Any

from dog_remote_tool.modules.navigation import route_analysis as _route_analysis
from dog_remote_tool.modules.navigation import route_commands as _route_commands
from dog_remote_tool.modules.navigation import route_direction as _route_direction

RouteCoordinate = tuple[float, float] | tuple[float, float, float]

DEFAULT_ROUTE_PASSABLE_WIDTH = 2.0
MIN_ROUTE_PASSABLE_WIDTH = 0.2
MAX_ROUTE_PASSABLE_WIDTH = 10.0
DEFAULT_ROUTE_ROAD_CLASS = 0
MIN_ROUTE_ROAD_CLASS = 0
MAX_ROUTE_ROAD_CLASS = 3
ROUTE_ROAD_CLASS_OPTIONS = (
    (0, "0 对膝 WALK"),
    (1, "1 对膝 WALK"),
    (2, "2 对膝 WALK"),
    (3, "3 同膝 WALK"),
)
ROUTE_ROAD_CLASS_MODE_OPTIONS = (
    (0, "对膝 0/1/2"),
    (3, "同膝 3"),
)


DEFAULT_REMOTE_ROUTE_DIR = _route_commands.DEFAULT_REMOTE_ROUTE_DIR
DEFAULT_REMOTE_ROUTE_FILE = _route_commands.DEFAULT_REMOTE_ROUTE_FILE
UPDATE_GRAPH_SERVICE = _route_commands.UPDATE_GRAPH_SERVICE
UPDATE_GRAPH_TYPE = _route_commands.UPDATE_GRAPH_TYPE
ROUTE_GRAPH_TOPIC = _route_commands.ROUTE_GRAPH_TOPIC
NAV_POINT_REQUIRED_FIELDS = _route_analysis.NAV_POINT_REQUIRED_FIELDS
NAV_EDGE_REQUIRED_FIELDS = _route_analysis.NAV_EDGE_REQUIRED_FIELDS
ROUTE_DIRECTION_BOTH = _route_direction.ROUTE_DIRECTION_BOTH
ROUTE_DIRECTION_FORWARD = _route_direction.ROUTE_DIRECTION_FORWARD
ROUTE_DIRECTION_BOTH_VALUES = _route_direction.ROUTE_DIRECTION_BOTH_VALUES
analyze_geojson_file = _route_analysis.analyze_geojson_file
CurrentPose = _route_commands.CurrentPose
current_pose_command = _route_commands.current_pose_command
current_pose_failure_message = _route_commands.current_pose_failure_message
list_route_file_command = _route_commands.list_route_file_command
parse_current_pose_output = _route_commands.parse_current_pose_output
pull_route_file_command = _route_commands.pull_route_file_command
route_file_exists_command = _route_commands.route_file_exists_command
route_status_command = _route_commands.route_status_command
route_status_spec = _route_commands.route_status_spec
update_graph_command = _route_commands.update_graph_command
upload_map_route_files_command = _route_commands.upload_map_route_files_command
upload_route_file_command = _route_commands.upload_route_file_command


@dataclass
class RouteNode:
    id: int
    x: float
    y: float
    properties: dict[str, Any] = field(default_factory=dict)
    z: float | None = None


@dataclass
class RouteEdge:
    id: int
    startid: int
    endid: int
    coordinates: list[RouteCoordinate]
    direction: int | str = "both"
    cost: float = 0.0
    properties: dict[str, Any] = field(default_factory=dict)

    def length(self) -> float:
        return polyline_length(self.coordinates)

    def is_reverse_allowed(self) -> bool:
        return normalized_direction(self.direction) == ROUTE_DIRECTION_BOTH

    def passable_width(self) -> float:
        return edge_passable_width(self)

    def road_class(self) -> int:
        return edge_road_class(self)


@dataclass
class RouteGraph:
    nodes: dict[int, RouteNode] = field(default_factory=dict)
    edges: dict[int, RouteEdge] = field(default_factory=dict)
    import_issues: list[Any] = field(default_factory=list)
    source_path: str = ""
    dirty: bool = False

    def next_node_id(self) -> int:
        return (max(self.nodes) + 1) if self.nodes else 1

    def next_edge_id(self) -> int:
        return (max(self.edges) + 1) if self.edges else 1


@dataclass(frozen=True)
class MapMetadata:
    image_path: Path
    resolution: float
    origin: tuple[float, float, float]
    occupied_thresh: float = 0.65
    free_thresh: float = 0.196
    negate: int = 0

    def world_to_pixel(self, x: float, y: float, image_height: int) -> tuple[float, float]:
        px = (x - self.origin[0]) / self.resolution
        py = image_height - (y - self.origin[1]) / self.resolution
        return px, py

    def pixel_to_world(self, px: float, py: float, image_height: int) -> tuple[float, float]:
        x = self.origin[0] + px * self.resolution
        y = self.origin[1] + (image_height - py) * self.resolution
        return x, y


@dataclass(frozen=True)
class Bounds:
    min_x: float
    min_y: float
    max_x: float
    max_y: float

    @property
    def width(self) -> float:
        return self.max_x - self.min_x

    @property
    def height(self) -> float:
        return self.max_y - self.min_y

    def contains_point(self, x: float, y: float, tolerance: float = 0.0) -> bool:
        return (
            self.min_x - tolerance <= x <= self.max_x + tolerance
            and self.min_y - tolerance <= y <= self.max_y + tolerance
        )

    def contains_bounds(self, other: "Bounds", tolerance: float = 0.0) -> bool:
        return (
            self.contains_point(other.min_x, other.min_y, tolerance)
            and self.contains_point(other.max_x, other.max_y, tolerance)
        )


@dataclass(frozen=True)
class ValidationIssue:
    severity: str
    code: str
    message: str
    object_type: str = ""
    object_id: int | None = None


@dataclass(frozen=True)
class PathResult:
    node_ids: list[int]
    edge_ids: list[int]
    cost: float

    @property
    def reachable(self) -> bool:
        return bool(self.node_ids)


@dataclass(frozen=True)
class CoordinateRouteNodeResult:
    node_id: int
    edge_id: int
    connected_node_id: int
    distance: float


normalized_direction = _route_direction.normalized_direction
direction_label = _route_direction.direction_label
edge_direction_change = _route_direction.edge_direction_change
apply_edge_direction = _route_direction.apply_edge_direction
reverse_edge_direction = _route_direction.reverse_edge_direction


def route_geojson_for_remote_map(remote_pgm: str) -> str:
    if not remote_pgm:
        return DEFAULT_REMOTE_ROUTE_FILE
    return str(PurePosixPath(remote_pgm).with_name("map.geojson"))


def normalized_passable_width(value: Any, default: float = DEFAULT_ROUTE_PASSABLE_WIDTH) -> float:
    try:
        width = float(value)
    except (TypeError, ValueError):
        width = default
    if width < MIN_ROUTE_PASSABLE_WIDTH:
        return MIN_ROUTE_PASSABLE_WIDTH
    if width > MAX_ROUTE_PASSABLE_WIDTH:
        return MAX_ROUTE_PASSABLE_WIDTH
    return width


def edge_passable_width(edge: RouteEdge, default: float = DEFAULT_ROUTE_PASSABLE_WIDTH) -> float:
    return normalized_passable_width(edge.properties.get("passable_width"), default)


def set_edge_passable_width(edge: RouteEdge, width: float) -> float:
    normalized = normalized_passable_width(width)
    edge.properties["passable_width"] = normalized
    return normalized


def normalized_road_class(value: Any, default: int = DEFAULT_ROUTE_ROAD_CLASS) -> int:
    try:
        road_class = int(value)
    except (TypeError, ValueError):
        road_class = default
    if road_class < MIN_ROUTE_ROAD_CLASS:
        return MIN_ROUTE_ROAD_CLASS
    if road_class > MAX_ROUTE_ROAD_CLASS:
        return MAX_ROUTE_ROAD_CLASS
    return road_class


def edge_road_class(edge: RouteEdge, default: int = DEFAULT_ROUTE_ROAD_CLASS) -> int:
    return normalized_road_class(edge.properties.get("road_class"), default)


def set_edge_road_class(edge: RouteEdge, road_class: int) -> int:
    normalized = normalized_road_class(road_class)
    edge.properties["road_class"] = normalized
    return normalized


def road_class_mode_value(road_class: Any) -> int:
    return 3 if normalized_road_class(road_class) == 3 else 0


def road_class_label(road_class: Any) -> str:
    normalized = normalized_road_class(road_class)
    for value, label in ROUTE_ROAD_CLASS_OPTIONS:
        if value == normalized:
            return label
    return str(normalized)


def node_coordinate_tuple(node: RouteNode) -> RouteCoordinate:
    if node.z is not None:
        return (node.x, node.y, node.z)
    return (node.x, node.y)


def add_coordinate_route_node(
    graph: RouteGraph,
    x: float,
    y: float,
    *,
    direction: int | str = ROUTE_DIRECTION_BOTH,
    passable_width: float = DEFAULT_ROUTE_PASSABLE_WIDTH,
    road_class: int = DEFAULT_ROUTE_ROAD_CLASS,
    edge_starts_at_new: bool = False,
) -> CoordinateRouteNodeResult:
    if not graph.nodes:
        raise ValueError("至少需要一个已有路网节点，才能自动连接输入坐标")
    nearest = min(graph.nodes.values(), key=lambda node: math.hypot(node.x - x, node.y - y))
    distance = math.hypot(nearest.x - x, nearest.y - y)
    node_id = graph.next_node_id()
    edge_id = graph.next_edge_id()
    node = RouteNode(
        node_id,
        float(x),
        float(y),
        {"id": node_id, "source": "manual_coordinate"},
    )
    start_id = node_id if edge_starts_at_new else nearest.id
    end_id = nearest.id if edge_starts_at_new else node_id
    start_coord = (float(x), float(y)) if edge_starts_at_new else node_coordinate_tuple(nearest)
    end_coord = node_coordinate_tuple(nearest) if edge_starts_at_new else (float(x), float(y))
    edge = RouteEdge(
        edge_id,
        start_id,
        end_id,
        [start_coord, end_coord],
        direction,
        distance,
        {"id": edge_id, "startid": start_id, "endid": end_id, "direction": direction},
    )
    set_edge_passable_width(edge, passable_width)
    set_edge_road_class(edge, road_class)
    graph.nodes[node_id] = node
    graph.edges[edge_id] = edge
    graph.dirty = True
    return CoordinateRouteNodeResult(node_id, edge_id, nearest.id, distance)


from dog_remote_tool.modules.navigation import route_geometry as _route_geometry

polyline_length = _route_geometry.polyline_length
map_bounds = _route_geometry.map_bounds
graph_bounds = _route_geometry.graph_bounds
nearest_node = _route_geometry.nearest_node

from dog_remote_tool.modules.navigation import route_geojson as _route_geojson

read_map_yaml = _route_geojson.read_map_yaml
load_geojson = _route_geojson.load_geojson
route_graph_from_geojson = _route_geojson.route_graph_from_geojson
graph_to_geojson = _route_geojson.graph_to_geojson
node_coordinates = _route_geojson.node_coordinates
coordinate_values = _route_geojson.coordinate_values
save_geojson = _route_geojson.save_geojson


from dog_remote_tool.modules.navigation import route_validation as _route_validation

validate_graph = _route_validation.validate_graph


from dog_remote_tool.modules.navigation import route_topology as _route_topology

split_crossing_edges = _route_topology.split_crossing_edges
attach_isolated_nodes_to_edges = _route_topology.attach_isolated_nodes_to_edges
shortest_path = _route_topology.shortest_path
