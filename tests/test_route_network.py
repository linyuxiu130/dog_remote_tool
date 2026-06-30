import base64
import json
import re
from pathlib import Path

from dog_remote_tool.core.profiles import get_product
from dog_remote_tool.core.shell import quote
from dog_remote_tool.modules import navigation
from dog_remote_tool.modules.navigation import route_analysis
from dog_remote_tool.modules.navigation import route_commands
from dog_remote_tool.modules.navigation import route_direction
from dog_remote_tool.modules.navigation import route_geometry
from dog_remote_tool.modules.navigation import route_geojson
from dog_remote_tool.modules.navigation import route_map_yaml
from dog_remote_tool.modules.navigation import route_network
from dog_remote_tool.modules.navigation import route_topology
from dog_remote_tool.modules.navigation import route_validation
from dog_remote_tool.modules.navigation.route_network import MapMetadata, RouteEdge, RouteGraph, RouteNode
from helpers import remote_command as _remote_command


def _sample_graph():
    graph = RouteGraph()
    graph.nodes[1] = RouteNode(1, 0.0, 0.0, {"id": 1})
    graph.nodes[2] = RouteNode(2, 1.0, 0.0, {"id": 2})
    graph.nodes[3] = RouteNode(3, 2.0, 0.0, {"id": 3})
    graph.edges[10] = RouteEdge(10, 1, 2, [(0.0, 0.0), (1.0, 0.0)], 0, 1.0, {"id": 10})
    graph.edges[11] = RouteEdge(11, 2, 3, [(1.0, 0.0), (2.0, 0.0)], 1, 1.0, {"id": 11})
    return graph


def _start_navigation_payloads(command: str) -> list[str]:
    return [
        base64.b64decode(match.encode("ascii")).decode("utf-8")
        for match in re.findall(r"START_NAV_PAYLOAD=([A-Za-z0-9+/=]+);", command)
    ]


def test_geojson_roundtrip_preserves_route_fields(tmp_path):
    graph = _sample_graph()
    target = tmp_path / "map.geojson"

    route_network.save_geojson(graph, target)
    loaded = route_network.load_geojson(target)

    assert loaded.nodes[1].x == 0.0
    assert loaded.edges[10].startid == 1
    assert loaded.edges[10].endid == 2
    assert loaded.edges[11].direction == 1
    data = json.loads(target.read_text(encoding="utf-8"))
    assert data["type"] == "FeatureCollection"
    assert any(feature["properties"].get("startid") == 1 for feature in data["features"])
    assert any(feature["geometry"]["type"] == "MultiLineString" for feature in data["features"])
    edge_features = [feature for feature in data["features"] if feature["geometry"]["type"] == "MultiLineString"]
    assert all(feature["properties"]["passable_width"] == route_network.DEFAULT_ROUTE_PASSABLE_WIDTH for feature in edge_features)
    assert all(feature["properties"]["road_class"] == route_network.DEFAULT_ROUTE_ROAD_CLASS for feature in edge_features)


def test_new_export_defaults_match_navigation_package_route_values(tmp_path):
    graph = RouteGraph()
    graph.nodes[1] = RouteNode(1, 0.0, 0.0)
    graph.nodes[2] = RouteNode(2, 1.0, 0.0)
    graph.edges[1] = RouteEdge(1, 1, 2, [(0.0, 0.0), (1.0, 0.0)])

    data = route_network.graph_to_geojson(graph)
    edge = next(feature for feature in data["features"] if feature["geometry"]["type"] == "MultiLineString")

    assert edge["properties"]["direction"] == "both"
    assert edge["properties"]["passable_width"] == route_network.DEFAULT_ROUTE_PASSABLE_WIDTH
    assert edge["properties"]["road_class"] == route_network.DEFAULT_ROUTE_ROAD_CLASS
    assert edge["geometry"]["coordinates"] == [[[0.0, 0.0], [1.0, 0.0]]]


