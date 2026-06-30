from __future__ import annotations

from dog_remote_tool.core.profiles import ProductProfile
from dog_remote_tool.core.shell import CommandSpec, echo_message, quote, remote_env, ssh_command
from dog_remote_tool.modules.arc_app_ws import common_arc_app_ws_python
from dog_remote_tool.modules.navigation import payloads as _payloads


def _arc_marking_app_ws_python() -> str:
    return common_arc_app_ws_python() + r'''
import re
import subprocess

MAP_ID = sys.argv[1]
MAP_PREFIX = sys.argv[2]
MAP_YAML = sys.argv[3]
TAG_ID = int(sys.argv[4])
MONITOR_SECONDS = int(sys.argv[5])
ARC_MAPPING_SERVICE = "/arc_mapping_service"


def run_ros(args, timeout=5):
    result = subprocess.run(
        args,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout,
        check=False,
    )
    return result.stdout


def topic_once(topic, *, best_effort=False, timeout=2):
    args = ["timeout", f"{timeout}s", "ros2", "topic", "echo"]
    if best_effort:
        args += ["--qos-reliability", "best_effort"]
    args += ["--once", topic, "--no-daemon"]
    try:
        return run_ros(args, timeout=timeout + 2)
    except subprocess.TimeoutExpired:
        return ""


def extract_scalar(text, name):
    match = re.search(rf"^{re.escape(name)}:\s*([^'\n]+)", text, re.MULTILINE)
    return "" if not match else match.group(1).strip()


def extract_position(text):
    match = re.search(
        r"(?:current_pose|pose):\s*\n\s*position:\s*\n\s*x:\s*([^\n]+)\n\s*y:\s*([^\n]+)",
        text,
    )
    if not match:
        match = re.search(r"position:\s*\n\s*x:\s*([^\n]+)\n\s*y:\s*([^\n]+)", text)
    if not match:
        return "", ""
    return match.group(1).strip(), match.group(2).strip()


def read_arc_fields():
    try:
        text = open(MAP_YAML, "r", encoding="utf-8", errors="replace").read()
    except OSError:
        return "", False
    lines = [
        f"{index}:{line}"
        for index, line in enumerate(text.splitlines(), 1)
        if "arc_position_flag" in line or line.lstrip().startswith("arc:")
    ]
    ready = bool(re.search(r"arc_position_flag:\s*(1|true|True)\b", text)) and "arc_position" in text
    return "\n".join(lines), ready


def map_mtime():
    try:
        return os.path.getmtime(MAP_YAML)
    except OSError:
        return 0.0


def ensure_arc_mapping_service():
    services = run_ros(["timeout", "5s", "ros2", "service", "list", "--no-daemon"], timeout=7)
    if ARC_MAPPING_SERVICE not in services.splitlines():
        print("[ERROR] /arc_mapping_service 未就绪，无法标记充电桩。", flush=True)
        raise SystemExit(3)
    print(f"[INFO] 使用服务: {ARC_MAPPING_SERVICE}", flush=True)


def call_map_state(data):
    payload = (
        "{mapping_type: 1, "
        f"arc_id: {TAG_ID}, "
        f"map_path_prefix: '{MAP_PREFIX}', "
        f"data: {data}" + "}"
    )
    labels = {0: "初始化", 3: "激活检测", 5: "保存桩位"}
    print(f"[INFO] ARC mapping {labels.get(data, '请求')}: data={data}", flush=True)
    output = run_ros(
        ["timeout", "30s", "ros2", "service", "call", ARC_MAPPING_SERVICE, "robots_dog_msgs/srv/MapState", payload],
        timeout=35,
    )
    if "success=True" not in output:
        print(output.strip(), flush=True)
        return False, output
    message = re.search(r"message='([^']*)'", output)
    if message:
        print(f"[INFO] ARC mapping 服务成功: {message.group(1)}", flush=True)
    else:
        print("[INFO] ARC mapping 服务成功", flush=True)
    return True, output


def ensure_localization():
    sock = connect_ws()
    try:
        load_map_until_localized(sock, 1, MAP_ID, "继续标记充电桩")
    finally:
        try:
            sock.close()
        except Exception:
            pass


def start_perception():
    info = run_ros(["timeout", "3s", "ros2", "topic", "info", "/arc/perception_mode_cmd"], timeout=5)
    sub_match = re.search(r"Subscription count:\s*(\d+)", info)
    subscribers = int(sub_match.group(1)) if sub_match else 0
    if subscribers < 1:
        print("[ERROR] /arc/perception_mode_cmd 没有订阅者，apriltag 感知节点可能未运行。", flush=True)
        raise SystemExit(3)

    payload = (
        "{stamp: {sec: 0, nanosec: 0}, "
        f"tag_id: {TAG_ID}, "
        "mode: 1, "
        "target_pose: {stamp: {sec: 0, nanosec: 0}, "
        "x: 0.0, y: 0.0, z: 0.0, yaw: 0.0, pitch: 0.0, roll: 0.0, "
        "x_tol: 0.0, y_tol: 0.0, z_tol: 0.0, yaw_tol: 0.0, pitch_tol: 0.0, roll_tol: 0.0}, "
        "multi_stage_ctrl_cmd: {enable: false, rollback_enabled: false, rollback_x_threshold: 0.0}}"
    )
    print(f"[INFO] 启动 ARC 感知: /arc/perception_mode_cmd RUNNING tag_id={TAG_ID}", flush=True)
    output = run_ros(
        ["timeout", "8s", "ros2", "topic", "pub", "--once", "/arc/perception_mode_cmd", "robots_dog_msgs/msg/ArcModuleCmd", payload],
        timeout=10,
    )
    if "publishing #1" not in output:
        print(output.strip(), flush=True)
    print("[INFO] ARC 感知 RUNNING 指令已发送。", flush=True)

    running = False
    pose_ready = False
    last_snapshot = None
    for _ in range(30):
        state_msg = topic_once("/arc/perception_state", best_effort=True, timeout=2)
        pose_msg = topic_once("/arc/perception_dock_pose", best_effort=True, timeout=2)
        state = extract_scalar(state_msg, "state")
        px, py = extract_position(pose_msg)
        snapshot = f"state={state or '无'} pose={px or '无'},{py or '无'}"
        if snapshot != last_snapshot:
            print(f"[INFO] ARC 感知状态 {snapshot}", flush=True)
            last_snapshot = snapshot
        if state == "1":
            running = True
        if px and py:
            pose_ready = True
            break
        time.sleep(1)
    if not running:
        print("[ERROR] ARC 感知未进入 RUNNING，未发送地图标记请求。", flush=True)
        raise SystemExit(5)
    if not pose_ready:
        print("[ERROR] ARC 感知未输出 /arc/perception_dock_pose，请确认充电桩二维码/桩体在视野内且无遮挡。", flush=True)
        raise SystemExit(5)


fields, old_ready = read_arc_fields()
print(f"[INFO] 标记目标地图: {MAP_YAML}", flush=True)
if old_ready:
    print("[INFO] 地图已有充电桩标记，本次会刷新桩位。", flush=True)
old_mtime = map_mtime()

ensure_arc_mapping_service()
ensure_localization()
start_perception()

ok, output = call_map_state(0)
if not ok:
    print("[ERROR] ARC mapping 进入 INIT 失败，未发送 ACTIVE。", flush=True)
    raise SystemExit(4)
time.sleep(2)
ok, output = call_map_state(3)
if not ok:
    if "Current state is 1" in output:
        print("[ERROR] ARC mapping 未进入 READY，通常是定位地图未连续定位或 /odom/localization_odom 未就绪。", flush=True)
    print("[ERROR] ARC mapping 进入 ACTIVE 失败，未发送 SAVE。", flush=True)
    raise SystemExit(4)
time.sleep(1)

ok, _output = call_map_state(5)
if not ok:
    print("[ERROR] ARC mapping 保存失败，map.yaml 未确认更新。", flush=True)
    raise SystemExit(4)

deadline = time.time() + MONITOR_SECONDS
while time.time() < deadline:
    fields, ready = read_arc_fields()
    new_mtime = map_mtime()
    if ready and (new_mtime != old_mtime or not old_ready):
        print("[INFO] map.yaml 已更新", flush=True)
        print(f"[INFO] 标记后地图 ARC 字段: {MAP_YAML}", flush=True)
        if fields:
            print(fields, flush=True)
        print("[INFO] 充电桩标记已写入地图，可在导航地图中看到桩位。", flush=True)
        raise SystemExit(0)
    if ready and old_ready:
        print("[INFO] map.yaml 已包含充电桩标记，等待文件更新时间确认。", flush=True)
    time.sleep(1)

fields, ready = read_arc_fields()
print(f"[INFO] 标记后地图 ARC 字段: {MAP_YAML}", flush=True)
if fields:
    print(fields, flush=True)
if ready:
    print("[WARN] map.yaml 包含充电桩标记，但未确认 mtime 变化；请刷新地图后复核桩位。", flush=True)
    raise SystemExit(0)
print("[ERROR] 未在 map.yaml 中看到 arc_position_flag=1，请检查 arc_mapping 保存流程。", flush=True)
raise SystemExit(5)
'''


