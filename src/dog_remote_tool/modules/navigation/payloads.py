from __future__ import annotations

import base64
import json
import math
from pathlib import PurePosixPath

from dog_remote_tool.core.quoting import yaml_string
from dog_remote_tool.core.profiles import ProductProfile
from dog_remote_tool.modules import mapping


DEFAULT_NAV_LATERAL_SPEED = 0.0
DEFAULT_NAV_ANGULAR_SPEED = 1.2


def alg_manager_ws_request_payload(req_func: str, frame_count: int, **data: object) -> str:
    payload = {
        "head": {
            "type": "app_req",
            "time_stamp": 0,
            "source": "app",
            "frame_count": frame_count,
        },
        "data": {"req_func": req_func, **data},
    }
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def alg_manager_start_multi_nav_by_points_payload(
    map_id: str,
    points: list[tuple[float, float, float]],
    frame_count: int,
) -> str:
    poses = []
    for x, y, yaw in points:
        poses.append(_pose_dict(x, y, yaw))
    payload = {
        "head": {
            "type": "app_req",
            "time_stamp": 0,
            "source": "app",
            "frame_count": frame_count,
        },
        "data": {"req_func": {"start_multi_nav_by_points": [map_id, "dog_remote_points", poses]}},
    }
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def alg_manager_start_multi_nav_task_route_value(
    map_id: str,
    route_geojson_path: str,
    points: list[tuple[float, float, float]],
    speed: float,
    tolerance: float,
) -> dict[str, object]:
    route_points = _route_points_with_forward_yaw(points)
    if not route_points:
        raise ValueError("路网导航至少需要 1 个点")
    tasks = []
    for x, y, yaw in route_points:
        goal = _pose_dict(x, y, yaw)
        tasks.append(
            {
                "type": "goal",
                "map_type": "route",
                "map_path": route_geojson_path,
                "goal_task_type": "route",
                "goal": goal,
                "goals": [goal],
                "speed": {"x": speed, "y": DEFAULT_NAV_LATERAL_SPEED, "z": DEFAULT_NAV_ANGULAR_SPEED},
                "goal_tolerance": {"x": tolerance, "y": tolerance, "theta": 0.1},
            }
        )
    return {
        "map_id": map_id,
        "tasks": tasks,
    }


def alg_manager_start_nav_payload(x: float, y: float, yaw: float) -> dict[str, object]:
    return {
        "map_type": "2d",
        **_pose_dict(x, y, yaw),
    }


def map_id_from_map_path(map_path: str) -> str:
    path = PurePosixPath(map_path.strip())
    if path.name in {"map.pcd", "map.pgm", "map.yaml"} and path.parent.name:
        return path.parent.name
    return path.name or map_path.strip()


def default_goal_map_path(profile: ProductProfile) -> str:
    return mapping.default_map_pcd_path(profile)


def _navigation_2d_map_path(map_pcd_path: str) -> str:
    if map_pcd_path.endswith(".pcd"):
        return map_pcd_path[:-4] + ".yaml"
    return map_pcd_path


def _initialize_payload(map_path: str, map_type: int = 1) -> str:
    return (
        "{header: {frame_id: \"map\"}, cmd: 0, tasks: ["
        "{task_type: 2, initial_task: {initial_task_type: 1, "
        f"map_type: {map_type}, map_path: {yaml_string(map_path)}"
        "}}"
        "]}"
    )


def _goal_payload(map_pcd_path: str, x: float, y: float, yaw: float, speed: float, tolerance: float) -> str:
    return "{header: {frame_id: \"map\"}, cmd: 1, tasks: [" + _goal_task_payload(
        map_pcd_path,
        x,
        y,
        yaw,
        speed,
        0.0,
    ) + "]}"


