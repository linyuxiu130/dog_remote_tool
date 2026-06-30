from __future__ import annotations

from dataclasses import dataclass

from dog_remote_tool.core.parsers import parse_key_values
from dog_remote_tool.core.profiles import ProductProfile
from dog_remote_tool.core.shell import quote, remote_env, ssh_command
import dog_remote_tool.modules.localization.alg as _localization_alg


@dataclass(frozen=True)
class CurrentPose:
    x: float
    y: float
    yaw: float | None = None


def current_pose_command(profile: ProductProfile) -> str:
    reader = """
import math
import sys
import time

try:
    import rclpy
    from nav_msgs.msg import Odometry
except Exception as exc:
    print("POSE=ros_error")
    print(f"ERROR={type(exc).__name__}: {exc}")
    raise SystemExit(5)

pose = {"seen": False, "x": 0.0, "y": 0.0, "yaw": 0.0}


def emit_pose():
    print("POSE=ok")
    print(f"X={pose['x']:.12g}")
    print(f"Y={pose['y']:.12g}")
    print(f"YAW={pose['yaw']:.12g}")


def on_pose(msg):
    position = msg.pose.pose.position
    orientation = msg.pose.pose.orientation
    yaw = math.atan2(
        2.0 * (orientation.w * orientation.z + orientation.x * orientation.y),
        1.0 - 2.0 * (orientation.y * orientation.y + orientation.z * orientation.z),
    )
    if all(math.isfinite(value) for value in (position.x, position.y, yaw)):
        pose.update(seen=True, x=float(position.x), y=float(position.y), yaw=float(yaw))


try:
    rclpy.init()
    node = rclpy.create_node("dog_remote_current_pose_reader")
    node.create_subscription(Odometry, "/odom/current_pose", on_pose, 10)

    deadline = time.monotonic() + 4.0
    while time.monotonic() < deadline:
        rclpy.spin_once(node, timeout_sec=0.1)
        if pose["seen"]:
            emit_pose()
            raise SystemExit(0)

    print("POSE=unavailable")
    raise SystemExit(2)
except SystemExit:
    raise
except Exception as exc:
    print("POSE=ros_error")
    print(f"ERROR={type(exc).__name__}: {exc}")
    raise SystemExit(5)
finally:
    try:
        node.destroy_node()
    except Exception:
        pass
    try:
        if rclpy.ok():
            rclpy.shutdown()
    except Exception:
        pass
""".strip()
    inner = (
        f"{remote_env(profile)}; "
        "source /opt/runtime/env.bash >/dev/null 2>&1 || true; "
        "source /opt/robot/robot_slam/install/setup.bash >/dev/null 2>&1 || true; "
        f"ALG_LOC_OUTPUT=$({_localization_alg.alg_loc_status_inner()} || true); "
        "printf '%s\\n' \"$ALG_LOC_OUTPUT\"; "
        "ALG_LOC_VALUE=$(printf '%s\\n' \"$ALG_LOC_OUTPUT\" | awk -F= '/^ALG_LOC_STATUS=/ {value=$2} END {print value}'); "
        "case \"$ALG_LOC_VALUE\" in ContinuousLoc|continuousloc|LocOk|InitLocOk) ;; "
        "*) echo POSE=localization_not_ready; echo '[ERROR] 定位状态未就绪，不能按当前车位置添加节点。'; "
        "echo LOCALIZATION_TOPIC=alg:get_loc_status; echo LOCALIZATION_CODE=${ALG_LOC_VALUE:-}; exit 4 ;; "
        "esac; "
        f"timeout 7s python3 -c {quote(reader)}"
    )
    return ssh_command(profile, inner)


def parse_current_pose_output(output: str) -> CurrentPose | None:
    values = parse_key_values(output)
    if values.get("POSE") != "ok":
        return None
    try:
        yaw = float(values["YAW"]) if values.get("YAW") else None
        return CurrentPose(float(values["X"]), float(values["Y"]), yaw)
    except (KeyError, ValueError):
        return None


def current_pose_failure_message(output: str, exit_code: int = 0) -> str:
    values = parse_key_values(output)
    pose_state = values.get("POSE", "")
    if pose_state == "ros_error":
        error = values.get("ERROR", "ROS 2 topic 查询失败")
        return (
            "当前无法按车身位置加点。\n\n"
            f"原因：ROS 2 / zenoh 通信初始化失败。\n{error}\n\n"
            "请先刷新远端状态，必要时重启相关 ROS/管理节点后再试。"
        )
    if pose_state == "localization_not_ready" or exit_code == 4:
        return (
            "当前无法按车身位置加点。\n\n"
            "原因：定位状态未就绪。\n\n"
            "请先确认导航页/定位页显示连续定位正常。"
        )
    if pose_state == "unavailable" or exit_code == 2:
        return (
            "当前无法按车身位置加点。\n\n"
            "原因：未从 /odom/current_pose 读取到有效 x/y。\n\n"
            "请确认 /odom/current_pose 正在发布当前位置。"
        )
    return (
        "当前无法按车身位置加点。\n\n"
        "原因：未读取到有效当前位置。\n\n"
        "请确认持续定位已启动，并且 /odom/current_pose 正在发布。"
    )
