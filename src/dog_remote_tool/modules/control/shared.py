from __future__ import annotations

import os
import textwrap

from dog_remote_tool.core.network_routes import with_route_repair
from dog_remote_tool.core.profiles import ProductProfile, get_product
from dog_remote_tool.core.shell import (
    quote,
    remote_env,
    ssh_command,
    ssh_prefix_command,
    sshpass_file,
)


def tool_cli() -> str:
    return os.environ.get("DOG_REMOTE_TOOL_CLI", "python3 -m dog_remote_tool")


def ssh_bash_stdin_command(profile: ProductProfile, script: str, env: dict[str, str] | None = None) -> str:
    env_values = dict(env or {})
    env_values.pop("SUDO_PASS", None)
    env_prefix = " ".join(f"{key}={quote(value)}" for key, value in env_values.items())
    remote = (
        "IFS= read -r SUDO_PASS || SUDO_PASS=; export SUDO_PASS; "
        f"{env_prefix} bash -s"
    ).strip()
    command = (
        f"{{ cat {quote(sshpass_file(profile.password))}; cat <<'DOG_REMOTE_L2_NAV_SCRIPT'\n"
        f"{script.rstrip()}\n"
        "DOG_REMOTE_L2_NAV_SCRIPT\n"
        f"}} | {ssh_prefix_command(profile)} {quote(remote)}"
    )
    return with_route_repair(profile, command)


def l2_control_profile(profile: ProductProfile) -> ProductProfile | None:
    if profile.key == "xg2_3588":
        return profile
    if profile.key == "xg2_s100":
        return get_product("xg2_3588")
    return None


def robot_sdk_control_profile(profile: ProductProfile) -> ProductProfile | None:
    key = getattr(profile, "key", "")
    if key in {"zg3588", "zg_surround_3588"}:
        return profile
    if key in {"zg_surround_s100", "zg_lidar_nx"}:
        return get_product("zg3588")
    return None


def robot_remote_control_profile(profile: ProductProfile) -> ProductProfile | None:
    key = getattr(profile, "key", "")
    if key in {"xg2_3588", "xg2_s100"}:
        return get_product("xg2_3588")
    return robot_sdk_control_profile(profile)


def arc_charging_guard_command(profile: ProductProfile) -> str:
    remote = (
        f"{remote_env(profile)}; "
        "state=$(timeout 2s ros2 topic echo --once /arc/dock_state --no-daemon 2>/dev/null "
        "| awk '/^state:/ {print $2; exit}' || true); "
        "if [ \"$state\" = 2 ]; then "
        "printf '%s\\n' DOG_REMOTE_ARC_BLOCK_CHARGING=1; "
        "printf '%s\\n' '[ERROR] 当前 /arc/dock_state=CHARGING(2)，请先退出充电/回充，确认离开充电状态后再执行站立或遥控。'; "
        "elif [ -n \"$state\" ]; then "
        "printf '[INFO] /arc/dock_state=%s，允许遥控。\\n' \"$state\"; "
        "fi"
    )
    check = ssh_command(profile, remote)
    return textwrap.dedent(
        f"""
        _dog_remote_arc_guard_output="$({check} 2>/dev/null || true)"
        if printf '%s\\n' "$_dog_remote_arc_guard_output" | grep -qx 'DOG_REMOTE_ARC_BLOCK_CHARGING=1'; then
          printf '%s\\n' "$_dog_remote_arc_guard_output" | sed '/^DOG_REMOTE_ARC_BLOCK_CHARGING=1$/d'
          exit 42
        fi
        if [ -n "$_dog_remote_arc_guard_output" ]; then
          printf '%s\\n' "$_dog_remote_arc_guard_output" | sed '/^DOG_REMOTE_ARC_BLOCK_CHARGING=1$/d'
        fi
        """
    ).strip()


def motion_control_claim_command(profile: ProductProfile) -> str:
    remote = f"""{remote_env(profile)}
set +e
old_pids=$(ps -eo pid,args | awk '/dog_remote_keyboard_control_claim[.]log|ros2 topic pub -r 20 \\/control_right\\/test std_msgs\\/msg\\/Bool [{{]data: true[}}]/ && $0 !~ /awk/ {{print $1}}')
if [ -n "$old_pids" ]; then
  kill $old_pids >/dev/null 2>&1 || true
  sleep 0.2
  kill -9 $old_pids >/dev/null 2>&1 || true
fi
timeout 86400s ros2 topic pub -r 20 /control_right/test std_msgs/msg/Bool '{{data: true}}' >/tmp/dog_remote_keyboard_control_claim.log 2>&1 &
claim_pid=$!
cleanup_claim() {{
  kill "$claim_pid" >/dev/null 2>&1 || true
  wait "$claim_pid" >/dev/null 2>&1 || true
}}
trap cleanup_claim EXIT HUP INT TERM
wait "$claim_pid"
"""
    return ssh_command(profile, remote)


