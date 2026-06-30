from __future__ import annotations

from dog_remote_tool.core.profiles import ProductProfile
from dog_remote_tool.core.shell import CommandSpec, quote, remote_env, ssh_command
from dog_remote_tool.modules.body_navigation_bridge import (
    body_navigation_bridge_profile,
    ensure_body_navigation_bridge_command,
    navigation_start_ssh_command,
)
from dog_remote_tool.modules.arc_app_ws import common_arc_app_ws_python, stale_app_ws_cleanup_shell
from dog_remote_tool.modules.mapping import arc_common as _arc_common
from dog_remote_tool.modules.mapping import arc_status as _arc_status


ARC_DOCK_STATE_TEXT = _arc_common.ARC_DOCK_STATE_TEXT
ARC_STATE_TEXT = _arc_common.ARC_STATE_TEXT
arc_runtime_profile = _arc_common.arc_runtime_profile
arc_status_snapshot_command = _arc_status.arc_status_snapshot_command


ARC_ACTIONS = {
    "dock": ("回充", "start_arc_align_coarse", True),
    "undock": ("出桩", "exit_charging", True),
}
ARC_ACTION_MONITOR_SECONDS_MAX = 120


def _undock_control_precheck_command(profile: ProductProfile) -> str:
    body_profile = body_navigation_bridge_profile(profile)
    if body_profile is None:
        return ""
    python = r'''
import json
import shutil
import socket
import subprocess
import sys
import time

import rclpy
from robot_common_interface.msg import ControlServerCurrentRequesterInfo


def read_requester(node, timeout=1.2):
    seen = []

    def callback(msg):
        if not seen:
            seen.append(str(msg.controller_name or ""))

    sub = node.create_subscription(
        ControlServerCurrentRequesterInfo,
        "/robot_control_server/current_requester_info",
        callback,
        10,
    )
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline and not seen:
        rclpy.spin_once(node, timeout_sec=0.02)
    node.destroy_subscription(sub)
    return seen[0] if seen else ""


def request_nav_control():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        target = ("127.0.0.1", 8081)
        for payload in ({"role": "remote", "type": "heartbeat"}, {"cmd": 180, "type": "cmd"}):
            sock.sendto(json.dumps(payload, separators=(",", ":")).encode("utf-8"), target)
            time.sleep(0.05)
    finally:
        sock.close()


def robot_remote_has_client():
    try:
        with open("/proc/net/tcp", "r", encoding="ascii", errors="ignore") as handle:
            lines = handle.readlines()[1:]
    except Exception:
        return True
    for line in lines:
        parts = line.split()
        if len(parts) < 4:
            continue
        local = parts[1]
        remote = parts[2]
        state = parts[3]
        if state != "01":
            continue
        if local.rsplit(":", 1)[-1].upper() == "1F91" or remote.rsplit(":", 1)[-1].upper() == "1F91":
            return True
    return False


def restart_robot_remote_if_possible():
    if shutil.which("robot-launch") is None:
        print("[WARN] 未找到 robot-launch，无法清理遗留 robot_remote 控制状态。", flush=True)
        return False
    try:
        result = subprocess.run(
            ["robot-launch", "restart", "robot_remote"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=6,
            check=False,
        )
    except subprocess.TimeoutExpired:
        print("[WARN] robot_remote 重启超时，无法自动清理遗留控制状态。", flush=True)
        return False
    if result.returncode == 0:
        print("[WARN] 已重启 robot_remote 清理遗留控制状态。", flush=True)
        time.sleep(1.0)
        return True
    output = (result.stdout or "").strip()
    print(f"[WARN] robot_remote 重启失败，无法自动清理遗留控制状态。{output}", flush=True)
    return False


def try_claim_for_undock(reason):
    if reason:
        print(f"[WARN] 出桩前检测到底盘控制权占用：{reason}，正在尝试抢占/切换控制权。", flush=True)
    request_nav_control()
    time.sleep(0.25)


def is_allowed_undock_requester(requester):
    if not requester:
        return True
    normalized = requester.lower()
    if requester == "robot_roamerx":
        return True
    return "arc" in normalized or "charg" in normalized


rclpy.init()
node = rclpy.create_node("dog_remote_arc_undock_control_precheck")
try:
    requester = read_requester(node)
    if is_allowed_undock_requester(requester):
        raise SystemExit(0)
    if requester == "robot_remote" and not robot_remote_has_client():
        restart_robot_remote_if_possible()
    try_claim_for_undock(f"requester={requester}")
    requester = read_requester(node, timeout=1.0)
    print(f"[INFO] 出桩控制权处理后 requester={requester or '--'}", flush=True)
    if is_allowed_undock_requester(requester):
        raise SystemExit(0)
    if requester == "robot_remote":
        print("[ERROR] 出桩前仍被 robot_remote 占用，请关闭其他遥控后再出桩。", flush=True)
        raise SystemExit(7)
    if requester:
        print(f"[ERROR] 出桩前控制权仍被 {requester} 占用，请关闭对应 app 后再出桩。", flush=True)
        raise SystemExit(7)
finally:
    node.destroy_node()
    rclpy.shutdown()
'''
    inner = (
        f"{remote_env(body_profile)}; "
        "source /opt/robot/install/setup.bash >/dev/null 2>&1 || true; "
        f"python3 -c {quote(python)}"
    )
    return ssh_command(body_profile, inner)


