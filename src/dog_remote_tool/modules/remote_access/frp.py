from __future__ import annotations

from dog_remote_tool.core.paths import app_root as _core_app_root
from dog_remote_tool.core.profiles import ProductProfile
from dog_remote_tool.core.shell import (
    CommandSpec,
    quote,
    rsync_push_command,
    ssh_command,
    ssh_options,
    ssh_prefix_command,
    sshpass_command,
    sudo_run_shell,
)
from dog_remote_tool.modules.remote_access import public as _public
from dog_remote_tool.modules.remote_access.resources import FRP_ZIP_NAME, bundled_or_downloads_resource


app_root = _core_app_root


def default_frp_zip() -> str:
    return bundled_or_downloads_resource("DOG_REMOTE_TOOL_FRP_ZIP", FRP_ZIP_NAME)


LOCAL_FRP_ZIP = default_frp_zip()
PUBLIC_SERVER = _public.PUBLIC_SERVER
FRPC_LOG = "/opt/frp-client/frpc.log"


def deploy_command(profile: ProductProfile, local_zip: str | None = None) -> CommandSpec:
    local_zip = local_zip or LOCAL_FRP_ZIP
    upload = rsync_push_command(profile, local_zip, "~/", options="-a")
    remote = ssh_command(
        profile,
        "set -e; rm -rf ~/frp_sevice; unzip -oq ~/frp_sevice.zip -d ~/; "
        "cd ~/frp_sevice/client; sudo bash deploy_connector.sh",
    )
    return CommandSpec("部署 FRP", f"{upload} && {remote}", dangerous=True)


def generate_config_command(profile: ProductProfile) -> CommandSpec:
    inner = "sudo python3 /opt/frp-client/frp_client_connector.py -g"
    return CommandSpec("申请公网端口", ssh_command(profile, inner), dangerous=True)


def start_frpc_command(profile: ProductProfile) -> CommandSpec:
    inner = "sudo /opt/frp-client/frpc -c /opt/frp-client/frpc.toml"
    return CommandSpec("启动 frpc", ssh_command(profile, inner), dangerous=True)


def start_frpc_background_command(profile: ProductProfile) -> CommandSpec:
    inner = (
        "set -e; "
        + sudo_run_shell(fallback_without_sudo=False)
        + "port=$(awk -F= '/remotePort/ {gsub(/[[:space:]]/, \"\", $2); print $2; exit}' /opt/frp-client/frpc.toml); "
        "old_pids=$(pgrep -f '^/opt/frp-client/frpc -c /opt/frp-client/frpc.toml$' || true); "
        "if [ -n \"$old_pids\" ]; then sudo_run kill $old_pids || true; sleep 1; fi; "
        f"sudo_run sh -c {quote(f'nohup /opt/frp-client/frpc -c /opt/frp-client/frpc.toml > {FRPC_LOG} 2>&1 &')}; "
        "sleep 1; "
        "if ! pgrep -f '^/opt/frp-client/frpc -c /opt/frp-client/frpc.toml$' >/dev/null; then "
        "printf 'frpc 启动失败，请查看 %s\\n' '/opt/frp-client/frpc.log'; exit 1; "
        "fi; "
        f"printf 'FRP 已后台启动\\n公网端口: %s\\n连接命令: ssh robot@{PUBLIC_SERVER} -p %s\\n' \"$port\" \"$port\""
    )
    return CommandSpec("后台启动 frpc", ssh_command(profile, inner), dangerous=True)


