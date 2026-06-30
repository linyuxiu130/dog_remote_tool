from __future__ import annotations

from pathlib import Path
from typing import Callable

from dog_remote_tool.core.profiles import ProductProfile
from dog_remote_tool.core.shell import (
    CommandSpec,
    echo_message,
    quote,
    rsync_push_command,
    scp_push_command,
    ssh_command,
    sudo_run_shell,
)
from dog_remote_tool.modules.remote_access import public as _public
from dog_remote_tool.modules.remote_access.resources import COMMUNITY_NODE_DEB_NAME, bundled_or_downloads_resource


PUBLIC_SERVER = _public.PUBLIC_SERVER
NX_REMOTE_SCRIPT_PATH = _public.REMOTE_SCRIPT_INSTALL_PATH
NX_REMOTE_SCRIPT_DIR = str(Path(NX_REMOTE_SCRIPT_PATH).parent)


def default_community_node_deb() -> str:
    return bundled_or_downloads_resource("DOG_REMOTE_TOOL_COMMUNITY_NODE_DEB", COMMUNITY_NODE_DEB_NAME)


NX_COMMUNITY_NODE_DEB = default_community_node_deb()


def internet_check_command(profile: ProductProfile) -> CommandSpec:
    inner = (
        "printf '[target]\\n'; hostname; date; "
        "printf '\\n[ip addr]\\n'; ip -br addr || true; "
        "printf '\\n[default route]\\n'; ip route | sed -n '1,8p' || true; "
        "printf '\\n[dns]\\n'; "
        "cat /etc/resolv.conf 2>/dev/null | sed -n '1,8p' || true; "
        "printf '\\n[public server tcp]\\n'; "
        + _public.public_server_tcp_check_shell()
        + f"PORT_MANAGER=fail; FRP_SERVER=fail; "
        f"if check_public_tcp {quote(PUBLIC_SERVER)} {quote(_public.PUBLIC_PORT_MANAGER_PORT)}; then PORT_MANAGER=ok; fi; "
        f"if check_public_tcp {quote(PUBLIC_SERVER)} {quote(_public.PUBLIC_FRP_SERVER_PORT)}; then FRP_SERVER=ok; fi; "
        f"printf '端口管理 {PUBLIC_SERVER}:{_public.PUBLIC_PORT_MANAGER_PORT} %s\\n' \"$PORT_MANAGER\"; "
        f"printf 'FRP 服务 {PUBLIC_SERVER}:{_public.PUBLIC_FRP_SERVER_PORT} %s\\n' \"$FRP_SERVER\"; "
        "printf '\\n[dns name]\\n'; "
        "if timeout 4 getent hosts www.baidu.com >/dev/null 2>&1; then "
        "DNS_STATE=ok; printf 'DNS 解析 ok\\n'; "
        "else DNS_STATE=fail; printf 'DNS 解析 fail（remote_access 使用公网 IP，不影响启动）\\n'; fi; "
        "printf '\\n[public ip]\\n'; "
        "if ping -c 2 -W 2 8.8.8.8 >/dev/null 2>&1; then "
        "IP_STATE=ok; printf '公网 IP ping ok\\n'; "
        "else IP_STATE=fail; printf '公网 IP ping fail\\n'; fi; "
        "if [ \"$PORT_MANAGER\" = ok ] || [ \"$FRP_SERVER\" = ok ]; then "
        "printf '\\n[判断] 公网服务器端口可达，可启动 remote_access/FRP。DNS=%s，公网 IP=%s。\\n' \"$DNS_STATE\" \"$IP_STATE\"; "
        "elif [ \"$IP_STATE\" = ok ]; then "
        "printf '\\n[判断] 普通公网 IP 可达，但智航公网服务器端口不可达；请检查服务器端口、防火墙或网络策略。DNS=%s。\\n' \"$DNS_STATE\"; "
        "else "
        "printf '\\n[判断] 当前设备没有可用外网路由。FRP/remote_access 需要 RK3588 或 NX 至少一侧能上网；"
        "如需 FRP 5G 映射，请确认当前选择的是 NX 192.168.234.234，或先让当前设备连接 WiFi/4G/5G。\\n'; "
        "fi; true"
    )
    return CommandSpec("检查外网", ssh_command(profile, inner))