def _undock_legacy_control_cleanup_command(profile: ProductProfile) -> str:
    body_profile = body_navigation_bridge_profile(profile)
    if body_profile is None:
        return ""
    remote = (
        f"{remote_env(body_profile)}; "
        "old_control_pids=$(ps -eo pid,args | awk "
        "'/dog_remote_keyboard_control_claim[.]log|ros2 topic pub -r 20 \\/control_right\\/test std_msgs\\/msg\\/Bool [{]data: true[}]/ "
        "&& $0 !~ /awk/ {print $1}'); "
        "if [ -n \"$old_control_pids\" ]; then "
        "echo '[WARN] 出桩前清理本工具遗留控制权发布器'; "
        "kill $old_control_pids >/dev/null 2>&1 || true; "
        "sleep 0.1; "
        "kill -9 $old_control_pids >/dev/null 2>&1 || true; "
        "timeout 0.4s ros2 topic pub -r 20 /control_right/test std_msgs/msg/Bool '{data: false}' "
        ">/tmp/dog_remote_arc_undock_pre_release_control_right.log 2>&1 || true; "
        "fi"
    )
    return ssh_command(body_profile, remote)


def _arc_app_ws_action_python() -> str:
    return common_arc_app_ws_python() + r'''
ACTION = sys.argv[1]
MONITOR_SECONDS = int(sys.argv[2])

ACTION_FUNC = {
    "dock": "start_arc_align_coarse",
    "undock": "exit_charging",
}[ACTION]
ACTION_RESPONSE_FUNC = {
    "start_arc_align_coarse": "start_align_coarse",
    "exit_charging": "exit_charging",
}
ARC_ERROR_CODES = set()


def request(func, frame):
    return {
        "head": {
            "type": "app_req",
            "time_stamp": int(time.time() * 1000),
            "source": "app",
            "frame_count": frame,
        },
        "data": {"req_func": {func: None}},
    }


def remember_arc_error(parsed):
    data = parsed.get("data", {}) if isinstance(parsed, dict) else {}
    for item in data.get("items", []) if isinstance(data, dict) else []:
        code = str(item.get("code", ""))
        desc = str(item.get("description", ""))
        if code:
            ARC_ERROR_CODES.add(code)
        if desc:
            ARC_ERROR_CODES.add(desc)
    print_arc_notify(parsed)


def dock_not_ready_seen():
    return "13697" in ARC_ERROR_CODES or "DOCK_NOT_READY" in ARC_ERROR_CODES


def undock_failure_seen():
    return (
        "13708" in ARC_ERROR_CODES
        or "13709" in ARC_ERROR_CODES
        or "EXIT_DOCK_FAILURE" in ARC_ERROR_CODES
    )


def print_dock_not_ready_hint():
    print(
        "[ERROR] 充电桩未就绪（DOCK_NOT_READY）。请确认充电桩已上电，并已完成蓝牙/UWB/桩配对。",
        flush=True,
    )


def read_response(sock, func, wait_seconds):
    deadline = time.time() + wait_seconds
    while time.time() < deadline:
        message = recv_text(sock)
        if not message:
            continue
        if "app_sub_topic" in message and "odom_ground_truth" in message:
            continue
        parsed = parse_app_response(message)
        if isinstance(parsed, dict) and parsed.get("kind") == "app_resp":
            if parsed.get("func") == func:
                return parsed
        elif isinstance(parsed, dict) and parsed.get("head", {}).get("type") == "alg_error_code_notify":
            remember_arc_error(parsed)
    return None


def send_action(sock, frame, func):
    send_text(sock, request(func, frame))
    frame += 1
    print("[INFO] 已发送出桩请求。" if ACTION == "undock" else "[INFO] 已发送无图进桩请求。", flush=True)
    parsed = read_response(sock, ACTION_RESPONSE_FUNC.get(func, func), 3)
    if parsed is None:
        return frame
    if parsed.get("status") not in (None, "ok"):
        print(
            f"[ERROR] ARC 请求失败: status={parsed.get('status')} error={parsed.get('error_code')}",
            flush=True,
        )
        raise SystemExit(6)
    return frame


def query_status(sock, frame):
    status = {}
    for func in ("get_arc_alg_status", "get_arc_dock_status"):
        send_text(sock, request(func, frame))
        frame += 1
        parsed = read_response(sock, func, 0.8)
        if parsed is not None:
            status[func] = parsed.get("data")
    return status, frame


def action_stage_text(alg, dock):
    if ACTION == "dock":
        if alg == "DockAlignCoarse":
            return "已识别充电桩，开始粗对准。"
        if alg == "DockAlignFine":
            return "正在精对准。"
        if alg == "DockContact":
            return "已接触充电桩。"
        if alg == "RequestPowerOn" or dock == "Contact":
            return "正在请求充电桩上电。"
        return ""
    if alg == "ChargedExit":
        return "正在出桩。"
    if alg == "UnDockReset":
        return "正在完成出桩复位。"
    return ""


sock = connect_ws()
frame = 1
try:
    before, frame = query_status(sock, frame)
    alg_before = str(before.get("get_arc_alg_status") or "")
    dock_before = str(before.get("get_arc_dock_status") or "")
    if ACTION == "dock" and (alg_before == "Charging" or dock_before == "Charging"):
        print("[ERROR] 当前已经在充电中，请使用出桩。", flush=True)
        raise SystemExit(4)
    if ACTION == "dock" and dock_before == "Passive":
        print_dock_not_ready_hint()
        raise SystemExit(7)
    if ACTION == "undock" and not (alg_before == "Charging" or dock_before == "Charging"):
        print("[ERROR] 当前未处于充电状态，不能出桩。", flush=True)
        raise SystemExit(5)

    frame = send_action(sock, frame, ACTION_FUNC)

    end = time.time() + MONITOR_SECONDS
    last = None
    undock_success_seen = False
    while time.time() < end:
        status, frame = query_status(sock, frame)
        snapshot = (status.get("get_arc_alg_status"), status.get("get_arc_dock_status"))
        if snapshot != last:
            stage_text = action_stage_text(snapshot[0], snapshot[1])
            if stage_text:
                print(f"[INFO] {stage_text}", flush=True)
            last = snapshot
        alg = str(status.get("get_arc_alg_status") or "")
        dock = str(status.get("get_arc_dock_status") or "")
        if ACTION == "dock" and dock_not_ready_seen():
            print_dock_not_ready_hint()
            raise SystemExit(7)
        if ACTION == "dock" and (alg == "Charging" or dock == "Charging"):
            print("[INFO] 回充成功，已进入充电状态。", flush=True)
            raise SystemExit(0)
        if ACTION == "undock" and undock_failure_seen():
            print("[ERROR] ARC 出桩失败。", flush=True)
            raise SystemExit(7)
        if ACTION == "undock" and alg in {"FailureSafe", "Failure", "FailureContact"}:
            print("[ERROR] ARC 出桩进入失败状态。", flush=True)
            raise SystemExit(7)
        if ACTION == "undock" and alg == "Success":
            undock_success_seen = True
        if ACTION == "undock" and undock_success_seen and alg in {"Success", "StandBy"} and dock in {"StandBy", "Finished"}:
            print("[INFO] 出桩成功，已离开充电状态。", flush=True)
            raise SystemExit(0)
        if ACTION == "dock" and alg in {"FailureSafe", "Failure", "Passive", "UnDockReset", "ChargedExit"}:
            print("[ERROR] ARC 无图进桩失败。", flush=True)
            if dock_not_ready_seen() or dock == "Passive":
                print_dock_not_ready_hint()
            raise SystemExit(7)
        if ACTION == "dock" and ARC_ERROR_CODES and alg in {"StandBy", "Success"} and dock != "Charging":
            print("[ERROR] ARC 无图进桩失败。", flush=True)
            if dock_not_ready_seen():
                print_dock_not_ready_hint()
            raise SystemExit(7)
        time.sleep(0.5)

    print("[ERROR] ARC 动作等待超时。", flush=True)
    if dock_not_ready_seen():
        print_dock_not_ready_hint()
    if ACTION == "undock" and not undock_success_seen:
        print("[ERROR] 出桩未观察到 ARC Success 状态，不能仅凭 StandBy 判定成功。", flush=True)
    if ACTION == "dock":
        try:
            send_text(sock, request("stop_arc", frame))
            print("[INFO] 已发送 stop_arc 清理超时回充任务。", flush=True)
        except Exception as exc:
            print(f"[WARN] stop_arc 发送失败: {exc}", flush=True)
    raise SystemExit(8)
finally:
    try:
        send_close(sock)
    except Exception:
        pass
    try:
        sock.close()
    except Exception:
        pass
'''


