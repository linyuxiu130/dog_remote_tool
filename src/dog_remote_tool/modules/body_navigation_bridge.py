from __future__ import annotations

from dog_remote_tool.core.profiles import ProductProfile
from dog_remote_tool.core.shell import CommandSpec, quote, remote_env, ssh_command, sudo_run_shell
from dog_remote_tool.modules.control.shared import l2_control_profile, robot_sdk_control_profile


def body_navigation_bridge_profile(profile: ProductProfile) -> ProductProfile | None:
    return robot_sdk_control_profile(profile) or l2_control_profile(profile)


def _switch_robot_roamerx_control_inner() -> str:
    script = r'''
import time

import rclpy
from rclpy.action import ActionClient
from robot_common_interface.action import ControlServerSwitchControl
from robot_common_interface.msg import ControlServerCurrentRequesterInfo

TARGET = "robot_roamerx"

rclpy.init()
node = rclpy.create_node("dog_remote_robot_roamerx_control")
state = {"requester": ""}

def on_requester(msg):
    state["requester"] = msg.controller_name

node.create_subscription(ControlServerCurrentRequesterInfo, "/robot_control_server/current_requester_info", on_requester, 10)

def wait_requester(timeout_sec):
    state["requester"] = ""
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        rclpy.spin_once(node, timeout_sec=0.05)
        if state["requester"]:
            return state["requester"]
    return state["requester"]

try:
    if wait_requester(1.5) == TARGET:
        print("[INFO] 导航控制权已就绪，跳过重复申请")
        raise SystemExit(0)

    print("[INFO] 正在申请导航控制权")
    client = ActionClient(node, ControlServerSwitchControl, "/robot_control_server/switch_control")
    if not client.wait_for_server(timeout_sec=2.0):
        print("[ERROR] 导航控制权申请失败，控制服务未就绪")
        raise SystemExit(13)

    goal = ControlServerSwitchControl.Goal()
    goal.requester_name = TARGET
    goal.level = 1
    goal.priority = 40
    future = client.send_goal_async(goal)
    deadline = time.monotonic() + 2.0
    while not future.done() and time.monotonic() < deadline:
        rclpy.spin_once(node, timeout_sec=0.05)
    if not future.done() or not future.result().accepted:
        print("[ERROR] 导航控制权申请失败，控制服务拒绝请求")
        raise SystemExit(13)

    deadline = time.monotonic() + 3.0
    while time.monotonic() < deadline:
        if wait_requester(0.3) == TARGET:
            print("[INFO] 导航控制权已就绪")
            raise SystemExit(0)
    print("[ERROR] 导航控制权申请失败，已取消下发")
    raise SystemExit(13)
finally:
    node.destroy_node()
    rclpy.shutdown()
'''.strip()
    return f"python3 -c {quote(script)}"


