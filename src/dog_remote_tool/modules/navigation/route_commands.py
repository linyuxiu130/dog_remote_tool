from __future__ import annotations

from pathlib import Path

from dog_remote_tool.core.profiles import ProductProfile
from dog_remote_tool.core.quoting import yaml_string
from dog_remote_tool.core.shell import (
    CommandSpec,
    echo_message,
    quote,
    remote_env,
    scp_pull_command,
    scp_push_command,
    ssh_command,
    sudo_run_shell,
)
from dog_remote_tool.modules.navigation import route_pose_commands as _route_pose_commands


DEFAULT_REMOTE_ROUTE_DIR = "/ota/alg_data/map"
DEFAULT_REMOTE_ROUTE_FILE = DEFAULT_REMOTE_ROUTE_DIR + "/map.geojson"
UPDATE_GRAPH_SERVICE = "/RouteGraphPlanner/update_graph"
UPDATE_GRAPH_TYPE = "robots_dog_msgs/srv/UpdateGraph"
ROUTE_GRAPH_TOPIC = "/navigo/ps/rp/vis/route_graph"


CurrentPose = _route_pose_commands.CurrentPose
current_pose_command = _route_pose_commands.current_pose_command
parse_current_pose_output = _route_pose_commands.parse_current_pose_output
current_pose_failure_message = _route_pose_commands.current_pose_failure_message


def list_route_file_command(profile: ProductProfile, remote_route_file: str = DEFAULT_REMOTE_ROUTE_FILE) -> str:
    inner = (
        f"ROUTE_FILE={quote(remote_route_file)}; "
        "if [ -s \"$ROUTE_FILE\" ]; then "
        "stat -c 'ROUTE\\t%y\\t%s\\t%n' \"$ROUTE_FILE\"; "
        "else echo 'MISSING\\t0\\t0\\t'\"$ROUTE_FILE\"; fi"
    )
    return ssh_command(profile, inner)


def pull_route_file_command(profile: ProductProfile, remote_route_file: str, local_file: str) -> CommandSpec:
    command = (
        f"mkdir -p {quote(str(Path(local_file).parent))}; "
        f"{scp_pull_command(profile, remote_route_file, local_file)}"
    )
    return CommandSpec("拉取路网 GeoJSON", command, description=remote_route_file, concurrency="parallel")


def upload_route_file_command(profile: ProductProfile, local_file: str, remote_route_file: str = DEFAULT_REMOTE_ROUTE_FILE) -> CommandSpec:
    remote_dir = str(Path(remote_route_file).parent)
    temp_file = f"{profile.home.rstrip('/')}/map.geojson.uploading"
    remote_install = (
        sudo_run_shell()
        + f"sudo_run install -d -m 0755 {quote(remote_dir)} && "
        f"sudo_run install -m 0644 {quote(temp_file)} {quote(remote_route_file)} && "
        f"rm -f {quote(temp_file)} && "
        f"ls -lh {quote(remote_route_file)}"
    )
    command = (
        f"test -s {quote(local_file)} || {{ {echo_message(f'[ERROR] 本地路网文件不存在或为空: {local_file}')}; exit 2; }}; "
        f"{scp_push_command(profile, local_file, temp_file)} && "
        f"{ssh_command(profile, remote_install)}"
    )
    return CommandSpec("上传路网 GeoJSON", command, description=remote_route_file, concurrency="parallel")


