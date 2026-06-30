from __future__ import annotations

from dog_remote_tool.core.profiles import ProductProfile
from dog_remote_tool.core.shell import CommandSpec, echo_message, quote, remote_env, ssh_command
from dog_remote_tool.modules.arc_app_ws import common_arc_app_ws_python
from dog_remote_tool.modules.navigation.helper_scripts import (
    MODE_SWITCH_STATE_PID,
    START_NAV_HELPER_FIFO,
    START_NAV_HELPER_LOG,
    START_NAV_HELPER_PID,
    START_NAV_HELPER_SCRIPT,
    _start_navigation_helper_python,
)
from dog_remote_tool.modules.navigation.payloads import _payload_b64


def _ensure_start_navigation_helper_inner() -> str:
    helper = quote(_start_navigation_helper_python())
    return (
        f"START_NAV_HELPER_PID_FILE={quote(START_NAV_HELPER_PID)}; "
        f"START_NAV_HELPER_SCRIPT={quote(START_NAV_HELPER_SCRIPT)}; "
        f"START_NAV_HELPER_FIFO={quote(START_NAV_HELPER_FIFO)}; "
        f"START_NAV_HELPER_LOG={quote(START_NAV_HELPER_LOG)}; "
        "START_NAV_HELPER_PID=$(cat \"$START_NAV_HELPER_PID_FILE\" 2>/dev/null || true); "
        "if [ -n \"$START_NAV_HELPER_PID\" ] && kill -0 \"$START_NAV_HELPER_PID\" 2>/dev/null && [ -p \"$START_NAV_HELPER_FIFO\" ]; then "
        "true; "
        "else "
        "if [ -n \"$START_NAV_HELPER_PID\" ]; then kill \"$START_NAV_HELPER_PID\" 2>/dev/null || true; fi; "
        f"printf '%s' {helper} > \"$START_NAV_HELPER_SCRIPT\"; "
        "chmod +x \"$START_NAV_HELPER_SCRIPT\"; "
        "rm -f \"$START_NAV_HELPER_FIFO\"; "
        "nohup python3 \"$START_NAV_HELPER_SCRIPT\" >> \"$START_NAV_HELPER_LOG\" 2>&1 & "
        "START_NAV_HELPER_PID=$!; echo \"$START_NAV_HELPER_PID\" > \"$START_NAV_HELPER_PID_FILE\"; "
        "for _ in 1 2 3 4 5 6 7 8 9 10; do "
        "if kill -0 \"$START_NAV_HELPER_PID\" 2>/dev/null && [ -p \"$START_NAV_HELPER_FIFO\" ]; then break; fi; "
        "sleep 0.2; "
        "done; "
        "if kill -0 \"$START_NAV_HELPER_PID\" 2>/dev/null && [ -p \"$START_NAV_HELPER_FIFO\" ]; then "
        "true; "
        "else "
        "echo '[ERROR] 导航下发通道启动失败'; "
        "tail -20 \"$START_NAV_HELPER_LOG\" 2>/dev/null || true; "
        "exit 7; "
        "fi; "
        "fi; "
    )


def _prewarm_app_ws_broker_inner() -> str:
    python = common_arc_app_ws_python() + "\n" + r'''
import time

client = AppWsBrokerClient()
obj = {
    "head": {"type": "app_req", "time_stamp": int(time.time() * 1000), "source": "app", "frame_count": 1},
    "data": {"req_func": "get_nav_status"},
}
client.request(obj, "get_nav_status", 2)
print("[INFO] app websocket/broker 已就绪", flush=True)
'''.strip()
    return (
        f"python3 -c {quote(python)} || "
        "echo '[WARN] app websocket/broker 预热失败，首次导航会自动重试'; "
    )


def _publish_start_navigation_payload_inner(
    payload: str,
    success_message: str,
    failure_message: str,
    timeout_seconds: int = 4,
) -> str:
    encoded = _payload_b64(payload)
    return _publish_start_navigation_payload_b64_inner(quote(encoded), success_message, failure_message, timeout_seconds)


def _publish_start_navigation_payload_var_inner(
    payload_var: str,
    success_message: str,
    failure_message: str,
    timeout_seconds: int = 4,
) -> str:
    return _publish_start_navigation_payload_b64_inner(
        f"$(printf '%s' \"${payload_var}\" | base64 -w0)",
        success_message,
        failure_message,
        timeout_seconds,
    )