def _ensure_robot_roamerx_forward_cmd_vel_inner() -> str:
    cfg = "/opt/robot/install/robot_roamerx/share/robot_roamerx/config/zsm/robot_roamerx.yaml"
    updater = r'''
import re
import sys
from pathlib import Path

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
pattern = re.compile(r"^(\s*enable_forward_cmd_vel\s*:\s*)(?:!!bool\s*)?(true|false)\s*$", re.M)
if not pattern.search(text):
    raise SystemExit("missing enable_forward_cmd_vel")
text = pattern.sub(r"\g<1>!!bool true", text, count=1)
path.write_text(text, encoding="utf-8")
'''.strip()
    return (
        "ROAMER_FORWARD=$(timeout 3s ros2 param get /robot_roamerx enable_forward_cmd_vel 2>/dev/null || true); "
        "if printf '%s\\n' \"$ROAMER_FORWARD\" | grep -qi 'true'; then "
        "echo '[INFO] robot_roamerx 已启用导航速度转发'; "
        "else "
        f"ROAMER_CFG={quote(cfg)}; "
        "if [ ! -f \"$ROAMER_CFG\" ]; then "
        "echo '[ERROR] robot_roamerx 未找到速度转发配置，已取消下发'; exit 13; "
        "fi; "
        f"{sudo_run_shell(fallback_without_sudo=False)}"
        "sudo_run cp -n \"$ROAMER_CFG\" \"$ROAMER_CFG.dog_remote_bak\" 2>/dev/null || true; "
        f"sudo_run python3 -c {quote(updater)} \"$ROAMER_CFG\" || {{ "
        "echo '[ERROR] robot_roamerx 速度转发配置修改失败，已取消下发'; exit 13; "
        "}; "
        "robot-launch restart robot_roamerx >/tmp/dog_remote_robot_roamerx_restart.log 2>&1 || { "
        "cat /tmp/dog_remote_robot_roamerx_restart.log 2>/dev/null || true; "
        "echo '[ERROR] robot_roamerx 重启失败，已取消下发'; exit 13; "
        "}; "
        "FORWARD_READY=0; "
        "for _forward_i in 1 2 3 4 5; do "
        "ROAMER_FORWARD=$(timeout 3s ros2 param get /robot_roamerx enable_forward_cmd_vel 2>/dev/null || true); "
        "if printf '%s\\n' \"$ROAMER_FORWARD\" | grep -qi 'true'; then FORWARD_READY=1; break; fi; "
        "sleep 0.6; "
        "done; "
        "if [ \"$FORWARD_READY\" != 1 ]; then "
        "echo '[ERROR] robot_roamerx 速度转发未生效，已取消下发'; exit 13; "
        "fi; "
        "echo '[INFO] robot_roamerx 已启用导航速度转发'; "
        "fi; "
    )


def ensure_body_navigation_bridge_command(profile: ProductProfile, *, require_control_switch: bool = False) -> str:
    body_profile = body_navigation_bridge_profile(profile)
    if body_profile is None:
        return ""
    needs_switch_control = require_control_switch and robot_sdk_control_profile(profile) is not None
    switch_control_inner = _switch_robot_roamerx_control_inner() if needs_switch_control else ""
    ready_marker = "/tmp/dog_remote_robot_roamerx_nav_ready"
    marker_fast_path = (
        "READY_TS=$(cat \"$READY_MARKER\" 2>/dev/null || true); "
        "NOW_TS=$(date +%s); "
        "if printf '%s\\n' \"$ROAMER_STATUS\" | grep -q 'running' "
        "&& case \"$READY_TS\" in ''|*[!0-9]*) false ;; *) [ $((NOW_TS - READY_TS)) -le 90 ] ;; esac; then "
        "echo '[INFO] 导航服务已就绪，复用已预热控制权'; "
        "exit 0; "
        "fi; "
        if needs_switch_control
        else ""
    )
    inner = (
        f"{remote_env(body_profile)}; "
        "source /opt/robot/install/setup.bash >/dev/null 2>&1 || true; "
        "if [ \"${DOG_REMOTE_DISABLE_BODY_NAV_BRIDGE:-0}\" = 1 ]; then "
        "echo '[INFO] 已跳过导航准备检查'; exit 0; "
        "fi; "
        "if ! command -v robot-launch >/dev/null 2>&1; then "
        "echo '[ERROR] 远端缺少导航准备工具，无法开始导航'; exit 13; "
        "fi; "
    )
    inner += (
        "ROAMER_STATUS=$(robot-launch list 2>/dev/null | sed -r 's/\\x1B\\[[0-9;]*[mK]//g' | grep -E 'robot_roamerx' | head -1 || true); "
        f"READY_MARKER={quote(ready_marker)}; "
        f"{marker_fast_path}"
        "if printf '%s\\n' \"$ROAMER_STATUS\" | grep -q 'running'; then "
        "echo '[INFO] 导航服务已在运行'; "
        "else "
        "echo '[INFO] 正在启动导航服务'; "
        "robot-launch start robot_roamerx >/tmp/dog_remote_robot_roamerx_start.log 2>&1 || { "
        "cat /tmp/dog_remote_robot_roamerx_start.log 2>/dev/null || true; "
        "echo '[ERROR] 导航服务启动失败，已取消下发'; exit 13; "
        "}; "
        "fi; "
    )
    if needs_switch_control:
        inner += (
            f"{_ensure_robot_roamerx_forward_cmd_vel_inner()}"
            "echo '[INFO] 导航服务已就绪'; "
            f"{switch_control_inner} && date +%s > {quote(ready_marker)}"
        )
    else:
        inner += (
        "BRIDGE_READY=0; "
        "for _bridge_i in 1 2 3 4 5 6 7 8; do "
        "NAV_POSE_PUBS=$(timeout 2s ros2 topic info /robot_control_server/nav_pose --no-daemon 2>/dev/null "
        "| awk -F: '/Publisher count:/ {gsub(/[[:space:]]/, \"\", $2); print $2; exit}'); "
        "if [ \"${NAV_POSE_PUBS:-0}\" -ge 1 ] 2>/dev/null; then BRIDGE_READY=1; break; fi; "
        "sleep 0.8; "
        "done; "
        "if [ \"$BRIDGE_READY\" != 1 ]; then "
        "echo '[ERROR] 导航服务未就绪，已取消下发'; "
        "exit 13; "
        "fi; "
        "echo '[INFO] 导航服务已就绪'; "
        )
    return ssh_command(body_profile, inner)