def _mark_charging_dock_inner(
    profile: ProductProfile,
    map_pcd_path: str,
    tag_id: int = 0,
    monitor_seconds: int = 45,
) -> str:
    map_path_prefix = _payloads._map_path_prefix(map_pcd_path)
    map_yaml_path = f"{map_path_prefix}/map.yaml"
    map_id = _payloads.map_id_from_map_path(map_pcd_path)
    return (
        f"{remote_env(profile)}; "
        "source /opt/robot/robot_slam/install/setup.bash >/dev/null 2>&1 || true; "
        "source /opt/robot/robot_arc/install/setup.bash >/dev/null 2>&1 || true; "
        f"if [ ! -s {quote(map_pcd_path)} ]; then {echo_message(f'[ERROR] 地图 PCD 不存在或为空: {map_pcd_path}')}; exit 2; fi; "
        f"if [ ! -f {quote(map_yaml_path)} ]; then {echo_message(f'[ERROR] 当前地图 map.yaml 不存在: {map_yaml_path}')}; exit 2; fi; "
        "if ! ros2 interface show robots_dog_msgs/srv/MapState >/dev/null 2>&1; then "
        "echo '[ERROR] robots_dog_msgs/srv/MapState 不可用，请检查 robot_slam/robot_arc 环境'; exit 2; fi; "
        "if ! ros2 interface show robots_dog_msgs/msg/ArcModuleCmd >/dev/null 2>&1; then "
        "echo '[ERROR] robots_dog_msgs/msg/ArcModuleCmd 不可用，请检查 robot_arc 环境'; exit 2; fi; "
        f"python3 -c {quote(_arc_marking_app_ws_python())} "
        f"{quote(map_id)} {quote(map_path_prefix)} {quote(map_yaml_path)} {int(tag_id)} {monitor_seconds}"
    )


def mark_charging_dock_command(
    profile: ProductProfile,
    map_pcd_path: str,
    tag_id: int = 0,
    monitor_seconds: int = 45,
    slam_version: str = "",
) -> CommandSpec:
    del slam_version
    monitor_seconds = max(10, min(int(monitor_seconds), 120))
    inner = _mark_charging_dock_inner(profile, map_pcd_path, tag_id, monitor_seconds)
    return CommandSpec(
        "标记充电桩",
        ssh_command(profile, inner),
        dangerous=True,
        description=(
            "请确认已选择并加载当前作业地图，机器狗位于充电桩正前方的标记位："
            "机身朝向充电桩，二维码/桩体在传感器视野内且无遮挡，距离适合 ARC 稳定识别。"
            "不要在斜角过大、距离过近/过远、桩体被遮挡或机器人仍在移动时标记。"
            "该操作会先通过系统应用通道加载定位地图，再通过 ARC mapping 将当前充电桩位置写入当前地图 map.yaml，"
            "用于后续有图回充；它不是 ARC/apriltag 标定。"
        ),
        display_command="执行：标记充电桩",
        concurrency="parallel",
        locks=("navigation", "app_ws"),
    )
