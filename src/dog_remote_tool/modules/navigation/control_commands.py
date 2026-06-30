from __future__ import annotations

from dog_remote_tool.core.profiles import ProductProfile
from dog_remote_tool.core.shell import CommandSpec, echo_message, quote, remote_env, ssh_command
from dog_remote_tool.modules.navigation.helper_commands import (
    _alg_manager_stop_nav_inner,
    _alg_manager_nav_request_inner,
    _alg_manager_control_owner_inner,
    _mode_switch_inner,
    _stop_navigation_loop_inner,
)
from dog_remote_tool.modules.body_navigation_bridge import release_body_navigation_bridge_command

NAVIGATION_CONTROL_LOCKS = ("navigation-control",)


def _navigation_stop_state_probe_inner() -> str:
    return (
        "NAV_STOP_STATE_SEEN=0; NAV_STOP_PRE_ACTIVE=0; "
        "NAV_STOP_MSG=$(timeout 0.7s ros2 topic echo --once /navigation_state --no-daemon 2>/dev/null || true); "
        "NAV_STOP_STATE=$(printf '%s\\n' \"$NAV_STOP_MSG\" | awk '/^state:/ {print $2; exit}'); "
        "NAV_STOP_TASK_STATUS=$(printf '%s\\n' \"$NAV_STOP_MSG\" | awk '/task_status_list:/ {in_list=1; next} in_list && /^[[:space:]]*-[[:space:]]*task_status:/ {print $NF; exit} in_list && /task_status:/ {print $NF; exit} in_list && /^[^[:space:]]/ {in_list=0}'); "
        "if [ -n \"$NAV_STOP_STATE\" ] || [ -n \"$NAV_STOP_TASK_STATUS\" ]; then NAV_STOP_STATE_SEEN=1; fi; "
        "case \"$NAV_STOP_STATE\" in 2|3|100|140|141) NAV_STOP_PRE_ACTIVE=1 ;; esac; "
        "case \"$NAV_STOP_TASK_STATUS\" in 1|2|3) NAV_STOP_PRE_ACTIVE=1 ;; esac; "
    )


def navigation_control_command(
    profile: ProductProfile,
    cmd: int,
    title: str,
    dangerous: bool = True,
    description: str = "会修改远端导航任务状态。",
    source: str = "",
) -> CommandSpec:
    success_message = f"{title}命令已发送"
    if cmd == 4:
        stop_source = source or "manual"
        inner = (
            f"{remote_env(profile)}; "
            "source /opt/robot/robot_nav/install/setup.bash >/dev/null 2>&1 || true; "
            f"printf '%s source=%s title=%s\\n' \"$(date '+%F %T')\" {quote(stop_source)} {quote(title)} >> /tmp/dog_remote_nav_stop_source.log 2>/dev/null || true; "
            f"{_stop_navigation_loop_inner()}"
            f"{_navigation_stop_state_probe_inner()}"
            f"{_alg_manager_stop_nav_inner(timeout_seconds=1.5, fail_on_error=False)}"
            f"{_mode_switch_inner(False, 0.2)}"
            f"{_alg_manager_control_owner_inner('app', timeout_seconds=1.0)}"
            "echo '[INFO] 导航停止已提交，状态刷新交由页面后台完成'; "
        )
    else:
        func = "pause_nav" if cmd == 2 else "continue_nav"
        inner = (
            f"{remote_env(profile)}; "
            "source /opt/robot/robot_nav/install/setup.bash >/dev/null 2>&1 || true; "
            f"{_alg_manager_nav_request_inner(func, timeout_seconds=2.0, fail_on_error=True)}"
            f"{echo_message(f'[INFO] {success_message}')}; "
        )
    command = ssh_command(profile, inner)
    if cmd == 4:
        body_release = release_body_navigation_bridge_command(profile)
        if body_release is not None:
            command = (
                f"( {command} ); "
                "_dog_remote_nav_stop_rc=$?; "
                f"( {body_release.command} ); "
                'exit "$_dog_remote_nav_stop_rc"'
            )
    return CommandSpec(
        title,
        command,
        dangerous=dangerous,
        description=description,
        display_command=f"执行：{title}",
        concurrency="parallel",
        locks=NAVIGATION_CONTROL_LOCKS,
    )


def pause_command(profile: ProductProfile) -> CommandSpec:
    return navigation_control_command(
        profile,
        2,
        "暂停导航",
        dangerous=False,
        description="会暂停当前远端导航任务。",
    )


def continue_command(profile: ProductProfile) -> CommandSpec:
    return navigation_control_command(
        profile,
        3,
        "继续导航",
        dangerous=False,
        description="会继续当前远端导航任务，机器人可能恢复移动。",
    )


def stop_command(profile: ProductProfile, source: str = "manual") -> CommandSpec:
    return navigation_control_command(profile, 4, "停止导航", description="会停止当前远端导航任务。", source=source)