def upload_map_route_files_command(
    profile: ProductProfile,
    local_pgm: str,
    local_yaml: str,
    local_route: str,
    remote_map_pgm: str,
) -> CommandSpec:
    remote_dir = str(Path(remote_map_pgm).parent)
    remote_yaml = str(Path(remote_map_pgm).with_name("map.yaml"))
    remote_route = str(Path(remote_map_pgm).with_name("map.geojson"))
    temp_dir = f"{profile.home.rstrip('/')}/dog_remote_tool_map_route_upload"
    prepare = ssh_command(profile, f"rm -rf {quote(temp_dir)} && mkdir -p {quote(temp_dir)}")
    upload_pgm = scp_push_command(profile, local_pgm, temp_dir + "/map.pgm")
    upload_yaml = scp_push_command(profile, local_yaml, temp_dir + "/map.yaml")
    upload_route = scp_push_command(profile, local_route, temp_dir + "/map.geojson")
    remote_install = (
        sudo_run_shell()
        + f"sudo_run install -d -m 0755 {quote(remote_dir)} && "
        f"sudo_run install -m 0644 {quote(temp_dir + '/map.pgm')} {quote(remote_map_pgm)} && "
        f"sudo_run install -m 0644 {quote(temp_dir + '/map.yaml')} {quote(remote_yaml)} && "
        f"sudo_run install -m 0644 {quote(temp_dir + '/map.geojson')} {quote(remote_route)} && "
        f"rm -rf {quote(temp_dir)} && "
        f"ls -lh {quote(remote_map_pgm)} {quote(remote_yaml)} {quote(remote_route)}"
    )
    command = (
        f"test -s {quote(local_pgm)} || {{ {echo_message(f'[ERROR] 本地 map.pgm 不存在或为空: {local_pgm}')}; exit 2; }}; "
        f"test -s {quote(local_yaml)} || {{ {echo_message(f'[ERROR] 本地 map.yaml 不存在或为空: {local_yaml}')}; exit 2; }}; "
        f"test -s {quote(local_route)} || {{ {echo_message(f'[ERROR] 本地路网文件不存在或为空: {local_route}')}; exit 2; }}; "
        f"{prepare} && {upload_pgm} && {upload_yaml} && {upload_route} && {ssh_command(profile, remote_install)}"
    )
    return CommandSpec("上传地图和路网文件", command, description=remote_dir, concurrency="parallel")


def update_graph_command(profile: ProductProfile, remote_route_file: str = DEFAULT_REMOTE_ROUTE_FILE) -> CommandSpec:
    payload = "{filepath: " + yaml_string(remote_route_file) + "}"
    inner = (
        f"{remote_env(profile)}; "
        "source /opt/runtime/env.bash >/dev/null 2>&1 || true; "
        "source /opt/robot/robot_nav/install/setup.bash >/dev/null 2>&1 || true; "
        f"if [ ! -s {quote(remote_route_file)} ]; then "
        f"{echo_message(f'[ERROR] 远端路网 GeoJSON 不存在: {remote_route_file}')}; "
        "echo '[INFO] 建图轨迹 map.txt 不能直接作为路网加载，请先在路网编辑器生成并上传 map.geojson'; "
        "exit 2; fi; "
        f"if ! timeout 4s ros2 service list --no-daemon 2>/dev/null | grep -Fx -- {quote(UPDATE_GRAPH_SERVICE)} >/dev/null; then "
        f"{echo_message(f'[ERROR] {UPDATE_GRAPH_SERVICE} 未就绪')}; exit 3; fi; "
        f"timeout 20s ros2 service call {quote(UPDATE_GRAPH_SERVICE)} {quote(UPDATE_GRAPH_TYPE)} {quote(payload)}"
    )
    return CommandSpec("加载路网到导航栈", ssh_command(profile, inner), description=remote_route_file, concurrency="parallel")


def route_status_command(profile: ProductProfile, remote_route_file: str = DEFAULT_REMOTE_ROUTE_FILE) -> str:
    inner = (
        f"ROUTE_FILE={quote(remote_route_file)}; "
        "[ -s \"$ROUTE_FILE\" ] && echo ROUTE_FILE_OK=1 || echo ROUTE_FILE_OK=0; "
        "echo ROUTE_FILE=$ROUTE_FILE"
    )
    return ssh_command(profile, inner)


def route_file_exists_command(profile: ProductProfile, remote_route_file: str = DEFAULT_REMOTE_ROUTE_FILE) -> str:
    inner = (
        f"ROUTE_FILE={quote(remote_route_file)}; "
        "[ -s \"$ROUTE_FILE\" ] && echo ROUTE_FILE_OK=1 || echo ROUTE_FILE_OK=0; "
        "echo ROUTE_FILE=$ROUTE_FILE"
    )
    return ssh_command(profile, inner)


def route_status_spec(profile: ProductProfile, remote_route_file: str = DEFAULT_REMOTE_ROUTE_FILE) -> CommandSpec:
    return CommandSpec("检查路网状态", route_status_command(profile, remote_route_file), description=remote_route_file, concurrency="parallel")
