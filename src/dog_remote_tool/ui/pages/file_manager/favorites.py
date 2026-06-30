from __future__ import annotations

import json

from dog_remote_tool.modules import file_manager


DEFAULT_REMOTE_FAVORITES: dict[str, tuple[str, ...]] = {
    "xg3588": (
        "/home/firefly",
        "/home/firefly/.ros/log",
        "/tmp",
        "/tmp/log",
        "/opt/robot",
        "/opt/robot/robot_nav",
        "/etc",
    ),
    "xg1_nx": (
        "/home/robot",
        "/home/robot/.ros/log",
        "/tmp",
        "/tmp/log",
        "/tmp/log/alg_data",
        "/ota",
        "/ota/alg_data/map",
        "/opt/robot",
        "/opt/robot/nx-launch",
        "/opt/robot/robot_nav",
        "/opt/robot/robot_slam",
        "/opt/robot/robot_arc",
        "/opt/nvidia/camera",
    ),
    "xg2_3588": (
        "/home/robot",
        "/home/robot/.ros/log",
        "/tmp",
        "/tmp/zsibot/log",
        "/tmp/log",
        "/ota",
        "/ota/alg_data/map",
        "/opt/robot",
        "/opt/robot/robot_nav",
        "/opt/robot/robot_slam",
        "/opt/robot/robot_arc",
        "/etc",
    ),
    "xg2_s100": (
        "/home/robot",
        "/home/robot/.ros/log",
        "/tmp",
        "/tmp/zsibot/log",
        "/tmp/log",
        "/tmp/log/alg_data",
        "/ota",
        "/ota/alg_data/map",
        "/opt/robot",
        "/opt/robot/robot_nav",
        "/opt/robot/robot_slam",
        "/etc",
    ),
    "zg3588": (
        "/home/robot",
        "/home/robot/.ros/log",
        "/tmp",
        "/tmp/zsibot/log",
        "/tmp/log",
        "/ota",
        "/ota/alg_data/map",
        "/opt/robot",
        "/opt/robot/robot_nav",
        "/opt/robot/robot_slam",
        "/opt/robot/robot_arc",
        "/etc",
    ),
    "zg_surround_3588": (
        "/home/robot",
        "/home/robot/.ros/log",
        "/tmp",
        "/tmp/zsibot/log",
        "/tmp/log",
        "/ota",
        "/ota/alg_data/map",
        "/opt/robot",
        "/opt/robot/robot_nav",
        "/opt/robot/robot_slam",
        "/opt/robot/robot_arc",
        "/etc",
    ),
    "zg_surround_s100": (
        "/home/robot",
        "/home/robot/.ros/log",
        "/tmp",
        "/tmp/zsibot/log",
        "/tmp/log",
        "/tmp/log/alg_data",
        "/ota",
        "/ota/alg_data/map",
        "/opt/robot",
        "/opt/robot/robot_nav",
        "/opt/robot/robot_slam",
        "/etc",
    ),
    "zg_lidar_nx": (
        "/home/robot",
        "/home/robot/.ros/log",
        "/tmp",
        "/tmp/zsibot/log",
        "/tmp/log",
        "/tmp/log/alg_data",
        "/ota",
        "/ota/alg_data/map",
        "/opt/robot",
        "/opt/robot/robot_nav",
        "/opt/robot/robot_slam",
        "/opt/robot/robot_arc",
        "/opt/nvidia/camera",
    ),
}


def favorite_storage_key(profile_key: str) -> str:
    return f"file_manager/favorites/{profile_key}"


def default_favorites(profile_key: str, home: str) -> list[str]:
    favorites = [home]
    for path in DEFAULT_REMOTE_FAVORITES.get(profile_key, ()):
        cleaned = file_manager.clean_remote_path(path, home)
        if cleaned not in favorites:
            favorites.append(cleaned)
    return favorites


def stored_favorites(profile_key: str, home: str, raw: str) -> list[str]:
    try:
        values = json.loads(raw) if raw else []
    except json.JSONDecodeError:
        values = []
    favorites = default_favorites(profile_key, home)
    for value in values:
        path = file_manager.clean_remote_path(str(value), home)
        if path not in favorites:
            favorites.append(path)
    return favorites


def short_path_label(path: str) -> str:
    return path if len(path) <= 38 else "..." + path[-35:]