def motion_control_release_command(profile: ProductProfile) -> str:
    remote = (
        f"{remote_env(profile)}; "
        "timeout 0.8s ros2 topic pub -r 20 /control_right/test std_msgs/msg/Bool '{data: false}' "
        ">/tmp/dog_remote_keyboard_control_release.log 2>&1 || true; "
        "echo '[INFO] 已释放键盘遥控控制权提示: /control_right/test=false'"
    )
    return ssh_command(profile, remote)


def robot_remote_restore_occupancy_command(profile: ProductProfile) -> str:
    target = robot_remote_control_profile(profile)
    if target is None:
        return ""
    marker = "/tmp/dog_remote_robot_roamerx_stopped_by_tool"
    remote = (
        f"{remote_env(target)}; "
        "source /opt/robot/install/setup.bash >/dev/null 2>&1 || true; "
        f"if [ -f {quote(marker)} ]; then "
        f"rm -f {quote(marker)}; "
        "if command -v robot-launch >/dev/null 2>&1; then "
        "if pgrep -af robot_roamerx >/dev/null 2>&1; then "
        "true; "
        "elif robot-launch start robot_roamerx >/tmp/dog_remote_start_robot_roamerx.log 2>&1; then "
        "printf '%s\\n' '[INFO] 已恢复 robot_roamerx，导航桥可继续接收 /navigation_cmd。'; "
        "elif grep -qi 'already running' /tmp/dog_remote_start_robot_roamerx.log 2>/dev/null; then "
        "true; "
        "else "
        "printf '%s\\n' '[WARN] robot-launch start robot_roamerx 执行失败:'; "
        "cat /tmp/dog_remote_start_robot_roamerx.log 2>/dev/null || true; "
        "fi; "
        "else "
        "printf '%s\\n' '[WARN] 未找到 robot-launch，无法自动恢复 robot_roamerx。'; "
        "fi; "
        "fi"
    )
    return ssh_command(target, remote)


def robot_remote_realtime_prepare_command(profile: ProductProfile) -> str:
    target = robot_remote_control_profile(profile)
    if target is None:
        return ""
    marker = "/tmp/dog_remote_robot_roamerx_stopped_by_tool"
    remote = (
        f"{remote_env(target)}; "
        "source /opt/robot/install/setup.bash >/dev/null 2>&1 || true; "
        "arc_state=$(timeout 0.5s ros2 topic echo --once /arc/dock_state --no-daemon 2>/dev/null "
        "| awk '/^state:/ {print $2; exit}' || true); "
        "if [ \"$arc_state\" = 2 ]; then "
        "printf '%s\\n' DOG_REMOTE_ARC_BLOCK_CHARGING=1; "
        "printf '%s\\n' '[ERROR] 当前正在充电，请先出桩后再遥控。'; "
        "exit 42; "
        "fi; "
        "req_msg=$(timeout 0.6s ros2 topic echo --once /robot_control_server/current_requester_info --no-daemon 2>/dev/null || true); "
        "requester=$(printf '%s\\n' \"$req_msg\" | awk -F: '/controller_name:/ {gsub(/^[[:space:]]+|[[:space:]]+$/, \"\", $2); print $2; exit}'); "
        "if [ \"$requester\" = robot_roamerx ]; then "
        "printf '%s\\n' '[实时遥控] 正在切换导航控制权。'; "
        "if command -v robot-launch >/dev/null 2>&1 && robot-launch stop robot_roamerx >/tmp/dog_remote_stop_robot_roamerx.log 2>&1; then "
        f"touch {quote(marker)}; "
        "fi; "
        "elif [ -n \"$requester\" ] && [ \"$requester\" != robot_remote ]; then "
        "printf '[实时遥控] 当前控制权由 %s 占用，继续尝试接管。\\n' \"$requester\"; "
        "elif [ \"$requester\" = robot_remote ]; then "
        "if ! ss -tan 2>/dev/null | awk '$1 == \"ESTAB\" && ($4 ~ /:8081$/ || $5 ~ /:8081$/) {found=1} END {exit !found}'; then "
        "printf '%s\\n' '[实时遥控] 清理上次未释放的 robot_remote 控制状态。'; "
        "if command -v robot-launch >/dev/null 2>&1; then "
        "robot-launch restart robot_remote >/tmp/dog_remote_restart_robot_remote.log 2>&1 || cat /tmp/dog_remote_restart_robot_remote.log 2>/dev/null || true; "
        "sleep 1.2; "
        "fi; "
        "fi; "
        "fi"
    )
    return ssh_command(target, remote)


def robot_remote_restart_command(profile: ProductProfile) -> str:
    target = robot_remote_control_profile(profile)
    if target is None:
        return ""
    remote = (
        f"{remote_env(target)}; "
        "source /opt/robot/install/setup.bash >/dev/null 2>&1 || true; "
        "if command -v robot-launch >/dev/null 2>&1; then "
        "robot-launch restart robot_remote >/tmp/dog_remote_restart_robot_remote.log 2>&1 || "
        "cat /tmp/dog_remote_restart_robot_remote.log 2>/dev/null || true; "
        "sleep 1.2; "
        "fi"
    )
    return ssh_command(target, remote)


