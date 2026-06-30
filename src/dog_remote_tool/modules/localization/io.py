from __future__ import annotations

from pathlib import Path

from dog_remote_tool.core.network_routes import with_route_repair
from dog_remote_tool.core.profiles import ProductProfile
from dog_remote_tool.core.shell import (
    CommandSpec,
    echo_message,
    quote,
    remote_env,
    remote_target_path,
    rsync_prefix_command,
    ssh_command,
)
from dog_remote_tool.modules.mapping.defaults import history_map_path
from dog_remote_tool.modules.localization import streams as localization_streams


REMOTE_POSE_RECORD = "/home/robot/pose_xyz.txt"


def _rsync_pull_command(profile: ProductProfile, connect_timeout: int = 20) -> str:
    return rsync_prefix_command(profile, options="-a", connect_timeout=connect_timeout)


def _rsync_pull_required(
    profile: ProductProfile,
    remote_path: str,
    local_path: str,
    label: str,
    connect_timeout: int = 20,
) -> str:
    rsync = _rsync_pull_command(profile, connect_timeout)
    return (
        "fetch_required() { "
        "src=\"$1\"; dst=\"$2\"; label=\"$3\"; attempt=1; rc=1; "
        "while [ \"$attempt\" -le 2 ]; do "
        f"if {rsync} \"$src\" \"$dst\"; then return 0; fi; "
        "rc=$?; echo \"[WARN] ${label} 拉取失败，第 ${attempt} 次，返回码 ${rc}\"; "
        "attempt=$((attempt + 1)); [ \"$attempt\" -le 2 ] && sleep 2; "
        "done; return \"$rc\"; "
        "}; "
        f"fetch_required {quote(remote_target_path(profile, remote_path))} {quote(local_path)} {quote(label)}"
    )


def _rsync_pull_optional(
    profile: ProductProfile,
    remote_path: str,
    local_path: str,
    connect_timeout: int = 20,
) -> str:
    rsync = _rsync_pull_command(profile, connect_timeout)
    return f"{rsync} {quote(remote_target_path(profile, remote_path))} {quote(local_path)} >/dev/null 2>&1 || true"


def fetch_pose_record_command(
    profile: ProductProfile,
    local_file: str,
    remote_path: str = REMOTE_POSE_RECORD,
) -> CommandSpec:
    local_path = Path(local_file)
    local_latest = local_path.with_name("pose_xyz.txt")
    command = (
        f"mkdir -p {quote(str(local_path.parent))}; "
        f"{_rsync_pull_required(profile, remote_path, str(local_path), 'pose_xyz.txt')} && "
        f"cp -f {quote(str(local_path))} {quote(str(local_latest))} && "
        f"{echo_message(f'[INFO] 定位 pose 记录已回传: {local_path}')}; " + echo_message(f"[INFO] 最新副本: {local_latest}")
    )
    return CommandSpec("回传定位 pose 记录", with_route_repair(profile, command), description=str(local_path), concurrency="parallel")


def fetch_map_files_command(profile: ProductProfile, remote_map_pgm: str, local_pgm: str, local_yaml: str) -> str:
    remote_yaml = str(Path(remote_map_pgm).with_name("map.yaml"))
    remote_track = str(Path(remote_map_pgm).with_name("map.txt"))
    local_dir = str(Path(local_pgm).parent)
    local_track = str(Path(local_pgm).with_name("map.txt"))
    command = (
        f"mkdir -p {quote(local_dir)}; "
        f"{_rsync_pull_required(profile, remote_map_pgm, local_pgm, 'map.pgm')} && "
        f"{_rsync_pull_required(profile, remote_yaml, local_yaml, 'map.yaml')}; "
        f"{_rsync_pull_optional(profile, remote_track, local_track)}"
    )
    return with_route_repair(profile, command)


def list_localization_map_pgm_command(profile: ProductProfile, remote_map_path: str) -> str:
    history_root = history_map_path(remote_map_path)
    inner = (
        f"find {quote(history_root)} -maxdepth 3 -type f -name 'map.pgm' -size +0c -print 2>/dev/null | "
        "while IFS= read -r pgm; do "
        "dir=$(dirname \"$pgm\"); "
        "[ -s \"$dir/map.yaml\" ] || { echo \"SKIP\\tmissing_yaml\\t$pgm\"; continue; }; "
        "[ -s \"$dir/map.pcd\" ] || { echo \"SKIP\\tmissing_pcd\\t$pgm\"; continue; }; "
        "size=$(du -sb \"$dir\" 2>/dev/null | awk '{print $1}'); "
        "mtime=$(stat -c '%y' \"$pgm\" 2>/dev/null); "
        "ts=$(stat -c '%Y' \"$pgm\" 2>/dev/null); "
        "printf '%s\\t%s\\t%s\\t%s\\n' \"$ts\" \"$mtime\" \"${size:-0}\" \"$pgm\"; "
        "done | sort -nr"
    )
    return ssh_command(profile, inner)


def pose_probe_command(profile: ProductProfile) -> str:
    inner = (
        f"{remote_env(profile)}; "
        "source /opt/runtime/env.bash >/dev/null 2>&1 || true; "
        "source /opt/robot/robot_slam/install/setup.bash >/dev/null 2>&1; "
        "MSG=$(timeout 2s ros2 topic echo --once /odom/current_pose --no-daemon 2>/dev/null || true); "
        "printf '%s\n' \"$MSG\" | awk '"
        "BEGIN{inpos=0; inori=0} "
        "/^    position:/{inpos=1; inori=0; next} "
        "/^    orientation:/{inpos=0; inori=1; next} "
        "/^  covariance:/{inpos=0; inori=0; next} "
        "inpos && /^      x:/{px=$2; next} "
        "inpos && /^      y:/{py=$2; next} "
        "inori && /^      x:/{ox=$2; next} "
        "inori && /^      y:/{oy=$2; next} "
        "inori && /^      z:/{oz=$2; next} "
        "inori && /^      w:/{ow=$2; next} "
        "END{"
        "if(px==\"\" || py==\"\"){print \"POSE=unavailable\"; exit} "
        "yaw=atan2(2*(ow*oz+ox*oy), 1-2*(oy*oy+oz*oz)); "
        "print \"POSE=ok\"; print \"X=\" px; print \"Y=\" py; print \"YAW=\" yaw"
        "}'"
    )
    return ssh_command(profile, inner)


def pose_stream_command(profile: ProductProfile) -> str:
    return localization_streams.pose_stream_command(profile)


def navigation_plan_stream_command(profile: ProductProfile) -> str:
    return localization_streams.navigation_plan_stream_command(profile)


def obstacle_stream_command(profile: ProductProfile) -> str:
    return localization_streams.obstacle_stream_command(profile)