def _goal_task_payload(map_pcd_path: str, x: float, y: float, yaw: float, speed: float, tolerance: float) -> str:
    half = yaw / 2.0
    z = math.sin(half)
    w = math.cos(half)
    map_path = yaml_string(_navigation_2d_map_path(map_pcd_path))
    theta_tolerance = 0.0 if abs(tolerance) < 1e-9 else 0.1
    return (
        "{task_type: 3, goal_task: {goal_task_type: 1, source_type: 0, map_type: 1, map_path: " + map_path + ", "
        f"goal: {{position: {{x: {x:.9f}, y: {y:.9f}, z: 0.0}}, "
        f"orientation: {{x: 0.0, y: 0.0, z: {z:.9f}, w: {w:.9f}}}}}, "
        f"speed: {{x: {speed:.3f}, y: {DEFAULT_NAV_LATERAL_SPEED:.3f}, z: {DEFAULT_NAV_ANGULAR_SPEED:.3f}}}, "
        f"goal_tolerance: {{x: {tolerance:.3f}, y: {tolerance:.3f}, theta: {theta_tolerance:.3f}}}"
        "}}"
    )


def _goals_payload(
    map_pcd_path: str,
    points: list[tuple[float, float, float]],
    speed: float,
    tolerance: float = 0.25,
) -> str:
    if len(points) < 2:
        raise ValueError("多点导航至少需要 2 个点")
    tasks = ", ".join(_goal_task_payload(map_pcd_path, x, y, yaw, speed, tolerance) for x, y, yaw in points)
    return "{header: {frame_id: \"map\"}, cmd: 1, tasks: [" + tasks + "]}"


def _pose_yaml(x: float, y: float, yaw: float = 0.0) -> str:
    half = yaw / 2.0
    z = math.sin(half)
    w = math.cos(half)
    return (
        "{position: "
        f"{{x: {x:.9f}, y: {y:.9f}, z: 0.0}}, "
        f"orientation: {{x: 0.0, y: 0.0, z: {z:.9f}, w: {w:.9f}}}"
        "}"
    )


def _pose_dict(x: float, y: float, yaw: float = 0.0) -> dict[str, object]:
    half = yaw / 2.0
    return {
        "position": {"x": x, "y": y, "z": 0.0},
        "orientation": {"x": 0.0, "y": 0.0, "z": math.sin(half), "w": math.cos(half)},
    }


def _route_points_with_forward_yaw(points: list[tuple[float, float, float]]) -> list[tuple[float, float, float]]:
    if len(points) <= 1:
        return list(points)
    result: list[tuple[float, float, float]] = []
    last_yaw = points[0][2]
    for index, (x, y, yaw) in enumerate(points):
        if index + 1 < len(points):
            next_x, next_y, _next_yaw = points[index + 1]
            dx = next_x - x
            dy = next_y - y
            if abs(dx) > 1e-6 or abs(dy) > 1e-6:
                yaw = math.atan2(dy, dx)
                last_yaw = yaw
        else:
            yaw = last_yaw
        result.append((x, y, yaw))
    return result


def _command_payload(cmd: int) -> str:
    return f"{{header: {{frame_id: \"map\"}}, cmd: {cmd}, tasks: []}}"


def _payload_b64(payload: str) -> str:
    return base64.b64encode(payload.encode("utf-8")).decode("ascii")


def _start_arc_calibration_payload(tag_id: int = 0) -> str:
    return (
        "header:\n"
        "  stamp:\n"
        "    sec: 0\n"
        "    nanosec: 0\n"
        "  frame_id: ''\n"
        "cmd: 2\n"
        "secondary_cmd: 2\n"
        f"tag_id: {int(tag_id)}\n"
        "map_path: ''\n"
        "rth_goals: []\n"
        "speed:\n"
        "  x: 0.0\n"
        "  y: 0.0\n"
        "  z: 0.0\n"
        "extra_info: ''"
    )


def _map_path_prefix(map_pcd_path: str) -> str:
    path = map_pcd_path.rstrip("/")
    if "/" not in path:
        return "."
    return path.rsplit("/", 1)[0] or "/"
