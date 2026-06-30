from __future__ import annotations

from dog_remote_tool.core.profiles import ProductProfile
from dog_remote_tool.core.shell import remote_env, ssh_command
from dog_remote_tool.modules.localization.streams import (
    local_stream_cleanup,
    remote_python_stream,
    remote_stream_cleanup,
    remote_stream_shm_guard,
)


NAV_CAMERA_OVERLAY_MARKER = "dog_remote_tool_nav_camera_overlay_stream"


def navigation_camera_overlay_stream_command(profile: ProductProfile) -> str:
    source = r"""
import base64
import json
import math
import time

import rclpy
from nav_msgs.msg import Odometry, Path

try:
    import yaml
except Exception:
    yaml = None


CALIBRATION_PATH = "/ota/calibration_results.yaml"
IMAGE_WIDTH = 1920
IMAGE_HEIGHT = 1080
MAX_POINTS = 160
MIN_EMIT_INTERVAL = 0.05
PATH_MAX_AGE_SECONDS = 0.8
GLOBAL_PATH_MAX_AGE_SECONDS = 30.0
POSE_MAX_AGE_SECONDS = 1.0
GLOBAL_FORWARD_METERS = 4.0
GLOBAL_SIDE_METERS = 2.5
PATH_VISUAL_Z_OFFSET = 0.12

LOCAL_PATH_TOPICS = [
    "/navigo/cs/ppc/vis/received_global_plan",
]
GLOBAL_PATH_TOPIC = "/navigo/bn/cmn/vis/global_path"
POSE_TOPIC = "/odom/current_pose"

paths = {}
selected_priority = {}
pose = None
last_emit = 0.0
warned = set()


def matmul(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(len(b))) for j in range(len(b[0]))] for i in range(len(a))]


def matvec(m, v):
    return [sum(m[i][j] * v[j] for j in range(len(v))) for i in range(len(m))]


def inv4(m):
    r = [[m[i][j] for j in range(3)] for i in range(3)]
    t = [m[i][3] for i in range(3)]
    rt = [[r[j][i] for j in range(3)] for i in range(3)]
    inv_t = [-sum(rt[i][j] * t[j] for j in range(3)) for i in range(3)]
    return [
        [rt[0][0], rt[0][1], rt[0][2], inv_t[0]],
        [rt[1][0], rt[1][1], rt[1][2], inv_t[1]],
        [rt[2][0], rt[2][1], rt[2][2], inv_t[2]],
        [0.0, 0.0, 0.0, 1.0],
    ]


def transform_from_rt(entry):
    r = entry.get("R") or []
    t = entry.get("T") or []
    if len(r) != 3 or len(t) != 3:
        return None
    tv = [float(row[0] if isinstance(row, list) else row) for row in t]
    return [
        [float(r[0][0]), float(r[0][1]), float(r[0][2]), tv[0]],
        [float(r[1][0]), float(r[1][1]), float(r[1][2]), tv[1]],
        [float(r[2][0]), float(r[2][1]), float(r[2][2]), tv[2]],
        [0.0, 0.0, 0.0, 1.0],
    ]


def load_projection():
    if yaml is None:
        raise RuntimeError("python yaml is unavailable")
    with open(CALIBRATION_PATH, "r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    intrinsics = data.get("intrinsics", {}).get("camera_front", {})
    k = intrinsics.get("K") or data.get("/front_camera/image_compressed", {}).get("K")
    if not k:
        raise RuntimeError("front camera intrinsics missing")
    fx, fy = float(k[0][0]), float(k[1][1])
    cx, cy = float(k[0][2]), float(k[1][2])
    transforms = data.get("extrinsic_transforms", {})
    cam_to_lidar = transforms.get("camera_front_to_lidar_front")
    lidar_to_imu = transforms.get("lidar_front_to_imu_front")
    imu_to_base = transforms.get("imu_front_to_base")
    if cam_to_lidar and lidar_to_imu and imu_to_base:
        cam_to_base = matmul(matmul(imu_to_base, lidar_to_imu), cam_to_lidar)
    else:
        front_camera = transform_from_rt(data.get("/front_camera/image_compressed", {}))
        if front_camera is None:
            raise RuntimeError("front camera extrinsic missing")
        cam_to_base = front_camera
    base_to_cam = inv4(cam_to_base)
    return fx, fy, cx, cy, base_to_cam


try:
    FX, FY, CX, CY, BASE_TO_CAMERA = load_projection()
    print("NAV_CAMERA_OVERLAY=ready CALIBRATION=/ota/calibration_results.yaml", flush=True)
except Exception as exc:
    FX = FY = CX = CY = 0.0
    BASE_TO_CAMERA = None
    print(f"NAV_CAMERA_OVERLAY=error MESSAGE=calibration_failed:{exc}", flush=True)


def path_frame_id(msg):
    frame = str(getattr(msg.header, "frame_id", "") or "").strip()
    if frame:
        return frame
    for pose_stamped in msg.poses:
        frame = str(getattr(pose_stamped.header, "frame_id", "") or "").strip()
        if frame:
            return frame
    return "map"


def overlay_path_frame(kind, topic, msg):
    return path_frame_id(msg)


def on_path(kind, topic, priority, msg):
    count = len(msg.poses)
    if count <= 0:
        return
    current_priority = selected_priority.get(kind, 999)
    if priority > current_priority and time.monotonic() - paths.get(kind, {}).get("updated", 0.0) < 2.0:
        return
    selected_priority[kind] = priority
    paths[kind] = {
        "topic": topic,
        "frame": overlay_path_frame(kind, topic, msg),
        "poses": list(msg.poses),
        "updated": time.monotonic(),
    }
    maybe_emit()


def yaw_from_quaternion(q):
    return math.atan2(2.0 * (q.w * q.z + q.x * q.y), 1.0 - 2.0 * (q.y * q.y + q.z * q.z))


def on_pose(msg):
    global pose
    p = msg.pose.pose.position
    q = msg.pose.pose.orientation
    pose = {
        "frame": str(getattr(msg.header, "frame_id", "") or "").strip(),
        "x": float(p.x),
        "y": float(p.y),
        "yaw": yaw_from_quaternion(q),
        "updated": time.monotonic(),
    }
    maybe_emit()


def map_point_to_base(point):
    if pose is None or time.monotonic() - pose.get("updated", 0.0) > POSE_MAX_AGE_SECONDS:
        return None
    dx = float(point.x) - pose["x"]
    dy = float(point.y) - pose["y"]
    yaw = pose["yaw"]
    c = math.cos(yaw)
    s = math.sin(yaw)
    bx = c * dx + s * dy
    by = -s * dx + c * dy
    return (bx, by, float(getattr(point, "z", 0.0)))


def path_point_to_base(frame, point):
    x = float(point.x)
    y = float(point.y)
    z = float(getattr(point, "z", 0.0))
    frame = (frame or "map").strip()
    if frame in {"base_link", "base_link_rviz"}:
        return (x, y, z)
    if frame == "map":
        return map_point_to_base(point)
    if frame not in warned:
        warned.add(frame)
        print(f"NAV_CAMERA_OVERLAY=warn MESSAGE=unsupported_frame:{frame}", flush=True)
    return None


def project_base_point(point):
    if BASE_TO_CAMERA is None:
        return None
    bx, by, bz = point
    cx, cy, cz, _ = matvec(BASE_TO_CAMERA, [bx, by, bz + PATH_VISUAL_Z_OFFSET, 1.0])
    if cz <= 0.05:
        return None
    u = FX * (cx / cz) + CX
    v = FY * (cy / cz) + CY
    # Near-field ground points often project just outside the image. Keep a
    # broad margin and let OpenCV clip the polyline without changing its shape.
    margin = max(IMAGE_WIDTH, IMAGE_HEIGHT) * 2
    if u < -margin or u > IMAGE_WIDTH + margin or v < -margin or v > IMAGE_HEIGHT + margin:
        return None
    return [round(float(u), 1), round(float(v), 1)]


def keep_global_base_point(point):
    bx, by, _ = point
    return -0.2 <= bx <= GLOBAL_FORWARD_METERS and abs(by) <= GLOBAL_SIDE_METERS


def compact_poses(poses):
    if len(poses) <= MAX_POINTS:
        return poses
    step = max(1, math.ceil(len(poses) / MAX_POINTS))
    compact = poses[::step]
    if compact[-1] is not poses[-1]:
        compact.append(poses[-1])
    return compact


def project_path(kind):
    entry = paths.get(kind)
    if not entry:
        return []
    max_age = GLOBAL_PATH_MAX_AGE_SECONDS if kind == "global" else PATH_MAX_AGE_SECONDS
    if time.monotonic() - entry.get("updated", 0.0) > max_age:
        return []
    pts = []
    for pose_stamped in compact_poses(entry["poses"]):
        base_point = path_point_to_base(entry["frame"], pose_stamped.pose.position)
        if base_point is None:
            continue
        if kind == "global" and not keep_global_base_point(base_point):
            continue
        pixel = project_base_point(base_point)
        if pixel is not None:
            pts.append(pixel)
    return pts


def maybe_emit():
    global last_emit
    now = time.monotonic()
    if now - last_emit < MIN_EMIT_INTERVAL:
        return
    last_emit = now
    if BASE_TO_CAMERA is None:
        return
    payload = {
        "stamp": time.time(),
        "width": IMAGE_WIDTH,
        "height": IMAGE_HEIGHT,
        "global": project_path("global"),
        "local": project_path("local"),
        "global_topic": paths.get("global", {}).get("topic", ""),
        "local_topic": paths.get("local", {}).get("topic", ""),
        "global_age_ms": round((now - paths.get("global", {}).get("updated", now)) * 1000, 1),
        "local_age_ms": round((now - paths.get("local", {}).get("updated", now)) * 1000, 1),
    }
    encoded = base64.b64encode(json.dumps(payload, separators=(",", ":")).encode("utf-8")).decode("ascii")
    print(f"NAV_CAMERA_OVERLAY_JSON={encoded}", flush=True)


node = None
try:
    rclpy.init()
    node = rclpy.create_node("dog_remote_tool_nav_camera_overlay_stream")
    node.create_subscription(Odometry, POSE_TOPIC, on_pose, 10)
    node.create_subscription(Path, GLOBAL_PATH_TOPIC, lambda msg: on_path("global", GLOBAL_PATH_TOPIC, 0, msg), 10)
    for priority, topic in enumerate(LOCAL_PATH_TOPICS):
        node.create_subscription(Path, topic, lambda msg, t=topic, p=priority: on_path("local", t, p, msg), 10)
    rclpy.spin(node)
except Exception as exc:
    print(f"NAV_CAMERA_OVERLAY=ros_error MESSAGE={exc}", flush=True)
finally:
    if node is not None:
        node.destroy_node()
    if rclpy.ok():
        rclpy.shutdown()
""".strip()
    inner = (
        f"{remote_env(profile)}; "
        f"{remote_stream_cleanup(NAV_CAMERA_OVERLAY_MARKER)}"
        f"{remote_stream_shm_guard(NAV_CAMERA_OVERLAY_MARKER)}"
        "source /opt/runtime/env.bash >/dev/null 2>&1 || true; "
        "source /opt/robot/robot_nav/install/setup.bash >/dev/null 2>&1 || true; "
        "source /opt/robot/robot_slam/install/setup.bash >/dev/null 2>&1 || true; "
        f"{remote_python_stream(NAV_CAMERA_OVERLAY_MARKER, source)}"
    )
    return local_stream_cleanup(NAV_CAMERA_OVERLAY_MARKER) + ssh_command(profile, inner)