def release_body_navigation_bridge_command(profile: ProductProfile, *, stop_service: bool = True) -> CommandSpec | None:
    body_profile = body_navigation_bridge_profile(profile)
    if body_profile is None:
        return None
    ready_marker = "/tmp/dog_remote_robot_roamerx_nav_ready"
    roamer_running_action = (
        "robot-launch stop robot_roamerx >/tmp/dog_remote_stop_robot_roamerx.log 2>&1 || cat /tmp/dog_remote_stop_robot_roamerx.log 2>/dev/null || true; "
        f"rm -f {quote(ready_marker)} 2>/dev/null || true; "
        "echo '[INFO] 已停止 robot_roamerx，释放导航控制权'; "
        if stop_service
        else "echo '[INFO] 已释放导航控制提示，保留 robot_roamerx 以加速下次导航'; "
    )
    inner = (
        f"{remote_env(body_profile)}; "
        "source /opt/robot/install/setup.bash >/dev/null 2>&1 || true; "
        "timeout 0.8s ros2 topic pub -r 20 /robot_roamerx/is_in_nav_control std_msgs/msg/Bool '{data: false}' "
        ">/tmp/dog_remote_navigation_body_release.log 2>&1 || true; "
        "if command -v robot-launch >/dev/null 2>&1; then "
        "ROAMER_STATUS=$(robot-launch list 2>/dev/null | sed -r 's/\\x1B\\[[0-9;]*[mK]//g' | grep -E 'robot_roamerx' | head -1 || true); "
        "if printf '%s\\n' \"$ROAMER_STATUS\" | grep -q 'running'; then "
        f"{roamer_running_action}"
        "else "
        "echo '[INFO] robot_roamerx 未运行，导航控制权已释放'; "
        "fi; "
        "else "
        "echo '[WARN] 未找到 robot-launch，仅发送 /robot_roamerx/is_in_nav_control=false'; "
        "fi"
    )
    return CommandSpec(
        "释放本体导航控制权",
        ssh_command(body_profile, inner),
        display_command="执行：释放本体导航控制权",
        concurrency="parallel",
        locks=("navigation-body-release",),
    )


def navigation_start_ssh_command(
    profile: ProductProfile,
    remote_inner: str,
    *,
    require_control_switch: bool = False,
) -> str:
    command = ssh_command(profile, remote_inner)
    bridge_command = ensure_body_navigation_bridge_command(profile, require_control_switch=require_control_switch)
    if not bridge_command:
        return command
    return (
        "if [ \"${DOG_REMOTE_DISABLE_BODY_NAV_BRIDGE:-0}\" = 1 ]; then "
        "echo '[INFO] 已跳过导航准备检查'; "
        f"( {command} ); "
        "else "
        f"( {bridge_command} ) && ( {command} ); "
        "fi"
    )