def arc_start_action_command(
    profile: ProductProfile,
    action: str,
    map_path: str = "",
    tag_id: int = 0,
    monitor_seconds: int = 120,
) -> CommandSpec:
    if action not in ARC_ACTIONS:
        return CommandSpec("ARC 动作", "echo '[ERROR] 未知 ARC 动作'; exit 2", dangerous=False)
    profile = arc_runtime_profile(profile)
    label, _app_func, dangerous = ARC_ACTIONS[action]
    monitor_seconds = max(5, min(int(monitor_seconds), ARC_ACTION_MONITOR_SECONDS_MAX))
    inner = (
        f"{remote_env(profile)}; "
        "source /opt/robot/robot_arc/install/setup.bash >/dev/null 2>&1 || true; "
        f"{stale_app_ws_cleanup_shell()}"
        f"python3 -c {quote(_arc_app_ws_action_python())} {quote(action)} {monitor_seconds}"
    )
    command = navigation_start_ssh_command(profile, inner)
    if action == "undock":
        bridge_command = ensure_body_navigation_bridge_command(profile)
        arc_command = ssh_command(profile, inner)
        legacy_control_cleanup = _undock_legacy_control_cleanup_command(profile)
        precheck = _undock_control_precheck_command(profile)
        if bridge_command and precheck:
            undock_preflight = " && ".join(
                f"( {part} )" for part in (bridge_command, legacy_control_cleanup, precheck) if part
            )
            command = (
                "if [ \"${DOG_REMOTE_DISABLE_BODY_NAV_BRIDGE:-0}\" = 1 ]; then "
                "echo '[INFO] 已跳过导航准备检查'; "
                f"( {arc_command} ); "
                "else "
                f"{undock_preflight} && ( {arc_command} ); "
                "fi"
            )
    return CommandSpec(
        label,
        command,
        dangerous=dangerous,
        description=f"会通过系统应用通道执行 ARC {label}，机器人可能移动。",
        display_command=f"执行：ARC {label}",
        locks=("arc", "motion", "app_ws"),
    )


def arc_release_control_command(profile: ProductProfile) -> CommandSpec:
    profile = arc_runtime_profile(profile)
    inner = (
        f"{remote_env(profile)}; "
        "timeout 0.8s ros2 topic pub -r 20 /control_right/test std_msgs/msg/Bool '{data: false}' "
        ">/tmp/dog_remote_arc_control_release.log 2>&1 || true; "
        "echo '[INFO] 已发送 ARC 动作控制权释放提示: /control_right/test=false'"
    )
    return CommandSpec(
        "ARC 释放控制权",
        ssh_command(profile, inner),
        dangerous=False,
        description="发布 /control_right/test=false，释放 ARC 动作控制权提示。",
        display_command="执行：ARC 释放控制权",
        locks=("arc",),
    )
