from __future__ import annotations

import os
from pathlib import Path

from dog_remote_tool.core.profiles import ProductProfile
from dog_remote_tool.core.shell import CommandSpec, quote


def default_visualizer_root() -> str:
    env_root = os.environ.get("DOG_REMOTE_TOOL_VISUALIZER_ROOT")
    if env_root:
        return str(Path(env_root).expanduser())
    return str(Path.home() / "dog_remote_tool_visualizer")


VISUALIZER_ROOT = default_visualizer_root()


def online_command(profile: ProductProfile) -> CommandSpec:
    cmd = (
        "export ROS_DOMAIN_ID=24; export RMW_IMPLEMENTATION=rmw_zenoh_cpp; "
        "export ROS_LOCALHOST_ONLY=0; source /opt/ros/humble/setup.bash; "
        f"bash {quote(VISUALIZER_ROOT + '/start_l2_zenoh_router.sh')} || true; "
        "rviz2"
    )
    return CommandSpec("启动在线可视化", cmd, concurrency="parallel", locks=("local:visualizer:online",))


def replay_command() -> CommandSpec:
    return CommandSpec("启动 Bag 回放可视化", f"bash {quote(VISUALIZER_ROOT + '/bag_view.sh')}", concurrency="parallel", locks=("local:visualizer:bag",))


def tf_command() -> CommandSpec:
    cmd = (
        "source /opt/ros/humble/setup.bash; "
        "ros2 run tf2_ros static_transform_publisher 0 0 0 0 0 0 base_link livox_frame"
    )
    return CommandSpec("发布 Livox TF", cmd, concurrency="parallel", locks=("local:tf:livox",))