def _publish_start_navigation_payload_b64_inner(
    encoded_value: str,
    success_message: str,
    failure_message: str,
    timeout_seconds: int,
) -> str:
    return (
        f"{_ensure_start_navigation_helper_inner()}"
        f"START_NAV_HELPER_PID_FILE={quote(START_NAV_HELPER_PID)}; "
        f"START_NAV_HELPER_FIFO={quote(START_NAV_HELPER_FIFO)}; "
        f"START_NAV_PAYLOAD={encoded_value}; "
        "START_NAV_HELPER_PID=$(cat \"$START_NAV_HELPER_PID_FILE\" 2>/dev/null || true); "
        "if [ -n \"$START_NAV_HELPER_PID\" ] && kill -0 \"$START_NAV_HELPER_PID\" 2>/dev/null && [ -p \"$START_NAV_HELPER_FIFO\" ]; then "
        f"if timeout {int(timeout_seconds)}s sh -c 'printf \"%s\\n\" \"$1\" > \"$0\"' \"$START_NAV_HELPER_FIFO\" \"$START_NAV_PAYLOAD\"; then "
        f"{echo_message(success_message)}; "
        "else "
        f"{echo_message(failure_message)}; exit 7; "
        "fi; "
        "else "
        "echo '[ERROR] 导航下发通道不可用'; exit 7; "
        "fi; "
    )


def ensure_navigation_helpers_command(profile: ProductProfile) -> CommandSpec:
    inner = (
        f"{remote_env(profile)}; "
        "source /opt/robot/robot_nav/install/setup.bash >/dev/null 2>&1 || true; "
        f"{_prewarm_app_ws_broker_inner()}"
        f"{_ensure_start_navigation_helper_inner()}"
    )
    command = ssh_command(profile, inner)
    return CommandSpec(
        "准备导航通道",
        command,
        display_command="执行：准备导航通道",
        concurrency="parallel",
        locks=("navigation-helper",),
    )


ensure_mode_switch_helper_command = ensure_navigation_helpers_command


def _cleanup_pid_helper_inner(pid_file: str, fifo: str, script: str, log: str, label: str) -> str:
    return (
        f"PID_FILE={quote(pid_file)}; FIFO_PATH={quote(fifo)}; SCRIPT_PATH={quote(script)}; LOG_PATH={quote(log)}; "
        f"HELPER_LABEL={quote(label)}; "
        "PID=$(cat \"$PID_FILE\" 2>/dev/null || true); "
        "if [ -n \"$PID\" ] && kill -0 \"$PID\" 2>/dev/null; then "
        "kill \"$PID\" 2>/dev/null || true; sleep 0.3; "
        "if kill -0 \"$PID\" 2>/dev/null; then kill -9 \"$PID\" 2>/dev/null || true; fi; "
        "fi; "
        "rm -f \"$PID_FILE\" \"$FIFO_PATH\" \"$SCRIPT_PATH\" \"$LOG_PATH\" 2>/dev/null || true; "
    )


def cleanup_navigation_tool_helpers_inner(*, include_ros_daemon: bool = False) -> str:
    marker_script = r"""
kill_marked() {
  marker="$1"
  ps -eo pid=,args= 2>/dev/null | awk -v self=$$ -v marker="$marker" '
    $1 != self && index($0, marker) && ($0 ~ /python3/ || $0 ~ /bash -c/ || $0 ~ /sshpass/ || $0 ~ /ssh /) {print $1}
  ' | sort -u | xargs -r kill 2>/dev/null || true
  sleep 0.2
  ps -eo pid=,args= 2>/dev/null | awk -v self=$$ -v marker="$marker" '
    $1 != self && index($0, marker) && ($0 ~ /python3/ || $0 ~ /bash -c/ || $0 ~ /sshpass/ || $0 ~ /ssh /) {print $1}
  ' | sort -u | xargs -r kill -9 2>/dev/null || true
}
kill_marked dog_remote_tool_pose_stream
kill_marked dog_remote_tool_plan_stream
kill_marked dog_remote_tool_obstacle_stream
kill_marked dog_remote_tool_nav_camera_overlay_stream
kill_marked dog_remote_nav_control_state_pub
rm -f /tmp/dog_remote_tool_pose_stream.py /tmp/dog_remote_tool_plan_stream.py /tmp/dog_remote_tool_obstacle_stream.py /tmp/dog_remote_tool_nav_camera_overlay_stream.py 2>/dev/null || true
"""
    inner = (
        marker_script
        + _cleanup_pid_helper_inner(
            START_NAV_HELPER_PID,
            START_NAV_HELPER_FIFO,
            START_NAV_HELPER_SCRIPT,
            START_NAV_HELPER_LOG,
            "导航下发通道",
        )
        + f"rm -f {quote(MODE_SWITCH_STATE_PID)} /tmp/dog_remote_nav_control_state_pub.log 2>/dev/null || true; "
    )
    if include_ros_daemon:
        inner += (
            "pkill -u \"$(id -u)\" -f 'ros2cli.daemon.daemonize|ros2-daemon --ros-domain-id' 2>/dev/null || true; "
        )
    return inner


def cleanup_navigation_tool_helpers_command(profile: ProductProfile, *, include_ros_daemon: bool = False) -> CommandSpec:
    title = "清理工具导航临时资源"
    if include_ros_daemon:
        title = "清理工具导航临时资源和 ROS 2 后台服务"
    return CommandSpec(
        title,
        ssh_command(profile, cleanup_navigation_tool_helpers_inner(include_ros_daemon=include_ros_daemon)),
        dangerous=include_ros_daemon,
        display_command=f"执行：{title}",
        concurrency="parallel",
        locks=("navigation-cleanup",),
    )