def test_geojson_import_preserves_and_defaults_passable_width(tmp_path):
    target = tmp_path / "map.geojson"
    target.write_text(
        json.dumps(
            {
                "type": "FeatureCollection",
                "features": [
                    {"type": "Feature", "geometry": {"type": "Point", "coordinates": [0.0, 0.0]}, "properties": {"id": 1}},
                    {"type": "Feature", "geometry": {"type": "Point", "coordinates": [1.0, 0.0]}, "properties": {"id": 2}},
                    {
                        "type": "Feature",
                        "geometry": {"type": "MultiLineString", "coordinates": [[[0.0, 0.0], [1.0, 0.0]]]},
                        "properties": {"id": 10, "startid": 1, "endid": 2, "direction": "both", "passable_width": 3.5, "road_class": 3},
                    },
                    {
                        "type": "Feature",
                        "geometry": {"type": "MultiLineString", "coordinates": [[[1.0, 0.0], [2.0, 0.0]]]},
                        "properties": {"id": 11, "startid": 2, "endid": 1, "direction": "forward"},
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    graph = route_network.load_geojson(target)

    assert route_network.edge_passable_width(graph.edges[10]) == 3.5
    assert route_network.edge_road_class(graph.edges[10]) == 3
    assert route_network.edge_passable_width(graph.edges[11]) == route_network.DEFAULT_ROUTE_PASSABLE_WIDTH
    assert route_network.edge_road_class(graph.edges[11]) == route_network.DEFAULT_ROUTE_ROAD_CLASS


def test_road_class_helpers_match_navigation_motion_model_mapping():
    edge = RouteEdge(1, 1, 2, [(0.0, 0.0), (1.0, 0.0)], "both", properties={"road_class": 9})

    assert route_network.edge_road_class(edge) == route_network.MAX_ROUTE_ROAD_CLASS
    assert route_network.road_class_label(3) == "3 同膝 WALK"

    route_network.set_edge_road_class(edge, 3)

    assert edge.road_class() == 3
    assert edge.properties["road_class"] == 3


def test_geojson_roundtrip_preserves_third_coordinate_values(tmp_path):
    target = tmp_path / "map.geojson"
    target.write_text(
        json.dumps(
            {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "geometry": {"type": "Point", "coordinates": [1.0, 2.0, 0.3]},
                        "properties": {"id": 1},
                    },
                    {
                        "type": "Feature",
                        "geometry": {"type": "Point", "coordinates": [3.0, 4.0, 0.4]},
                        "properties": {"id": 2},
                    },
                    {
                        "type": "Feature",
                        "geometry": {"type": "MultiLineString", "coordinates": [[[1.0, 2.0, 0.3], [3.0, 4.0, 0.4]]]},
                        "properties": {"id": 10, "startid": 1, "endid": 2, "direction": "both"},
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    loaded = route_network.load_geojson(target)
    exported = route_network.graph_to_geojson(loaded)

    point = next(feature for feature in exported["features"] if feature["geometry"]["type"] == "Point")
    edge = next(feature for feature in exported["features"] if feature["geometry"]["type"] == "MultiLineString")

    assert loaded.nodes[1].z == 0.3
    assert point["geometry"]["coordinates"] == [1.0, 2.0, 0.3]
    assert edge["geometry"]["coordinates"] == [[[1.0, 2.0, 0.3], [3.0, 4.0, 0.4]]]


def test_validation_reports_missing_references_and_endpoint_mismatch():
    graph = RouteGraph()
    graph.nodes[1] = RouteNode(1, 0.0, 0.0)
    graph.edges[2] = RouteEdge(2, 1, 99, [(1.0, 0.0), (2.0, 0.0)], 0)

    issues = route_network.validate_graph(graph)
    codes = {issue.code for issue in issues}

    assert "missing_end" in codes
    assert "endpoint_mismatch" in codes


def test_add_coordinate_route_node_preserves_precision_and_connects_nearest_node():
    graph = RouteGraph()
    graph.nodes[1] = RouteNode(1, 0.0, 0.0)
    graph.nodes[2] = RouteNode(2, 3.0, -7.0)
    graph.edges[5] = RouteEdge(5, 1, 2, [(0.0, 0.0), (3.0, -7.0)], "both")

    result = route_network.add_coordinate_route_node(
        graph,
        2.806028840,
        -7.476321017,
    )

    assert result.node_id == 3
    assert result.edge_id == 6
    assert result.connected_node_id == 2
    assert graph.nodes[3].x == 2.806028840
    assert graph.nodes[3].y == -7.476321017
    assert graph.nodes[3].properties["id"] == 3
    assert graph.nodes[3].properties["source"] == "manual_coordinate"
    assert graph.edges[6].startid == 2
    assert graph.edges[6].endid == 3
    assert graph.edges[6].coordinates == [(3.0, -7.0), (2.806028840, -7.476321017)]
    assert graph.edges[6].properties["direction"] == "both"
    assert graph.dirty is True


def test_add_coordinate_route_node_requires_existing_node_to_connect():
    graph = RouteGraph()

    try:
        route_network.add_coordinate_route_node(graph, 2.806028840, -7.476321017)
    except ValueError as exc:
        assert "至少需要一个已有路网节点" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_map_and_graph_bounds_support_scale_alignment_diagnostics():
    metadata = MapMetadata(Path("map.pgm"), resolution=0.05, origin=(-1.0, -2.0, 0.0))
    graph = RouteGraph()
    graph.nodes[1] = RouteNode(1, -0.5, -1.5)
    graph.nodes[2] = RouteNode(2, 1.0, 0.5)
    graph.edges[1] = RouteEdge(1, 1, 2, [(-0.5, -1.5), (1.0, 0.5)])

    map_area = route_network.map_bounds(metadata, (100, 80))
    graph_area = route_network.graph_bounds(graph)

    assert map_area.min_x == -1.0
    assert map_area.max_x == 4.0
    assert map_area.min_y == -2.0
    assert map_area.max_y == 2.0
    assert graph_area is not None
    assert map_area.contains_bounds(graph_area)


def test_validation_reports_edge_geometry_outside_map():
    metadata = MapMetadata(Path("map.pgm"), resolution=1.0, origin=(0.0, 0.0, 0.0))
    graph = RouteGraph()
    graph.nodes[1] = RouteNode(1, 1.0, 1.0)
    graph.nodes[2] = RouteNode(2, 2.0, 2.0)
    graph.edges[1] = RouteEdge(1, 1, 2, [(1.0, 1.0), (12.0, 2.0), (2.0, 2.0)])

    issues = route_network.validate_graph(graph, metadata, (10, 10))
    codes = {issue.code for issue in issues}

    assert "edge_outside_map" in codes


def test_split_crossing_edges_adds_shared_intersection_node():
    graph = RouteGraph()
    graph.nodes[1] = RouteNode(1, 0.0, 0.0)
    graph.nodes[2] = RouteNode(2, 2.0, 2.0)
    graph.nodes[3] = RouteNode(3, 0.0, 2.0)
    graph.nodes[4] = RouteNode(4, 2.0, 0.0)
    graph.edges[1] = RouteEdge(1, 1, 2, [(0.0, 0.0), (2.0, 2.0)])
    graph.edges[2] = RouteEdge(2, 3, 4, [(0.0, 2.0), (2.0, 0.0)])

    before_codes = {issue.code for issue in route_network.validate_graph(graph)}
    added_nodes, split_edges = route_network.split_crossing_edges(graph)
    after_codes = {issue.code for issue in route_network.validate_graph(graph)}

    assert "crossing_edges" in before_codes
    assert added_nodes == 1
    assert split_edges == 4
    assert len(graph.nodes) == 5
    assert len(graph.edges) == 4
    crossing_node = next(node for node in graph.nodes.values() if node.properties.get("source") == "auto_crossing")
    assert crossing_node.x == 1.0
    assert crossing_node.y == 1.0
    assert sum(1 for edge in graph.edges.values() if crossing_node.id in {edge.startid, edge.endid}) == 4
    assert "crossing_edges" not in after_codes


def test_split_crossing_edges_preserves_existing_polyline_vertices():
    graph = RouteGraph()
    graph.nodes[1] = RouteNode(1, 0.0, 0.0)
    graph.nodes[2] = RouteNode(2, 2.0, 0.0)
    graph.nodes[3] = RouteNode(3, 1.5, -1.0)
    graph.nodes[4] = RouteNode(4, 1.5, 1.0)
    graph.edges[1] = RouteEdge(1, 1, 2, [(0.0, 0.0), (1.0, 0.0), (2.0, 0.0)])
    graph.edges[2] = RouteEdge(2, 3, 4, [(1.5, -1.0), (1.5, 1.0)])

    added_nodes, split_edges = route_network.split_crossing_edges(graph)

    crossing_node = next(node for node in graph.nodes.values() if node.properties.get("source") == "auto_crossing")
    first_half = next(edge for edge in graph.edges.values() if edge.startid == 1 and edge.endid == crossing_node.id)
    second_half = next(edge for edge in graph.edges.values() if edge.startid == crossing_node.id and edge.endid == 2)

    assert added_nodes == 1
    assert split_edges == 4
    assert first_half.coordinates == [(0.0, 0.0), (1.0, 0.0), (1.5, 0.0)]
    assert second_half.coordinates == [(1.5, 0.0), (2.0, 0.0)]


def test_attach_isolated_nodes_to_edges_adds_new_edge_to_nearest_node_without_changing_existing_edge():
    graph = RouteGraph()
    graph.nodes[1] = RouteNode(1, 0.0, 0.0)
    graph.nodes[2] = RouteNode(2, 2.0, 0.0)
    graph.nodes[3] = RouteNode(3, 1.0, 0.0)
    graph.edges[1] = RouteEdge(1, 1, 2, [(0.0, 0.0), (2.0, 0.0)])

    before_codes = {issue.code for issue in route_network.validate_graph(graph)}
    original_edge = graph.edges[1]
    attached_nodes, created_edges = route_network.attach_isolated_nodes_to_edges(graph)
    after_issues = route_network.validate_graph(graph)

    assert "isolated_node" in before_codes
    assert attached_nodes == 1
    assert created_edges == 1
    assert graph.edges[1] is original_edge
    assert graph.edges[1].coordinates == [(0.0, 0.0), (2.0, 0.0)]
    assert graph.edges[2].startid == 3
    assert graph.edges[2].endid == 1
    assert graph.edges[2].coordinates == [(1.0, 0.0), (0.0, 0.0)]
    assert graph.edges[2].properties["source"] == "auto_attach_isolated"
    assert not any(issue.code == "isolated_node" and issue.object_id == 3 for issue in after_issues)


def test_shortest_path_respects_one_way_edges():
    graph = _sample_graph()

    forward = route_network.shortest_path(graph, 1, 3)
    backward = route_network.shortest_path(graph, 3, 1)

    assert forward.node_ids == [1, 2, 3]
    assert forward.edge_ids == [10, 11]
    assert not backward.reachable


def test_reverse_edge_direction_swaps_endpoints_and_geometry():
    edge = RouteEdge(1, 10, 20, [(1.0, 1.0), (2.0, 2.0), (3.0, 3.0)], "forward", 3.0)

    route_network.reverse_edge_direction(edge)

    assert edge.startid == 20
    assert edge.endid == 10
    assert edge.coordinates == [(3.0, 3.0), (2.0, 2.0), (1.0, 1.0)]
    assert edge.direction == "forward"
    assert edge.properties["startid"] == 20
    assert edge.properties["endid"] == 10
    assert edge.properties["direction"] == "forward"


def test_route_direction_normalization_keeps_legacy_values_simple():
    assert route_network.normalized_direction("both") == "both"
    assert route_network.normalized_direction("0") == "both"
    assert route_network.normalized_direction(2) == "both"
    assert route_network.normalized_direction("双向") == "both"
    assert route_network.normalized_direction("forward") == "forward"
    assert route_network.normalized_direction("1") == "forward"
    assert route_network.direction_label("0") == "双向"
    assert route_network.direction_label("1") == "单向"


def test_route_robot_commands_use_expected_paths_and_service():
    profile = get_product("xg2_s100")

    upload = route_network.upload_route_file_command(profile, "/tmp/map.geojson")
    pull = route_network.pull_route_file_command(profile, "/ota/alg_data/map/map.geojson", "/tmp/map.geojson")
    load = route_network.update_graph_command(profile, "/ota/alg_data/map/map.geojson")
    pose = route_network.current_pose_command(profile)
    exists = route_network.route_file_exists_command(profile, "/ota/alg_data/map/map.geojson")

    assert "/ota/alg_data/map/map.geojson" in upload.command
    assert "ProxyCommand=" in upload.command
    assert "ProxyCommand=" in pull.command
    assert "robot@192.168.234.1" in upload.command
    assert route_network.UPDATE_GRAPH_SERVICE in load.command
    assert route_network.UPDATE_GRAPH_TYPE in load.command
    assert "/odom/current_pose" in pose
    assert 'create_node("dog_remote_current_pose_reader")' in pose
    assert "create_subscription(Odometry, \"/odom/current_pose\"" in pose
    assert "rclpy.spin_once" in pose
    assert "ros2 topic echo --once" not in pose
    assert "/localization_state" in pose
    assert "/robot_slam/localization_state" in pose
    assert pose.index("/robot_slam/localization_state") < pose.index("/localization_state")
    assert "定位状态未就绪" in pose
    assert "localization_ready(code, desc, field)" in pose
    assert "code in (\"3\", \"100\")" in pose
    assert "LOCALIZATION_CODE" in pose
    assert "LOCALIZATION_DESC" in pose
    assert "POSE=ros_error" in pose
    assert "ROUTE_FILE_OK" in exists
    assert "ros2 service list" not in exists
    assert "ros2 topic list" not in exists


def test_route_network_quotes_paths_in_status_messages():
    profile = get_product("xg2_s100")
    local_file = "/tmp/a'route.geojson"
    remote_file = "/ota/alg_data/map/a'route.geojson"

    upload = route_network.upload_route_file_command(profile, local_file)
    load = route_network.update_graph_command(profile, remote_file)
    load_remote_command = _remote_command(load, profile.target)

    assert f"test -s {quote(local_file)}" in upload.command
    assert quote(f"[ERROR] 本地路网文件不存在或为空: {local_file}") in upload.command
    assert "echo '[ERROR] 本地路网文件不存在或为空:" not in upload.command
    assert "sudo_run install -d -m 0755" in upload.command
    assert "sudo_run install -m 0644" in upload.command
    assert "mv -f" not in upload.command
    assert f"[ ! -s {quote(remote_file)} ]" in load_remote_command
    assert quote(f"[ERROR] 远端路网 GeoJSON 不存在: {remote_file}") in load_remote_command
    assert "echo '[ERROR] 远端路网 GeoJSON 不存在:" not in load_remote_command


def test_route_network_upload_map_route_files_uses_sudo_install():
    profile = get_product("xg2_s100")
    spec = route_network.upload_map_route_files_command(
        profile,
        "/tmp/local map/map.pgm",
        "/tmp/local map/map.yaml",
        "/tmp/local map/map.geojson",
        "/ota/alg_data/map/history_map/a/map.pgm",
    )

    assert spec.title == "上传地图和路网文件"
    assert "test -s '/tmp/local map/map.pgm'" in spec.command
    assert "test -s '/tmp/local map/map.yaml'" in spec.command
    assert "test -s '/tmp/local map/map.geojson'" in spec.command
    assert "-o ConnectTimeout=20" in spec.command
    assert spec.command.count(" scp ") == 3
    for remote_name in ("map.pgm", "map.yaml", "map.geojson"):
        remote_target = f"{profile.target}:/home/robot/dog_remote_tool_map_route_upload/{remote_name}"
        preceding = spec.command[: spec.command.index(remote_target)]
        assert "ProxyCommand=" in preceding
    assert "sudo_run install -d -m 0755 /ota/alg_data/map/history_map/a" in spec.command
    assert "sudo_run install -m 0644 /home/robot/dog_remote_tool_map_route_upload/map.pgm /ota/alg_data/map/history_map/a/map.pgm" in spec.command
    assert "sudo_run install -m 0644 /home/robot/dog_remote_tool_map_route_upload/map.yaml /ota/alg_data/map/history_map/a/map.yaml" in spec.command
    assert "sudo_run install -m 0644 /home/robot/dog_remote_tool_map_route_upload/map.geojson /ota/alg_data/map/history_map/a/map.geojson" in spec.command
    assert "mv -f" not in spec.command


def test_parse_current_pose_output_extracts_xy_and_yaw():
    pose = route_network.parse_current_pose_output("POSE=ok\nX=1.25\nY=-2.5\nYAW=0.75\n")

    assert pose is not None
    assert pose.x == 1.25
    assert pose.y == -2.5
    assert pose.yaw == 0.75


def test_parse_current_pose_output_rejects_missing_pose():
    assert route_network.parse_current_pose_output("POSE=unavailable\n") is None


def test_current_pose_failure_message_reports_specific_cause():
    ros_error = route_network.current_pose_failure_message(
        "POSE=ros_error\nERROR=Error setting up zenoh session\n",
        5,
    )
    localization_error = route_network.current_pose_failure_message("POSE=localization_not_ready\n", 4)
    odom_error = route_network.current_pose_failure_message("POSE=unavailable\n", 2)

    assert "ROS 2 / zenoh 通信初始化失败" in ros_error
    assert "Error setting up zenoh session" in ros_error
    assert "定位状态未就绪" in localization_error
    assert "/odom/current_pose" in odom_error


def test_navigation_route_goal_command_uses_route_map_type():
    profile = get_product("xg2_s100")

    spec = navigation.start_route_goal_command(
        profile,
        "/ota/alg_data/map/map.pcd",
        "/ota/alg_data/map/map.geojson",
        1.0,
        2.0,
        0.0,
        0.5,
        0.2,
    )

    assert spec.title == "发送路网导航目标"
    payloads = _start_navigation_payloads(spec.command)
    payload = payloads[-1]
    assert "map_type: 3" in payload
    assert "goal_task_type: 3" in payload
    assert "/load_map_service" not in spec.command
    assert "/RouteGraphPlanner/update_graph" in spec.command
    assert "路网已更新" in spec.command
    assert "路网更新失败，已取消下发目标" in spec.command
    assert "TOPIC_LIST=$(timeout" not in spec.command
    assert "ros2 topic info /start_navigation" not in spec.command
    assert '{header: {frame_id: "map"}, cmd: 0' not in spec.command
    assert '{header: {frame_id: "map"}, cmd: 1' in payload
    assert "正在提交路网导航目标" in spec.command
