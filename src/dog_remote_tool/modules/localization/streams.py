from __future__ import annotations

from dog_remote_tool.core.profiles import ProductProfile
from dog_remote_tool.core.shell import quote, remote_env, ssh_command


def local_stream_cleanup(marker: str) -> str:
    awk_script = (
        '$1 != self && index($0, marker) && '
        '(($2 ~ /(^|\\/)ssh(pass)?$/) || ($2 ~ /(^|\\/)python3$/ && $3 == "-u" && $4 == "-")) {print $1}'
    )
    return (
        "ps -eo pid=,args= 2>/dev/null | "
        f"awk -v self=$$ -v marker={quote(marker)} {quote(awk_script)} | "
        "xargs -r kill 2>/dev/null || true; "
    )


def remote_stream_cleanup(marker: str) -> str:
    script_path = f"/tmp/{marker}.py"
    awk_script = (
        '$1 != self && index($0, script_path) && '
        '($2 ~ /(^|\\/)python3$/ && $3 == "-u") {print $1}'
    )
    return (
        "ps -eo pid=,args= 2>/dev/null | "
        f"awk -v self=$$ -v script_path={quote(script_path)} {quote(awk_script)} | "
        "xargs -r kill 2>/dev/null || true; "
    )


def remote_stream_shm_guard(marker: str, max_used_percent: int = 95) -> str:
    return (
        "SHM_USED_PERCENT=$(df -P /dev/shm 2>/dev/null | awk 'NR==2 {gsub(/%/, \"\", $5); print $5}'); "
        f"if [ -n \"$SHM_USED_PERCENT\" ] && [ \"$SHM_USED_PERCENT\" -ge {max_used_percent} ]; then "
        f"echo 'STREAM=shm_guard MARKER={marker} USED_PERCENT='\"$SHM_USED_PERCENT\"' MAX_PERCENT={max_used_percent}'; "
        "exit 80; "
        "fi; "
    )


def remote_python_stream(marker: str, source: str) -> str:
    script_path = f"/tmp/{marker}.py"
    return (
        f"STREAM_SCRIPT={quote(script_path)}; "
        f"printf '%s' {quote(source)} > \"$STREAM_SCRIPT\"; "
        "chmod +x \"$STREAM_SCRIPT\"; "
        "exec python3 -u \"$STREAM_SCRIPT\""
    )


def pose_stream_command(profile: ProductProfile) -> str:
    source = """
import math
import time
import rclpy
from nav_msgs.msg import Odometry

last_emit = 0.0
min_interval = 0.25


def callback(msg):
    global last_emit
    now = time.monotonic()
    if now - last_emit < min_interval:
        return
    last_emit = now
    p = msg.pose.pose.position
    q = msg.pose.pose.orientation
    yaw = math.atan2(2 * (q.w * q.z + q.x * q.y), 1 - 2 * (q.y * q.y + q.z * q.z))
    print(f"POSE=ok X={p.x:.9f} Y={p.y:.9f} YAW={yaw:.9f}", flush=True)


node = None
try:
    rclpy.init()
    node = rclpy.create_node("dog_remote_tool_pose_stream")
    node.create_subscription(Odometry, "/odom/current_pose", callback, 10)
    rclpy.spin(node)
except Exception as exc:
    print(f"STREAM=ros_error MARKER=dog_remote_tool_pose_stream ERROR={exc}", flush=True)
finally:
    if node is not None:
        node.destroy_node()
    if rclpy.ok():
        rclpy.shutdown()
""".strip()
    inner = (
        f"{remote_env(profile)}; "
        f"{remote_stream_cleanup('dog_remote_tool_pose_stream')}"
        f"{remote_stream_shm_guard('dog_remote_tool_pose_stream')}"
        "source /opt/runtime/env.bash >/dev/null 2>&1 || true; "
        "source /opt/robot/robot_slam/install/setup.bash >/dev/null 2>&1; "
        f"{remote_python_stream('dog_remote_tool_pose_stream', source)}"
    )
    return local_stream_cleanup("dog_remote_tool_pose_stream") + ssh_command(profile, inner)