def with_motion_control_claim(profile: ProductProfile, command: str) -> str:
    claim = motion_control_claim_command(profile)
    release = motion_control_release_command(profile)
    restore_roamerx = robot_remote_restore_occupancy_command(profile)
    return textwrap.dedent(
        f"""
        _dog_remote_motion_guard_pid=
        _dog_remote_release_motion_control() {{
          if [ -n "$_dog_remote_motion_guard_pid" ]; then
            kill "$_dog_remote_motion_guard_pid" >/dev/null 2>&1 || true
            wait "$_dog_remote_motion_guard_pid" >/dev/null 2>&1 || true
          fi
          {release}
          {restore_roamerx}
        }}
        trap _dog_remote_release_motion_control EXIT INT TERM
        {claim} &
        _dog_remote_motion_guard_pid=$!
        sleep 0.3
        {command}
        """
    ).strip()


def motion_state_hint_command(profile: ProductProfile) -> str:
    remote = (
        f"{remote_env(profile)}; "
        "source /opt/robot/install/setup.bash >/dev/null 2>&1 || true; "
        "state=$(timeout 2s ros2 topic echo --once /robot_control_server/mc_state --no-daemon 2>/dev/null || true); "
        "ctrl=$(printf '%s\\n' \"$state\" | awk '/cur_ctrl_mode:/ {print $2; exit}'); "
        "motion=$(printf '%s\\n' \"$state\" | awk '/cur_motion_mode:/ {print $2; exit}'); "
        "if [ -n \"$ctrl$motion\" ]; then "
        "printf '[INFO] 运动控制状态: cur_ctrl_mode=%s cur_motion_mode=%s\\n' \"${ctrl:---}\" \"${motion:---}\"; "
        "if [ \"$ctrl\" != 18 ] || [ \"$motion\" != 1 ]; then "
        "printf '%s\\n' '[WARN] 已抢占控制权，但当前不是站立控制态；方向键可能不会动，请先点 站立/恢复 或按 1。'; "
        "fi; "
        "else "
        "printf '%s\\n' '[WARN] 未读到 /robot_control_server/mc_state，无法确认站立控制态。'; "
        "fi"
    )
    return ssh_command(profile, remote)


def robot_remote_occupancy_guard_command(profile: ProductProfile) -> str:
    target = robot_remote_control_profile(profile)
    if target is None:
        return ""
    marker = "/tmp/dog_remote_robot_roamerx_stopped_by_tool"
    remote = (
        f"{remote_env(target)}; "
        "source /opt/robot/install/setup.bash >/dev/null 2>&1 || true; "
        "req_msg=$(timeout 2s ros2 topic echo --once /robot_control_server/current_requester_info --no-daemon 2>/dev/null || true); "
        "requester=$(printf '%s\\n' \"$req_msg\" | awk -F: '/controller_name:/ {gsub(/^[[:space:]]+|[[:space:]]+$/, \"\", $2); print $2; exit}'); "
        "if [ \"$requester\" = robot_roamerx ]; then "
        "printf '%s\\n' '[WARN] 当前底盘控制权被 robot_roamerx 占用，正在停止 robot_roamerx 以允许实时遥控。'; "
        "if command -v robot-launch >/dev/null 2>&1; then "
        "if robot-launch stop robot_roamerx >/tmp/dog_remote_stop_robot_roamerx.log 2>&1; then "
        f"touch {quote(marker)}; "
        "else "
        "printf '%s\\n' '[WARN] robot-launch stop robot_roamerx 执行失败:'; "
        "cat /tmp/dog_remote_stop_robot_roamerx.log 2>/dev/null || true; "
        "fi; "
        "else "
        "printf '%s\\n' '[WARN] 未找到 robot-launch，无法自动停止 robot_roamerx。'; "
        "fi; "
        "sleep 0.8; "
        "after_msg=$(timeout 2s ros2 topic echo --once /robot_control_server/current_requester_info --no-daemon 2>/dev/null || true); "
        "after_requester=$(printf '%s\\n' \"$after_msg\" | awk -F: '/controller_name:/ {gsub(/^[[:space:]]+|[[:space:]]+$/, \"\", $2); print $2; exit}'); "
        "printf '[INFO] 底盘控制权占用处理后 requester=%s\\n' \"${after_requester:---}\"; "
        "elif [ -n \"$requester\" ] && [ \"$requester\" != robot_remote ]; then "
        "printf '[WARN] 当前底盘控制权由 %s 占用，尝试继续实时遥控。\\n' \"$requester\"; "
        "else "
        "printf '[INFO] 底盘控制权未被 robot_roamerx 占用: requester=%s\\n' \"${requester:---}\"; "
        "fi"
    )
    return ssh_command(target, remote)


def l1_control_profile(profile: ProductProfile) -> ProductProfile | None:
    if profile.key == "xg3588":
        return profile
    if profile.key == "xg1_nx":
        return get_product("xg3588")
    return None


def l2_s100_profile(profile: ProductProfile) -> ProductProfile | None:
    if profile.key == "xg2_s100":
        return profile
    if profile.key == "xg2_3588":
        return get_product("xg2_s100")
    return None
