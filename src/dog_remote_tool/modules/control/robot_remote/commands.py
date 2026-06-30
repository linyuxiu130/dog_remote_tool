from __future__ import annotations

from dog_remote_tool.core.profiles import ProductProfile
from dog_remote_tool.core.shell import CommandSpec, echo_message, quote
import dog_remote_tool.modules.control.l2_telemetry as _control_l2_telemetry
import dog_remote_tool.modules.control.shared as _control_shared


ROBOT_REMOTE_COMMANDS = {
    "stand_up": ("站立", "action/stand_up"),
    "lie_down": ("趴下", "action/lie_down"),
    "stand": ("站立", "action/stand_up"),
    "lie": ("趴下", "action/lie_down"),
    "crawl": ("匍匐", "action/crawl"),
    "head": ("原地", "mode/in_place"),
    "general": ("通用", "mode/general"),
}


def robot_remote_probe_command(profile: ProductProfile) -> CommandSpec:
    robot_remote_target = _control_shared.robot_remote_control_profile(profile)
    target = robot_remote_target or _control_shared.l2_control_profile(profile) or profile
    read_only = " --read-only" if robot_remote_target is not None else ""
    command = (
        f"{_control_shared.tool_cli()} --robot-remote probe "
        f"--host {quote(target.host)} --port 8081 --timeout 3{read_only}"
    )
    return CommandSpec(
        "robot_remote 协议检查",
        command,
        display_command="执行：遥控协议检查",
        concurrency="parallel",
    )


def robot_remote_posture_command(profile: ProductProfile, posture: str) -> CommandSpec:
    target = _control_shared.robot_remote_control_profile(profile) or _control_shared.l2_control_profile(profile) or profile
    label, remote_command = ROBOT_REMOTE_COMMANDS[posture]
    restore_roamerx = _control_shared.robot_remote_restore_occupancy_command(profile)
    command = (
        f"{_control_shared.arc_charging_guard_command(profile)}\n"
        "_dog_remote_restore_roamerx() {\n"
        f"{restore_roamerx}\n"
        "}\n"
        "trap _dog_remote_restore_roamerx EXIT INT TERM\n"
        f"{_control_shared.robot_remote_occupancy_guard_command(profile)}\n"
        f"{_control_shared.tool_cli()} --robot-remote posture "
        f"--host {quote(target.host)} --port 8081 --timeout 3 --cmd {quote(remote_command)}"
    )
    return CommandSpec(
        f"robot_remote {label}",
        command,
        dangerous=True,
        display_command=f"执行：遥控动作 {label}",
    )


def robot_sdk_posture_command(profile: ProductProfile, action: str) -> CommandSpec:
    target = _control_shared.robot_remote_control_profile(profile)
    if target is None:
        return CommandSpec(
            "RobotSDK 协议控制",
            "echo '[ERROR] 当前设备未适配 robot_remote 协议控制。'",
            dangerous=False,
        )
    if action in {"status", "neutral"}:
        return CommandSpec(
            "RobotSDK 停止移动",
            (
                f"{_control_shared.tool_cli()} --robot-remote stream "
                f"--host {quote(target.host)} --port 8081 --timeout 3 --axis-limit 5 --interval 0.02 --no-general <<'EOF'\n"
                '{"cmd":"neutral"}\n{"cmd":"quit"}\nEOF'
            ),
            dangerous=False,
            display_command="执行：停止移动",
        )
    if action not in ROBOT_REMOTE_COMMANDS:
        return CommandSpec("RobotSDK 协议控制", echo_message(f"[ERROR] 未知动作: {action}"), dangerous=False)
    return robot_remote_posture_command(profile, action)


def robot_sdk_stream_command(profile: ProductProfile, axis_limit: int = 100, interval_ms: int = 20) -> str:
    target = _control_shared.robot_remote_control_profile(profile)
    if target is None:
        return "echo '[ERROR] 当前设备未适配 robot_remote 键盘遥控。'; exit 2"
    percent_limit = max(5, min(abs(int(axis_limit)), 100))
    interval = max(0.02, min(float(interval_ms) / 1000.0, 0.10))
    restore_roamerx = _control_shared.robot_remote_restore_occupancy_command(profile)
    restart_robot_remote = _control_shared.robot_remote_restart_command(profile)
    recover_control = _control_shared.robot_remote_realtime_prepare_command(profile)
    preflight_control = (
        f"{recover_control}\n_dog_remote_needs_restore_roamerx=1\n"
        if getattr(profile, "key", "").startswith("zg")
        else ""
    )
    stream_command = (
        f"{_control_shared.tool_cli()} --robot-remote stream "
        f"--host {quote(target.host)} --port 8081 --timeout 2 "
        f"--axis-limit {percent_limit} --interval {interval:.3f}"
    )
    command = (
        "_dog_remote_needs_restore_roamerx=0\n"
        "_dog_remote_restore_roamerx() {\n"
        "if [ \"$_dog_remote_needs_restore_roamerx\" = 1 ]; then\n"
        f"{restore_roamerx}\n"
        "fi\n"
        "}\n"
        "trap _dog_remote_restore_roamerx EXIT INT TERM\n"
        f"{preflight_control}"
        "_dog_remote_stream_log=$(mktemp /tmp/dog_remote_robot_remote_stream.XXXXXX)\n"
        "_dog_remote_run_stream() {\n"
        f"  {stream_command}\n"
        "}\n"
        "set +e\n"
        "_dog_remote_retry_pattern='another master exists|获取控制权.*被拒绝|take[ _-]?control.*(refused|rejected|failed)|control.*(occupied|busy|占用)|master.*(exists|already|占用)|occupied|busy|占用'\n"
        "_dog_remote_run_stream 2>&1 | tee \"$_dog_remote_stream_log\"\n"
        "_dog_remote_rc=${PIPESTATUS[0]}\n"
        "if [ \"$_dog_remote_rc\" -ne 0 ] && grep -Eqi \"$_dog_remote_retry_pattern\" \"$_dog_remote_stream_log\"; then\n"
        "  printf '%s\\n' '[实时遥控] 清理上次未释放的 robot_remote 控制状态后重试。'\n"
        f"  {recover_control}\n"
        f"  {restart_robot_remote}\n"
        "  _dog_remote_needs_restore_roamerx=1\n"
        "  : > \"$_dog_remote_stream_log\"\n"
        "  _dog_remote_run_stream 2>&1 | tee \"$_dog_remote_stream_log\"\n"
        "  _dog_remote_rc=${PIPESTATUS[0]}\n"
        "fi\n"
        "rm -f \"$_dog_remote_stream_log\"\n"
        "exit \"$_dog_remote_rc\""
    )
    return command


def body_realtime_stream_command(profile: ProductProfile, axis_limit: int = 100, interval_ms: int = 20) -> str:
    if _control_shared.robot_remote_control_profile(profile) is not None:
        return robot_sdk_stream_command(profile, axis_limit, interval_ms)
    return "echo '[ERROR] 当前设备未适配 robot_remote 键盘遥控。'; exit 2"


def robot_sdk_body_telemetry_stream_command(profile: ProductProfile, interval_ms: int = 250) -> str:
    target = _control_shared.robot_remote_control_profile(profile)
    if target is None:
        return "echo '{\"type\":\"error\",\"message\":\"当前设备未适配 robot_remote，无法读取本体速度。\"}'; exit 2"
    interval = max(0.1, min(float(interval_ms) / 1000.0, 2.0))
    return _control_l2_telemetry.build_l2_body_telemetry_stream_command(target, interval)