def navigation_plan_stream_command(profile: ProductProfile) -> str:
    source = """
import math
import time
import rclpy
from nav_msgs.msg import Path

TOPICS = {
    "GLOBAL": [
        "/navigo/bn/cmn/vis/global_path",
        "/rv/trajectory/global",
        "/navigo/ps/cmn/vis/planned_path",
    ],
}
last_emit = {}
selected_priority = {}
selected_at = {}
min_interval = 0.20
max_points = 360


def yaw_from_quat(q):
    return math.atan2(2 * (q.w * q.z + q.x * q.y), 1 - 2 * (q.y * q.y + q.z * q.z))


def compact_path(msg):
    poses = list(msg.poses)
    if len(poses) > max_points:
        step = max(1, math.ceil(len(poses) / max_points))
        poses = poses[::step]
        if poses[-1] is not msg.poses[-1]:
            poses.append(msg.poses[-1])
    parts = []
    for pose_stamped in poses:
        p = pose_stamped.pose.position
        q = pose_stamped.pose.orientation
        parts.append(f"{p.x:.3f},{p.y:.3f},{yaw_from_quat(q):.3f}")
    return ";".join(parts)


def callback(kind, topic, priority, msg):
    now = time.monotonic()
    count = len(msg.poses)
    if count <= 0:
        return
    current_priority = selected_priority.get(kind, 999)
    current_age = now - selected_at.get(kind, 0.0)
    if priority > current_priority and current_age < 2.0:
        return
    key = (kind, topic)
    if now - last_emit.get(key, 0.0) < min_interval:
        return
    selected_priority[kind] = priority
    selected_at[kind] = now
    last_emit[key] = now
    print(f"PLAN={kind} TOPIC={topic} COUNT={count} POINTS={compact_path(msg)}", flush=True)


node = None
try:
    rclpy.init()
    node = rclpy.create_node("dog_remote_tool_plan_stream")
    for kind, topics in TOPICS.items():
        for priority, topic in enumerate(topics):
            node.create_subscription(Path, topic, lambda msg, k=kind, t=topic, p=priority: callback(k, t, p, msg), 10)
    rclpy.spin(node)
except Exception as exc:
    print(f"STREAM=ros_error MARKER=dog_remote_tool_plan_stream ERROR={exc}", flush=True)
finally:
    if node is not None:
        node.destroy_node()
    if rclpy.ok():
        rclpy.shutdown()
""".strip()
    inner = (
        f"{remote_env(profile)}; "
        f"{remote_stream_cleanup('dog_remote_tool_plan_stream')}"
        f"{remote_stream_shm_guard('dog_remote_tool_plan_stream')}"
        "source /opt/runtime/env.bash >/dev/null 2>&1 || true; "
        "source /opt/robot/robot_nav/install/setup.bash >/dev/null 2>&1 || true; "
        f"{remote_python_stream('dog_remote_tool_plan_stream', source)}"
    )
    return local_stream_cleanup("dog_remote_tool_plan_stream") + ssh_command(profile, inner)


def obstacle_stream_command(profile: ProductProfile) -> str:
    source = """
import math
import time

import rclpy
from nav_msgs.msg import Odometry
from sensor_msgs.msg import LaserScan


TOPIC = "/laser_scan"
last_emit = {}
selected_priority = 999
selected_at = 0.0
last_pose = None
min_interval = 0.12
max_points = 480
max_range_m = 8.0
min_range_m = 0.05


def yaw_from_quat(q):
    return math.atan2(2 * (q.w * q.z + q.x * q.y), 1 - 2 * (q.y * q.y + q.z * q.z))


def pose_callback(msg):
    global last_pose
    p = msg.pose.pose.position
    last_pose = (float(p.x), float(p.y), yaw_from_quat(msg.pose.pose.orientation), time.monotonic())


def to_world(points):
    if last_pose is None:
        return []
    pose_x, pose_y, yaw, pose_at = last_pose
    if time.monotonic() - pose_at > 2.0:
        return []
    cos_yaw = math.cos(yaw)
    sin_yaw = math.sin(yaw)
    world = []
    for x, y in points:
        world.append((pose_x + cos_yaw * x - sin_yaw * y, pose_y + sin_yaw * x + cos_yaw * y))
    return world


def compact_points(points):
    if len(points) > max_points:
        step = max(1, math.ceil(len(points) / max_points))
        points = points[::step][:max_points]
    return ";".join(f"{x:.3f},{y:.3f}" for x, y in points)


def emit(points):
    global selected_priority, selected_at
    now = time.monotonic()
    if now - last_emit.get(TOPIC, 0.0) < min_interval:
        return
    world = to_world(points)
    if not world:
        return
    selected_priority = 0
    selected_at = now
    last_emit[TOPIC] = now
    print(f"OBS=ok TOPIC={TOPIC} FRAME=map COUNT={len(world)} POINTS={compact_points(world)}", flush=True)


def scan_callback(msg):
    points = []
    angle = float(msg.angle_min)
    for value in msg.ranges:
        distance = float(value)
        if math.isfinite(distance) and min_range_m <= distance <= max_range_m:
            points.append((distance * math.cos(angle), distance * math.sin(angle)))
        angle += float(msg.angle_increment)
    emit(points)


node = None
try:
    rclpy.init()
    node = rclpy.create_node("dog_remote_tool_obstacle_stream")
    node.create_subscription(Odometry, "/odom/current_pose", pose_callback, 10)
    node.create_subscription(LaserScan, TOPIC, scan_callback, 10)
    rclpy.spin(node)
except Exception as exc:
    print(f"STREAM=ros_error MARKER=dog_remote_tool_obstacle_stream ERROR={exc}", flush=True)
finally:
    if node is not None:
        node.destroy_node()
    if rclpy.ok():
        rclpy.shutdown()
""".strip()
    inner = (
        f"{remote_env(profile)}; "
        f"{remote_stream_cleanup('dog_remote_tool_obstacle_stream')}"
        f"{remote_stream_shm_guard('dog_remote_tool_obstacle_stream')}"
        "source /opt/runtime/env.bash >/dev/null 2>&1 || true; "
        "source /opt/robot/robot_slam/install/setup.bash >/dev/null 2>&1 || true; "
        "source /opt/robot/robot_nav/install/setup.bash >/dev/null 2>&1 || true; "
        f"{remote_python_stream('dog_remote_tool_obstacle_stream', source)}"
    )
    return local_stream_cleanup("dog_remote_tool_obstacle_stream") + ssh_command(profile, inner)
