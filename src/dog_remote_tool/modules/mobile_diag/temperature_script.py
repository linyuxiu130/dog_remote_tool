from __future__ import annotations

from dog_remote_tool.core.shell import quote


def temperature_probe_script(
    prefix: str, source_label: str, include_joints: bool, ros_domain_id: str, rmw: str
) -> str:
    python_source = f"""
import mmap
import os
import struct
import time

PREFIX = {prefix!r}
SOURCE_LABEL = {source_label!r}
INCLUDE_JOINTS = {include_joints!r}
SHM_PATH = "/dev/shm/spline_shm"
LEG_KEYS = ["RF", "LF", "RR", "LR"]
JOINT_KEYS = ["ABAD", "HIP", "KNEE"]
TOPIC_TO_GRID = {{
    "fr1_hip_roll": ("RF", "ABAD"),
    "fr2_hip_pitch": ("RF", "HIP"),
    "fr3_knee_pitch": ("RF", "KNEE"),
    "fl1_hip_roll": ("LF", "ABAD"),
    "fl2_hip_pitch": ("LF", "HIP"),
    "fl3_knee_pitch": ("LF", "KNEE"),
    "br1_hip_roll": ("RR", "ABAD"),
    "br2_hip_pitch": ("RR", "HIP"),
    "br3_knee_pitch": ("RR", "KNEE"),
    "bl1_hip_roll": ("LR", "ABAD"),
    "bl2_hip_pitch": ("LR", "HIP"),
    "bl3_knee_pitch": ("LR", "KNEE"),
}}

CMD_SIZE = 4 * (4 * 5 * 4 + 4) + 2 * 4
STATE_OFFSET = CMD_SIZE
JOINT_SIZE = 4 + 3 * 4


def emit(key, value):
    print(f"{{key}}={{value}}")


def read_thermals():
    data = {{}}
    root = "/sys/class/thermal"
    try:
        names = os.listdir(root)
    except OSError:
        return data
    for name in names:
        path = os.path.join(root, name)
        try:
            with open(os.path.join(path, "type"), encoding="utf-8") as f:
                typ = f.read().strip()
            with open(os.path.join(path, "temp"), encoding="utf-8") as f:
                data[typ] = int(f.read().strip()) / 1000
        except (OSError, ValueError):
            pass
    return data


def pick_temp(data, *names):
    for name in names:
        if name in data:
            return f"{{data[name]:.1f}}"
    return "--"


def read_joint(mm, leg_index, joint_index):
    off = STATE_OFFSET + leg_index * (4 * JOINT_SIZE) + joint_index * JOINT_SIZE
    flags, _, _, _ = struct.unpack_from("<ifff", mm, off)
    enabled = bool(flags & 0x1)
    over_temp = bool(flags & (1 << 3))
    temp = (flags >> 8) & 0xFF
    return enabled, over_temp, temp


def emit_joint_values(joints, source):
    max_temp = -1.0
    max_name = "--"
    for leg in LEG_KEYS:
        for joint in JOINT_KEYS:
            value = joints.get((leg, joint))
            key = f"JOINT_{{leg}}_{{joint}}"
            if value is None:
                emit(f"{{key}}_ENABLED", "0")
                emit(f"{{key}}_TEMP", "--")
                emit(f"{{key}}_OVER_TEMP", "0")
                continue
            temp, over_temp = value
            emit(f"{{key}}_ENABLED", "1")
            emit(f"{{key}}_TEMP", f"{{temp:.1f}}")
            emit(f"{{key}}_OVER_TEMP", "1" if over_temp else "0")
            if temp > max_temp:
                max_temp = temp
                max_name = f"{{leg}} {{joint}}"
    emit("JOINT_AVAILABLE", "1")
    emit("JOINT_SOURCE", source)
    emit("JOINT_MAX_TEMP", f"{{max_temp:.1f}}" if max_temp >= 0 else "--")
    emit("JOINT_MAX_NAME", max_name)


def read_joint_from_ros():
    try:
        import rclpy
        from robot_common_interface.msg import JointSensor
    except Exception:
        return None
    joints = {{}}
    rclpy.init(args=None)
    node = rclpy.create_node("dog_remote_joint_temp_probe")
    box = {{}}

    def cb(msg):
        box["msg"] = msg

    node.create_subscription(JointSensor, "/joint_shm_controller/joint_sensor", cb, 10)
    deadline = time.monotonic() + 3.0
    while "msg" not in box and time.monotonic() < deadline:
        rclpy.spin_once(node, timeout_sec=0.2)
    msg = box.get("msg")
    node.destroy_node()
    rclpy.shutdown()
    if msg is None:
        return None
    for name, temp in zip(msg.name, msg.temp):
        grid_key = TOPIC_TO_GRID.get(name)
        if grid_key is not None:
            joints[grid_key] = (float(temp), False)
    return joints if joints else None


def read_joint_from_spline_shm():
    if not os.path.exists(SHM_PATH):
        return None
    joints = {{}}
    with open(SHM_PATH, "rb") as f:
        mm = mmap.mmap(f.fileno(), 1024 * 10, access=mmap.ACCESS_READ)
        for leg_index, leg in enumerate(LEG_KEYS):
            for joint_index, joint in enumerate(JOINT_KEYS):
                enabled, over_temp, temp = read_joint(mm, leg_index, joint_index)
                if enabled:
                    joints[(leg, joint)] = (float(temp), over_temp)
    return joints if joints else None


print(f"{{PREFIX}}_TEMP_BEGIN")
emit(f"{{PREFIX}}_TEMP_SOURCE", SOURCE_LABEL)
thermals = read_thermals()
emit(f"{{PREFIX}}_TEMP_MAIN", pick_temp(thermals, "soc-thermal", "cpu-thermal", "tj-thermal"))
emit(f"{{PREFIX}}_TEMP_GPU", pick_temp(thermals, "gpu-thermal"))

if INCLUDE_JOINTS:
    try:
        joints = read_joint_from_ros()
        if joints is not None:
            emit_joint_values(joints, "joint_sensor")
        else:
            joints = read_joint_from_spline_shm()
            if joints is not None:
                emit_joint_values(joints, "spline_shm")
            else:
                emit("JOINT_AVAILABLE", "0")
                emit("JOINT_ERROR", "未收到 joint_sensor，且 spline_shm 不存在")
    except Exception as exc:
        emit("JOINT_AVAILABLE", "0")
        emit("JOINT_ERROR", str(exc))
print(f"{{PREFIX}}_TEMP_END")
"""
    return (
        "source /opt/ros/humble/setup.bash >/dev/null 2>&1 || true\n"
        "source /opt/robot/install/setup.bash >/dev/null 2>&1 || true\n"
        f"export ROS_DOMAIN_ID={quote(ros_domain_id)}\n"
        f"export RMW_IMPLEMENTATION={quote(rmw)}\n"
        f"python3 - <<'PY'\n{python_source}\nPY\n"
    )
