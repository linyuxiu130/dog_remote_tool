from __future__ import annotations

from pathlib import Path

from dog_remote_tool.core.profiles import ProductProfile
from dog_remote_tool.core.shell import echo_message, quote, remote_env


def pose_record_env(profile: ProductProfile) -> str:
    return (
        f"{remote_env(profile)}; "
        "source /opt/runtime/env.bash >/dev/null 2>&1 || true; "
        "source /opt/robot/robot_slam/install/setup.bash >/dev/null 2>&1"
    )


def stop_pose_record_inner(remote_pid: str) -> str:
    return (
        f"if [ -f {quote(remote_pid)} ]; then "
        f"POSE_PID=$(cat {quote(remote_pid)} 2>/dev/null || true); "
        "if [ -n \"$POSE_PID\" ]; then "
        "kill -INT -- -\"$POSE_PID\" 2>/dev/null || kill -INT \"$POSE_PID\" 2>/dev/null || true; "
        "sleep 1; "
        "kill -TERM -- -\"$POSE_PID\" 2>/dev/null || true; "
        "fi; "
        f"rm -f {quote(remote_pid)}; "
        "fi"
    )


def start_pose_record_inner(
    profile: ProductProfile,
    remote_path: str,
    remote_pid: str,
    remote_log: str,
) -> str:
    env = pose_record_env(profile)
    csv_filter = (
        "awk -F, '"
        "NF>=3 { "
        "ok=1; "
        "for (i=1; i<=3; i++) { "
        "gsub(/^[ \t]+|[ \t]+$/, \"\", $i); "
        "if ($i !~ /^-?([0-9]+([.][0-9]*)?|[.][0-9]+)([eE][-+]?[0-9]+)?$/) ok=0; "
        "} "
        "if (ok) { print $1 \",\" $2 \",\" $3; fflush(); } "
        "}'"
    )
    record_inner = (
        f"{env}; "
        f"ros2 topic echo /odom/localization_odom --field pose.pose.position --csv --no-daemon "
        f"2>> {quote(remote_log)} | {csv_filter} > {quote(remote_path)}"
    )
    return (
        f"{stop_pose_record_inner(remote_pid)}; "
        f"mkdir -p {quote(str(Path(remote_path).parent))}; "
        f"rm -f {quote(remote_path)}; "
        f"setsid bash -lc {quote(record_inner)} > {quote(remote_log)} 2>&1 < /dev/null & "
        f"echo $! > {quote(remote_pid)}; " + echo_message(f"[INFO] 定位 pose 记录已启动: {remote_path}")
    )
