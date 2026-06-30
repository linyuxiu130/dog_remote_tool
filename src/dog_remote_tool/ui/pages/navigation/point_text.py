from __future__ import annotations

import math

from dog_remote_tool.modules.navigation import route_network

NavigationPoint = tuple[float, float, float]


def format_waypoint_line(x: float, y: float, yaw: float) -> str:
    return f"{x:.9f},{y:.9f},{yaw:.9f}"


def waypoint_lines(text: str) -> list[str]:
    return [line for line in text.splitlines() if line.strip()]


def parse_navigation_points(text: str, fallback: NavigationPoint) -> list[NavigationPoint]:
    points: list[NavigationPoint] = []
    for line_number, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line:
            continue
        parts = [part.strip() for part in line.replace("，", ",").split(",")]
        if len(parts) not in (2, 3):
            raise ValueError(f"第 {line_number} 行格式应为 x,y 或 x,y,yaw")
        try:
            x = float(parts[0])
            y = float(parts[1])
            yaw = float(parts[2]) if len(parts) == 3 else 0.0
        except ValueError as exc:
            raise ValueError(f"第 {line_number} 行包含非数字坐标") from exc
        points.append((x, y, yaw))
    return points or [fallback]


def visible_navigation_points(text: str, goal_selected: bool, fallback: NavigationPoint) -> list[NavigationPoint]:
    try:
        points = parse_navigation_points(text, fallback)
    except ValueError:
        return []
    if not text.strip() and not goal_selected:
        return []
    return points


def format_target_summary(
    points: list[NavigationPoint],
    *,
    route_target_mode: bool,
    route_graph: route_network.RouteGraph | None,
) -> str:
    if route_target_mode:
        route_prefix = (
            f"路网：{len(route_graph.nodes)} 点 / {len(route_graph.edges)} 边；"
            if route_graph is not None
            else "路网：未加载；"
        )
        if len(points) >= 2:
            _x, _y, yaw = points[-1]
            return f"{route_prefix}已设定 {len(points)} 个路网目标节点，末端方向={math.degrees(yaw):.0f}°"
        if len(points) == 1:
            x, y, yaw = points[-1]
            return f"{route_prefix}目标节点：x={x:.2f}, y={y:.2f}, 方向={math.degrees(yaw):.0f}°"
        return f"{route_prefix}点击路网节点附近设定目标"
    if len(points) >= 2:
        return f"目标路线：{len(points)} 个目标，点击地图继续追加"
    if len(points) == 1:
        x, y, yaw = points[-1]
        return f"目标点：x={x:.2f}, y={y:.2f}, 方向={math.degrees(yaw):.0f}°"
    return "目标点：点击地图添加目标"


def format_navigation_point_rows(points: list[NavigationPoint], *, route_target_mode: bool) -> list[str]:
    if route_target_mode:
        return [
            f"{index}. 路网目标节点  x={x:.3f}, y={y:.3f}, 方向={math.degrees(yaw):.0f}°"
            for index, (x, y, yaw) in enumerate(points, start=1)
        ]
    return [
        f"{index}. x={x:.3f}, y={y:.3f}, 方向={math.degrees(yaw):.0f}°"
        for index, (x, y, yaw) in enumerate(points, start=1)
    ]


def robot_pose_summary_text(
    robot_pose: NavigationPoint | None,
    last_status_values: dict[str, str],
) -> str:
    if robot_pose is None:
        if last_status_values.get("LOCALIZATION_READY") == "1":
            return "机器人：定位正常，等待位姿"
        return "机器人：等待定位"
    x, y, yaw = robot_pose
    return f"机器人：x={x:.2f}, y={y:.2f}, 方向={math.degrees(yaw):.0f}°"
