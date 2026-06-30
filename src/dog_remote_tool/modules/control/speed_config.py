from __future__ import annotations


NAV_CONFIG_CANDIDATES = {
    "xg1_nx": [
        "/opt/robot/robot_nav/install/robot_nav2/share/robot_nav2/params/XG/nav2_params.yaml",
        "/opt/robot/robot_nav/install/robot_nav2/share/robot_nav2/params/XGW/nav2_params.yaml",
    ],
    "zg_lidar_nx": [
        "/opt/robot/robot_nav/install/robot_nav2/share/robot_nav2/params/ZGW/nav2_params.yaml",
        "/opt/robot/robot_nav/install/robot_nav2/share/robot_nav2/params/ZG/nav2_params.yaml",
    ],
}
L2_REMOTE_CONFIG = "/opt/robot/install/robot_remote/share/robot_remote/config/remote_config.yaml"


def clamp_nav_speed(speed: float) -> float:
    return max(0.05, min(float(speed), 3.0))