def auto_deploy_start_command(profile: ProductProfile, local_zip: str | None = None) -> CommandSpec:
    local_zip = local_zip or LOCAL_FRP_ZIP
    upload = rsync_push_command(profile, local_zip, "~/", options="-a")
    remote_inner = (
        "set -e; "
        + sudo_run_shell(fallback_without_sudo=False)
        + "rm -rf ~/frp_sevice; "
        "unzip -oq ~/frp_sevice.zip -d ~/; "
        "cd ~/frp_sevice/client; "
        "sudo_run bash deploy_connector.sh; "
        "sudo_run python3 /opt/frp-client/frp_client_connector.py -g; "
        "port=$(awk -F= '/remotePort/ {gsub(/[[:space:]]/, \"\", $2); print $2; exit}' /opt/frp-client/frpc.toml); "
        "active_port=''; "
        "if pgrep -f '^remote_access -c /tmp/frpc_.*\\.toml$' >/dev/null 2>&1; then "
        "active_port=$(awk -F= '/remotePort/ {gsub(/[[:space:]]/, \"\", $2); print $2; exit}' /tmp/frpc_*.toml 2>/dev/null || true); "
        "fi; "
        "if [ -n \"$port\" ] && [ \"$port\" = \"$active_port\" ]; then "
        f"printf '公网端口: %s\\n端口已由 robot-launch remote_access 使用，未重复启动 frpc。\\n连接命令: ssh robot@{PUBLIC_SERVER} -p %s\\n' \"$port\" \"$port\"; "
        "exit 0; "
        "fi; "
        "old_pids=$(pgrep -f '^/opt/frp-client/frpc -c /opt/frp-client/frpc.toml$' || true); "
        "if [ -n \"$old_pids\" ]; then sudo_run kill $old_pids || true; sleep 1; fi; "
        f"sudo_run sh -c {quote(f'nohup /opt/frp-client/frpc -c /opt/frp-client/frpc.toml > {FRPC_LOG} 2>&1 &')}; "
        "sleep 1; "
        "if ! pgrep -f '^/opt/frp-client/frpc -c /opt/frp-client/frpc.toml$' >/dev/null; then "
        "printf 'frpc 启动失败，请查看 %s\\n' '/opt/frp-client/frpc.log'; exit 1; "
        "fi; "
        f"printf 'FRP 已后台启动\\n公网端口: %s\\n连接命令: ssh robot@{PUBLIC_SERVER} -p %s\\n' \"$port\" \"$port\""
    )
    remote = ssh_command(profile, remote_inner)
    return CommandSpec("一键部署并后台启动 FRP", f"{upload} && {remote}", dangerous=True)


def frpc_status_command(profile: ProductProfile) -> CommandSpec:
    inner = (
        sudo_run_shell(fallback_without_sudo=False)
        + "printf '[robot-launch remote_access]\\n'; "
        "pgrep -af '^remote_access -c /tmp/frpc_.*\\.toml$' || true; "
        "printf '\\n[manual /opt/frp-client/frpc]\\n'; "
        "pgrep -af '^/opt/frp-client/frpc -c /opt/frp-client/frpc.toml$' || true; "
        "printf '\\n[frpc.toml remotePort]\\n'; "
        "grep -n 'remotePort' /opt/frp-client/frpc.toml || true; "
        "printf '\\n[remote_access remotePort]\\n'; "
        "grep -n 'remotePort' /tmp/frpc_*.toml 2>/dev/null || true; "
        f"printf '\\n[{FRPC_LOG} tail]\\n'; "
        f"sudo_run tail -n 50 {quote(FRPC_LOG)} || true"
    )
    return CommandSpec("FRP 状态", ssh_command(profile, inner))


def external_ssh_command(profile: ProductProfile) -> CommandSpec:
    public_options = ssh_options(connect_timeout=8)
    pass_cmd = sshpass_command(profile.password)
    public_user = profile.user
    read_port = (
        "for file in /tmp/frpc_*.toml /opt/frp-client/frpc.toml; do "
        "[ -r \"$file\" ] || continue; "
        "port=$(awk -F= '/remotePort/ {gsub(/[[:space:]]/, \"\", $2); print $2; exit}' \"$file\"); "
        "if [ -n \"$port\" ]; then printf '%s\\n' \"$port\"; exit 0; fi; "
        "done; "
        "exit 1"
    )
    public_probe = (
        "printf 'ONLINE\\nhost=%s\\nuser=%s\\ntime=%s\\nkernel=%s\\n' "
        "\"$(hostname)\" \"$(whoami)\" \"$(date '+%F %T %Z')\" \"$(uname -r)\""
    )
    cmd = (
        "set -e; "
        f"port=$({ssh_prefix_command(profile)} {quote(read_port)}); "
        "port=$(printf '%s\\n' \"$port\" | tail -n 1 | tr -d '[:space:]'); "
        "if [ -z \"$port\" ]; then printf '[失败] 未读取到公网端口 remotePort\\n'; exit 1; fi; "
        f"printf '[目标] 公网 SSH: {public_user}@{PUBLIC_SERVER}:%s\\n' \"$port\"; "
        f"{pass_cmd} ssh {public_options} "
        f"-p \"$port\" {public_user}@{PUBLIC_SERVER} "
        f"{quote(public_probe)}; "
        "printf '\\n[结果] 公网 SSH 测试通过\\n'; "
        f"printf '公网地址: {public_user}@{PUBLIC_SERVER}\\n'; "
        "printf '公网端口: %s\\n' \"$port\"; "
        f"printf '交互命令: ssh {public_user}@{PUBLIC_SERVER} -p %s\\n' \"$port\""
    )
    return CommandSpec("公网 SSH 连通测试", cmd)