def replace_remote_access_script_command(
    profile: ProductProfile,
    script_path_resolver: Callable[[], str] = _public.default_remote_access_script_path,
) -> CommandSpec:
    local_script = script_path_resolver()
    tmp_script = f"/tmp/dog_remote_replace_start_remote_access_{profile.user}.sh"
    upload_script = scp_push_command(profile, local_script, tmp_script, connect_timeout=6)
    replace = (
        "set -e; "
        + _public.remote_version_shell()
        + "printf '[版本] /etc/release/%s，类型=%s\\n' \"${RELEASE_FILE:-unknown}\" \"$VERSION_KIND\"; "
        "if [ \"$VERSION_KIND\" != new ]; then "
        "printf '[跳过] 当前不是 0.2.9(B)+，不替换 robot-launch 脚本。\\n'; "
        "exit 1; "
        "fi; "
        f"SRC={quote(tmp_script)}; DST={quote(NX_REMOTE_SCRIPT_PATH)}; "
        + sudo_run_shell(fallback_without_sudo=False)
        + f"sudo_run install -d -m 0755 {quote(NX_REMOTE_SCRIPT_DIR)} >/dev/null; "
        "src_sha=$(sha256sum \"$SRC\" | awk '{print $1}'); "
        "dst_sha=$(if [ -f \"$DST\" ]; then sha256sum \"$DST\" | awk '{print $1}'; else printf missing; fi); "
        "printf '[检查] 本地脚本=%s\\n' \"$src_sha\"; "
        "printf '[检查] 远程脚本=%s\\n' \"$dst_sha\"; "
        "if [ \"$src_sha\" = \"$dst_sha\" ]; then "
        "printf '[完成] 远程脚本已是最新，无需替换。\\n'; rm -f \"$SRC\"; exit 0; "
        "fi; "
        "ts=$(date +%Y%m%d_%H%M%S); "
        "backup=\"$DST.bak.$ts\"; "
        "if [ -f \"$DST\" ]; then "
        "sudo_run cp \"$DST\" \"$backup\" >/dev/null; "
        "printf '[备份] %s\\n' \"$backup\"; "
        "else "
        "printf '[备份] 原脚本不存在，跳过备份。\\n'; "
        "fi; "
        "sudo_run install -m 0755 \"$SRC\" \"$DST\" >/dev/null; "
        "rm -f \"$SRC\"; "
        "printf '[完成] 已替换 %s\\n' \"$DST\"; "
        "sha256sum \"$DST\"; "
        "ls -l \"$DST\""
    )
    command = (
        "set -e; "
        f"test -f {quote(local_script)} || ({echo_message(f'[失败] 工具内置脚本不存在：{local_script}')}; exit 1); "
        f"printf '[目标] {profile.label} {profile.target}\\n'; "
        f"{upload_script}; "
        f"{ssh_command(profile, replace)}"
    )
    return CommandSpec("替换远程脚本", command, dangerous=True)


def start_remote_access_command(profile: ProductProfile) -> CommandSpec:
    inner = (
        "if command -v robot-launch >/dev/null 2>&1; then "
        "robot-launch start remote_access; "
        f"else bash {quote(NX_REMOTE_SCRIPT_PATH)}; fi"
    )
    return CommandSpec("启动 remote_access", ssh_command(profile, inner), dangerous=True)


def status_command(profile: ProductProfile) -> CommandSpec:
    inner = (
        _public.remote_version_shell()
        + "printf '[version]\\n/etc/release/%s (%s)\\n' \"${RELEASE_FILE:-unknown}\" \"$VERSION_KIND\"; "
        "printf '\\n[robot-launch remote_access]\\n'; "
        "if command -v robot-launch >/dev/null 2>&1; then "
        "robot-launch list 2>/dev/null | sed -r 's/\\x1B\\[[0-9;]*[A-Za-z]//g' | grep remote_access || true; "
        "else printf 'robot-launch not found\\n'; fi; "
        "printf '[remote_access/frpc process]\\n'; "
        "found=0; "
        "pgrep -x remote_access >/dev/null 2>&1 && { pgrep -af '^remote_access( |$)'; found=1; }; "
        "pgrep -af '^/opt/frp-client/frpc( |$)' && found=1 || true; "
        "pgrep -af '[s]tart_remote_access' && found=1 || true; "
        "[ \"$found\" = 1 ] || printf '未发现 remote_access/frpc 进程\\n'; "
        "printf '\\n[listening tcp ports]\\n'; "
        "ss -lntp || true"
    )
    return CommandSpec("远程访问状态", ssh_command(profile, inner))


def deploy_nx_remote_access_script_command(
    profile: ProductProfile, local_script: str = _public.default_remote_access_script_path()
) -> CommandSpec:
    script = local_script.strip() or _public.default_remote_access_script_path()
    if not Path(script).is_absolute():
        script = _public.default_remote_access_script_path()
    remote_name = Path(script).name
    upload = rsync_push_command(profile, script, "~/")
    remote = ssh_command(
        profile,
        "set -e; "
        + sudo_run_shell(fallback_without_sudo=False)
        + f"sudo_run install -m 0755 ~/{quote(remote_name)} "
        f"{quote(NX_REMOTE_SCRIPT_PATH)} >/dev/null; "
        f"sha256sum {quote(NX_REMOTE_SCRIPT_PATH)}; "
        f"ls -l {quote(NX_REMOTE_SCRIPT_PATH)}",
    )
    return CommandSpec("部署 NX 远程 SSH 脚本", f"{upload} && {remote}", dangerous=True)


def install_community_node_command(
    profile: ProductProfile, local_deb: str | None = None
) -> CommandSpec:
    local_deb = (local_deb or NX_COMMUNITY_NODE_DEB).strip() or NX_COMMUNITY_NODE_DEB
    remote_deb = f"{profile.home.rstrip('/')}/{Path(local_deb).name}"
    public_server_pattern = PUBLIC_SERVER.replace(".", "\\.")
    upload = rsync_push_command(profile, local_deb, "~/")
    remote = ssh_command(
        profile,
        "set -e; "
        f"sudo dpkg -i {quote(remote_deb)}; "
        "dpkg -l | grep community-node || true; "
        "printf '\\n[config server]\\n'; "
        f"grep -nE {quote(public_server_pattern + '|9000')} /ota/community_node/config/config.yaml || true",
    )
    return CommandSpec("安装 NX community-node", f"{upload} && {remote}", dangerous=True)


def nx_robot_launch_status_command(profile: ProductProfile) -> CommandSpec:
    inner = (
        "robot-launch egg 27 || true; "
        "robot-launch egg 28 || true; "
        "printf '\\n[community-node]\\n'; "
        "dpkg -l | grep community-node || true"
    )
    return CommandSpec("NX 远程控制状态", ssh_command(profile, inner), concurrency="parallel")
