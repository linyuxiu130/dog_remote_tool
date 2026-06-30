from __future__ import annotations

from dog_remote_tool.core.profiles import ProductProfile
from dog_remote_tool.core.shell import CommandSpec, quote, remote_env, ssh_command


SENSOR_TOPICS = [
    "/front_stereo_camera/image_compressed",
    "/rear_stereo_camera/image_compressed",
    "/front_fisheye/image_compressed",
    "/rear_fisheye/image_compressed",
    "/left_fisheye/image_compressed",
    "/right_fisheye/image_compressed",
    "/front_lidar",
    "/rear_lidar",
    "/front_lidar/imu",
    "/rear_lidar/imu",
]


def basic_check_command(profile: ProductProfile) -> CommandSpec:
    checks = " ".join(quote(topic) for topic in SENSOR_TOPICS)
    inner = (
        f"{remote_env(profile)}; "
        "echo 'ROS_DOMAIN_ID='$ROS_DOMAIN_ID; "
        "echo 'RMW_IMPLEMENTATION='$RMW_IMPLEMENTATION; "
        "ros2 node list --no-daemon | head -80; "
        f"for t in {checks}; do echo ===$t===; ros2 topic hz $t -w 5 --once || true; done"
    )
    return CommandSpec("传感器基础检查", ssh_command(profile, inner), concurrency="parallel")


def long_run_command(profile: ProductProfile, minutes: int) -> CommandSpec:
    topic_args = " ".join(quote(topic) for topic in SENSOR_TOPICS)
    seconds = max(1, minutes) * 60
    inner = (
        f"{remote_env(profile)}; "
        f"timeout {seconds}s bash -lc 'for t in {topic_args}; do echo ===$t===; timeout 12s ros2 topic hz $t -w 20 || true; done'"
    )
    return CommandSpec("传感器短时长稳", ssh_command(profile, inner), concurrency="parallel")
