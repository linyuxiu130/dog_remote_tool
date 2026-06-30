from __future__ import annotations

from pathlib import Path

from dog_remote_tool.core.network_routes import with_route_repair
from dog_remote_tool.core.profiles import ProductProfile
from dog_remote_tool.core.shell import (
    CommandSpec,
    quote,
    remote_target_path,
    rsync_prefix_command,
    ssh_command,
    sudo_run_shell,
)
from dog_remote_tool.modules.mapping.defaults import history_map_path


def delete_history_map_command(profile: ProductProfile, remote_map_pgm: str, save_map_path: str) -> CommandSpec:
    remote_dir = str(Path(remote_map_pgm).parent)
    map_root = save_map_path.rstrip("/")
    history_root = history_map_path(save_map_path).rstrip("/")
    inner = (
        f"TARGET_DIR={quote(remote_dir)}; "
        f"MAP_ROOT={quote(map_root)}; "
        f"HISTORY_ROOT={quote(history_root)}; "
        + sudo_run_shell()
        + "case \"$TARGET_DIR\" in "
        "\"$MAP_ROOT\") DELETE_MODE=root ;; "
        "\"$HISTORY_ROOT\"/*) DELETE_MODE=history ;; "
        "*) echo \"[ERROR] refusing to delete outside map roots: $TARGET_DIR\"; exit 2 ;; "
        "esac; "
        "if [ ! -f \"$TARGET_DIR/map.pgm\" ]; then echo \"[ERROR] map.pgm not found: $TARGET_DIR/map.pgm\"; exit 3; fi; "
        "echo \"[INFO] deleting map: $TARGET_DIR\"; "
        "if [ \"$DELETE_MODE\" = root ]; then "
        "sudo_run rm -f -- \"$TARGET_DIR/map.pgm\" \"$TARGET_DIR/map.yaml\" \"$TARGET_DIR/map.pcd\" \"$TARGET_DIR/map.txt\"; "
        "sudo_run rm -rf -- \"$TARGET_DIR/map.static\"; "
        "if [ -e \"$TARGET_DIR/map.pgm\" ] || [ -e \"$TARGET_DIR/map.yaml\" ] || [ -e \"$TARGET_DIR/map.pcd\" ] || [ -e \"$TARGET_DIR/map.txt\" ] || [ -e \"$TARGET_DIR/map.static\" ]; then "
        "echo '[ERROR] delete failed, files still exist:'; "
        "find \"$TARGET_DIR\" -maxdepth 2 \\( -name 'map.pgm' -o -name 'map.yaml' -o -name 'map.pcd' -o -name 'map.txt' -o -name 'map.static' \\) -print 2>/dev/null | head -20; "
        "exit 5; "
        "fi; "
        "else "
        "sudo_run rm -rf -- \"$TARGET_DIR\"; "
        "if [ -e \"$TARGET_DIR\" ]; then "
        "echo '[ERROR] delete failed, directory still exists:'; "
        "find \"$TARGET_DIR\" -maxdepth 2 -type f -print 2>/dev/null | head -20; "
        "exit 5; "
        "fi; "
        "fi; "
        "echo '[INFO] delete complete'"
    )
    return CommandSpec("删除选中地图", ssh_command(profile, inner), description=remote_dir)


def list_map_pgm_command(profile: ProductProfile, remote_map_path: str) -> str:
    history_root = history_map_path(remote_map_path)
    root = remote_map_path.rstrip("/")
    inner = (
        f"DF_TARGET={quote(root)}; [ -e \"$DF_TARGET\" ] || DF_TARGET=$(dirname \"$DF_TARGET\"); "
        "DF_LINE=$(df -B1 --output=avail,size,pcent,target \"$DF_TARGET\" 2>/dev/null | awk 'NR==2{print $1\"\\t\"$2\"\\t\"$3\"\\t\"$4}'); "
        "if [ -n \"$DF_LINE\" ]; then printf 'DISK\\t%s\\n' \"$DF_LINE\"; fi; "
        f"find {quote(history_root)} -maxdepth 3 -type f -name 'map.pgm' -size +0c -print 2>/dev/null | "
        "while IFS= read -r pgm; do "
        "dir=$(dirname \"$pgm\"); "
        "[ -s \"$dir/map.yaml\" ] || continue; "
        "size=$(du -sb \"$dir\" 2>/dev/null | awk '{print $1}'); "
        "mtime=$(stat -c '%y' \"$pgm\" 2>/dev/null); "
        "ts=$(stat -c '%Y' \"$pgm\" 2>/dev/null); "
        "printf '%s\\t%s\\t%s\\t%s\\n' \"$ts\" \"$mtime\" \"${size:-0}\" \"$pgm\"; "
        "done | sort -nr"
    )
    return ssh_command(profile, inner)


def fetch_map_preview_files_command(profile: ProductProfile, remote_map_pgm: str, local_dir: str) -> str:
    remote_yaml = str(Path(remote_map_pgm).with_name("map.yaml"))
    remote_track = str(Path(remote_map_pgm).with_name("map.txt"))
    remote_static_track = str(Path(remote_map_pgm).parent / "map.static" / "static_map.txt")
    local_static_track = Path(local_dir) / "map.static" / "static_map.txt"
    local_static_tmp = Path(local_dir) / ".static_map.txt.tmp"
    rsync = rsync_prefix_command(profile, options="-a", connect_timeout=20)
    command = (
        f"mkdir -p {quote(local_dir)}; "
        "fetch_required() { "
        "src=\"$1\"; dst=\"$2\"; label=\"$3\"; attempt=1; rc=1; "
        "while [ \"$attempt\" -le 2 ]; do "
        f"if {rsync} \"$src\" \"$dst\"; then return 0; fi; "
        "rc=$?; echo \"[WARN] ${label} 拉取失败，第 ${attempt} 次，返回码 ${rc}\"; "
        "attempt=$((attempt + 1)); [ \"$attempt\" -le 2 ] && sleep 2; "
        "done; return \"$rc\"; "
        "}; "
        f"fetch_required {quote(remote_target_path(profile, remote_map_pgm))} {quote(str(Path(local_dir) / 'map.pgm'))} map.pgm && "
        f"fetch_required {quote(remote_target_path(profile, remote_yaml))} {quote(str(Path(local_dir) / 'map.yaml'))} map.yaml || exit $?; "
        f"{rsync} "
        f"{quote(remote_target_path(profile, remote_track))} {quote(str(Path(local_dir) / 'map.txt'))} >/dev/null 2>&1 || true; "
        f"rm -f {quote(str(local_static_tmp))}; "
        f"if {rsync} "
        f"{quote(remote_target_path(profile, remote_static_track))} {quote(str(local_static_tmp))} >/dev/null 2>&1; then "
        f"mkdir -p {quote(str(local_static_track.parent))}; "
        f"mv -f {quote(str(local_static_tmp))} {quote(str(local_static_track))}; "
        "else "
        f"rm -f {quote(str(local_static_tmp))}; "
        "fi"
    )
    return with_route_repair(profile, command)
